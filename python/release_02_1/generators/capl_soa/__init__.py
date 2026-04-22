#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`generators.capl_soa` 包：中央域服务通信矩阵 → ILNode / SOANode 等 CAPL 生成。

- 主入口在 `entrypoint`（Jinja2 模板 + 矩阵 Excel），本包作命名空间，可按需从包外 `import generators.capl_soa` 触发打包 `hidden-import` 收录。
- 与 `TaskOrchestrator` / `capl_soa/entrypoint` 编排一致，不在本文件实现业务。
"""
