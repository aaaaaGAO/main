#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
步骤解析模块（供 CAN/CIN 生成器复用）

新规则（普通关键字）：
- 在 IO_mapping 翻译之后，关键字之后的所有参数用空格拼接成一个整体字符串作为唯一入参：
    func("arg1 arg2 arg3")
- 无参数则：func()

保留特殊关键字：
- SetRepeatKeyword
- AutoIncreaseInVal
- Clib
- KeepOpenWithTime, KeepShToGNDWithTime, KeepShToPOWWithTime, KeepOverCurWithTime
  （后接：变量/数字/单位如 abc 100 ms → 原样写入 CAPL；或 io_mapping 的 Name 如 J_xxx+ → 换成 Path 后与后续参数一起写入；configuration 名如 ATLEnableConfigure 出现则报错 io_mapping 表中 Name 找不到）

并保留 CIN 的“自动补 Step 前缀”兼容逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Sequence

if TYPE_CHECKING:
    from core.translator.config_enum import ConfigEnumParseError
    from core.translator.io_mapping import IOMappingParseError
else:
    try:
        from core.translator.io_mapping import IOMappingParseError
    except ImportError:  # pragma: no cover - 兼容兜底
        IOMappingParseError = Exception
    try:
        from core.translator.config_enum import ConfigEnumParseError
    except ImportError:  # pragma: no cover - 兼容兜底
        ConfigEnumParseError = Exception


class KeywordMatchError(Exception):
    """关键字匹配失败。"""

    def __init__(self, line: str, func_token: str):
        """参数: line — 原始步骤行；func_token — 未匹配到的函数/关键字。"""
        super().__init__(f"关键字匹配失败: func={func_token!r} line={line!r}")
        self.line = line
        self.func_token = func_token


class StepSyntaxError(Exception):
    """步骤语法错误（参数不足/格式不对）。"""


class ClibMatchError(Exception):
    """Clib 关键字匹配失败（在 Clib 配置表中未找到）。"""

    def __init__(self, line: str, clib_name: str):
        """参数: line — 原始步骤行；clib_name — 在配置表中未找到的 Clib 名称。"""
        super().__init__(f"Clib 关键字匹配失败: clib_name={clib_name!r} line={line!r}")
        self.line = line
        self.clib_name = clib_name


@dataclass(frozen=True)
class ParseResult:
    """单行步骤解析结果：生成的 CAPL 代码行与原始步骤行。
    属性: code_lines — 生成的 CAPL 行列表；original_line_full — 原始步骤行全文。
    """
    code_lines: List[str]
    original_line_full: str


def _strip_inline_comment(s: str) -> str:
    """去掉行内 // 及其后的注释。参数: s — 一行字符串。返回: 去掉注释并 strip 后的字符串。"""
    if "//" in s:
        return s.split("//", 1)[0].strip()
    return s.strip()


def _iter_inclusive(start: float, end: float, step: float) -> List[float]:
    """生成 [start, end] 步长为 step 的数列（含端点）。参数: start/end/step — 起止与步长。返回: 数值列表。"""
    if step == 0:
        return []
    vals: List[float] = []
    cur = start
    if step > 0:
        while cur <= end + 1e-12:
            vals.append(cur)
            cur += step
    else:
        while cur >= end - 1e-12:
            vals.append(cur)
            cur += step
    return vals


def _format_num(x: float) -> str:
    """浮点数格式化为字符串，整数则去掉小数部分。参数: x — 数值。返回: 字符串。"""
    if abs(x - int(x)) < 1e-12:
        return str(int(x))
    return str(x)


def _escape_c_string(s: str) -> str:
    """对 CAPL/类 C 字符串做反斜杠与双引号转义。参数: s — 原始字符串。返回: 转义后字符串。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def parse_step_line(
    line: str,
    keyword_specs: dict,
    *,
    mode: str,
    io_mapping_ctx: Any = None,
    config_enum_ctx: Any = None,
    sanitize_clib_name: Optional[Callable[[str], str]] = None,
    default_param_parser: Optional[Callable[[Sequence[str]], Sequence[str]]] = None,
    clib_validator: Optional[Callable[[str], bool]] = None,
) -> Optional[ParseResult]:
    """解析一行步骤，返回生成的 CAPL 代码行（ParseResult）或 None（空行/注释）。
    参数:
        line: 步骤行原文。
        keyword_specs: 关键字规格字典。
        mode: "can" 或 "cin"。
        io_mapping_ctx: 提供 transform_args 的 IO 映射上下文，可为 None。
        config_enum_ctx: 配置枚举上下文，可为 None。
        sanitize_clib_name: Clib 名称清洗函数，可为 None。
        default_param_parser: Clib 参数默认解析函数，可为 None。
        clib_validator: Clib 名称校验函数，可为 None。
    返回: ParseResult 或 None。
    """
    original_line_full = str(line).strip()
    if not original_line_full:
        return None
    if original_line_full.startswith("//"):
        return None

    line_without_comment = _strip_inline_comment(original_line_full)
    if not line_without_comment:
        return None

    tokens = line_without_comment.split()
    if not tokens:
        return None

    mode_l = str(mode).lower().strip()
    if mode_l not in ("can", "cin"):
        raise ValueError(f"mode 只能是 can/cin，收到: {mode!r}")

    _SPECIAL_CMDS = {
        "setrepeatkeyword",
        "autoincreaseinval",
        "clib",
        "keepopenwithtime",
        "keepshtogndwithtime",
        "keepshtopowwithtime",
        "keepovercurwithtime",
    }
    start_idx = 0
    if len(tokens) >= 2 and tokens[0].lower() == "step":
        if tokens[1].lower() in _SPECIAL_CMDS:
            start_idx = 1

    first_cmd = tokens[start_idx].lower() if start_idx < len(tokens) else ""

    if first_cmd == "setrepeatkeyword":
        val_idx = start_idx + 1
        if len(tokens) < val_idx + 2:
            raise StepSyntaxError(f"SetRepeatKeyword 参数不足: {original_line_full}")

        try:
            repeat_count = int(tokens[val_idx])
        except ValueError:
            raise StepSyntaxError(f"SetRepeatKeyword 次数无效: {tokens[val_idx]!r}")

        inner_line = " ".join(tokens[val_idx + 1 :])
        inner_tokens = inner_line.strip().split()
        if inner_tokens and inner_tokens[0].lower() != "step":
            inner_line = "Step " + inner_line

        out_lines: List[str] = []
        for _ in range(max(0, repeat_count)):
            inner_res = parse_step_line(
                inner_line,
                keyword_specs,
                mode=mode_l,
                io_mapping_ctx=io_mapping_ctx,
                config_enum_ctx=config_enum_ctx,
                sanitize_clib_name=sanitize_clib_name,
                default_param_parser=default_param_parser,
            )
            if inner_res and inner_res.code_lines:
                out_lines.extend(inner_res.code_lines)
        return ParseResult(out_lines, original_line_full)

    if first_cmd == "autoincreaseinval":
        val_idx = start_idx + 1
        if len(tokens) < val_idx + 4:
            raise StepSyntaxError(f"AutoIncreaseInVal 参数不足: {original_line_full}")

        try:
            start_v = float(tokens[val_idx])
            end_v = float(tokens[val_idx + 1])
            step_v = float(tokens[val_idx + 2])
        except ValueError:
            raise StepSyntaxError(
                f"AutoIncreaseInVal 数值参数错误: {tokens[val_idx:val_idx+3]!r}"
            )

        inner_cmd_tokens = tokens[val_idx + 3 :]
        if not inner_cmd_tokens:
            raise StepSyntaxError(f"AutoIncreaseInVal 缺少内部命令: {original_line_full}")

        vals = _iter_inclusive(start_v, end_v, step_v)
        out_lines: List[str] = []
        for v in vals:
            v_str = _format_num(v)
            temp_tokens = list(inner_cmd_tokens)
            temp_tokens.append(v_str)
            new_inner_line = " ".join(temp_tokens)
            new_inner_tokens = new_inner_line.strip().split()
            if new_inner_tokens and new_inner_tokens[0].lower() != "step":
                new_inner_line = "Step " + new_inner_line

            inner_res = parse_step_line(
                new_inner_line,
                keyword_specs,
                mode=mode_l,
                io_mapping_ctx=io_mapping_ctx,
                config_enum_ctx=config_enum_ctx,
                sanitize_clib_name=sanitize_clib_name,
                default_param_parser=default_param_parser,
            )
            if inner_res and inner_res.code_lines:
                for code in inner_res.code_lines:
                    out_lines.append(code.rstrip())
        return ParseResult(out_lines, original_line_full)

    if first_cmd == "clib":
        sub_kw_idx = start_idx + 1
        if len(tokens) <= sub_kw_idx:
            raise StepSyntaxError(f"Clib 缺少子关键字: {original_line_full}")
        sub_kw = tokens[sub_kw_idx]
        original_clib_name = sub_kw
        if sanitize_clib_name is not None:
            sub_kw = sanitize_clib_name(sub_kw)

        if clib_validator is not None:
            if not clib_validator(original_clib_name):
                raise ClibMatchError(original_line_full, original_clib_name)

        capl_func = f"g_HIL_Clib_Swc_Clib_{sub_kw}"
        extra_args = tokens[sub_kw_idx + 1 :]
        if extra_args:
            parsed = (
                list(default_param_parser(extra_args))
                if default_param_parser
                else list(extra_args)
            )
            arg_str = ", ".join(parsed)
            return ParseResult([f"  {capl_func}({arg_str});"], original_line_full)
        return ParseResult([f"  {capl_func}();"], original_line_full)

    _KEEP_TIME_CMDS = {
        "keepopenwithtime",
        "keepshtogndwithtime",
        "keepshtopowwithtime",
        "keepovercurwithtime",
    }

    def _is_literal_token(t: str) -> bool:
        """判断 token 是否为字面量（数字、单位如 ms/s 等），不参与 IO 映射替换。参数: t — 单个 token。返回: bool。"""
        if not t:
            return True
        s = str(t).strip()
        if not s:
            return True
        if s.replace(".", "", 1).replace("-", "", 1).replace("+", "", 1).isdigit():
            return True
        if s[0] in "-+" and s[1:].replace(".", "", 1).isdigit():
            return True
        if s.lower() in ("ms", "s", "us", "ns", "v", "mv", "a", "ma"):
            return True
        return False

    if first_cmd in _KEEP_TIME_CMDS:
        spec_kt = (
            keyword_specs.get("step::" + first_cmd)
            or keyword_specs.get(first_cmd)
            or keyword_specs.get("::" + first_cmd)
        )
        if spec_kt is None or not getattr(spec_kt, "capl_func", None):
            raise KeywordMatchError(original_line_full, first_cmd)
        capl_func = spec_kt.capl_func
        args_kt = tokens[start_idx + 1 :]
        if not args_kt:
            return ParseResult([f"  {capl_func}();"], original_line_full)
        first_tok = str(args_kt[0]).strip()
        rest_toks = args_kt[1:]
        one_arg_raw: Optional[str] = None
        if first_tok.upper().startswith("J_"):
            if io_mapping_ctx is None:
                # 未配置 io_mapping 时，全部透传为参数，不报错
                one_arg_raw = " ".join(args_kt).strip()
            else:
                try:
                    mapped = list(io_mapping_ctx.transform_args([first_tok]))
                    path_val = mapped[0] if mapped else first_tok
                    one_arg_raw = (
                        (path_val + " " + " ".join(rest_toks)).strip()
                        if rest_toks
                        else path_val
                    )
                except IOMappingParseError:
                    raise IOMappingParseError(f"IO_mapping 表中 Name 找不到: {first_tok}")
        elif _is_literal_token(first_tok):
            one_arg_raw = " ".join(args_kt).strip()
        else:

            def _looks_like_config_name(t: str) -> bool:
                if not t or len(t) < 2:
                    return False
                u = t.strip()
                if "Configure" in u or "Enable" in u or "Config" in u:
                    return True
                if u[0].isupper() and any(c.isupper() for c in u[1:]):
                    return True
                return False

            if io_mapping_ctx is not None:
                name_key_kt = first_tok.casefold().strip()
                name_to_path_kt = getattr(io_mapping_ctx, "name_to_path", {})
                name_to_vals_kt = getattr(io_mapping_ctx, "name_to_values", {})
                in_path = name_key_kt in name_to_path_kt
                in_vals = name_key_kt in name_to_vals_kt
                if in_path or in_vals:
                    try:
                        mapped = list(io_mapping_ctx.transform_args([first_tok]))
                        path_val = mapped[0] if mapped else first_tok
                        one_arg_raw = (
                            (path_val + " " + " ".join(rest_toks)).strip()
                            if rest_toks
                            else path_val
                        )
                    except IOMappingParseError:
                        raise IOMappingParseError(
                            f"IO_mapping 表中 Name 找不到: {first_tok}"
                        )
                elif _looks_like_config_name(first_tok):
                    raise IOMappingParseError(f"IO_mapping 表中 Name 找不到: {first_tok}")
                else:
                    one_arg_raw = " ".join(args_kt).strip()
            else:
                # 未配置 io_mapping 时，全部透传为参数，不报错
                one_arg_raw = " ".join(args_kt).strip()
        one_arg = _escape_c_string(one_arg_raw or "")
        return ParseResult([f'  {capl_func}("{one_arg}");'], original_line_full)

    match_tokens = tokens[1:] if (len(tokens) >= 2 and tokens[0].lower() == "step") else tokens
    if not match_tokens:
        raise KeywordMatchError(original_line_full, tokens[0] if tokens else "")

    spec = None
    args_start_idx = 0
    potential_func = match_tokens[0]

    matched = False
    for i in range(len(match_tokens), 0, -1):
        potential_keyword_parts = match_tokens[1:i]
        if potential_keyword_parts:
            potential_keyword = " ".join(potential_keyword_parts)
            full_key = f"{potential_func}::{potential_keyword}".lower()
        else:
            full_key = potential_func.lower()
        if full_key in keyword_specs:
            spec = keyword_specs[full_key]
            args_start_idx = i
            matched = True
            break

    if not matched:
        for i in range(1, min(5, len(match_tokens) + 1)):
            potential_keyword = " ".join(match_tokens[:i])
            keyword_key = f"::{potential_keyword}".lower()
            if keyword_key in keyword_specs:
                spec = keyword_specs[keyword_key]
                args_start_idx = i
                matched = True
                break

    if (not matched or spec is None) and mode_l == "cin":
        if match_tokens and match_tokens[0].lower() != "step":
            new_match_tokens = ["Step"] + match_tokens
            new_potential_func = "Step"
            new_spec = None
            new_args_start_idx = 0
            new_matched = False

            for i in range(len(new_match_tokens), 0, -1):
                potential_keyword_parts = new_match_tokens[1:i]
                if potential_keyword_parts:
                    potential_keyword = " ".join(potential_keyword_parts)
                    full_key = f"{new_potential_func}::{potential_keyword}".lower()
                else:
                    full_key = new_potential_func.lower()
                if full_key in keyword_specs:
                    new_spec = keyword_specs[full_key]
                    new_args_start_idx = i
                    new_matched = True
                    break

            if not new_matched:
                for i in range(1, min(5, len(new_match_tokens) + 1)):
                    potential_keyword = " ".join(new_match_tokens[:i])
                    keyword_key_fallback = f"::{potential_keyword}".lower()
                    if keyword_key_fallback in keyword_specs:
                        new_spec = keyword_specs[keyword_key_fallback]
                        new_args_start_idx = i
                        new_matched = True
                        break

            if new_matched and new_spec is not None:
                match_tokens = new_match_tokens
                spec = new_spec
                args_start_idx = new_args_start_idx
                matched = True
                potential_func = new_potential_func

    if not matched or spec is None:
        raise KeywordMatchError(original_line_full, potential_func)

    args: List[str] = match_tokens[args_start_idx:] if args_start_idx < len(match_tokens) else []

    spec_kw_raw = str(getattr(spec, "keyword", "") or "")
    spec_func_raw = str(getattr(spec, "func_name", "") or "")
    spec_capl_raw = str(getattr(spec, "capl_func", "") or "")
    combined = (
        " ".join([spec_kw_raw, spec_func_raw, spec_capl_raw]).strip().casefold().replace(" ", "_")
    )
    _CFG_KWS = {"set_config", "setconfig"}
    _use_config_enum = any(cw in combined for cw in _CFG_KWS)
    # 当配置了 configuration.xlsx（config_enum_ctx 不为空）时才启用配置枚举转换；
    # 若未配置 configuration.xlsx，则将 Set_Config/Set_CF 视为普通关键字，直接透传参数，不报错。
    if _use_config_enum and config_enum_ctx is not None:
        if not args:
            raise ConfigEnumParseError(
                "Set_Config/Set_CF 至少需要 Name 参数（DID_Config 配置表中的名称）"
            )
        args = list(config_enum_ctx.translate_args(args))
    else:
        if io_mapping_ctx is not None and args:
            first_arg = str(args[0]).strip()
            if first_arg.upper().startswith("J_"):
                args = list(io_mapping_ctx.transform_args(args))

    if args:
        one_arg = " ".join([str(a) for a in args]).strip()
        one_arg = _escape_c_string(one_arg)
        code = f'  {spec.capl_func}("{one_arg}");'
    else:
        code = f"  {spec.capl_func}();"

    return ParseResult([code], original_line_full)


__all__ = [
    "parse_step_line",
    "ParseResult",
    "KeywordMatchError",
    "StepSyntaxError",
    "ClibMatchError",
]

