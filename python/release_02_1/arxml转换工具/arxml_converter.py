import re
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext


def transform_content(text: str) -> tuple[str, dict[str, int]]:
    byte_order_replaced_count = 0

    def replace_byte_order(match: re.Match) -> str:
        nonlocal byte_order_replaced_count
        inner = match.group(1)
        if "FIRST" in inner:
            replaced = inner.replace("FIRST", "LAST")
            if replaced != inner:
                byte_order_replaced_count += 1
            return f"<BYTE-ORDER>{replaced}</BYTE-ORDER>"
        return match.group(0)

    text = re.sub(
        r"<BYTE-ORDER>(.*?)</BYTE-ORDER>",
        replace_byte_order,
        text,
        flags=re.DOTALL,
    )

    text, category_replace_count = re.subn(
        r"<CATEGORY>\s*STRING\s*</CATEGORY>",
        "<CATEGORY>utf8</CATEGORY>",
        text,
    )
    stats = {
        "byte_order_replaced": byte_order_replaced_count,
        "category_replaced": category_replace_count,
    }
    return text, stats


def append_log(log_widget: scrolledtext.ScrolledText, message: str) -> None:
    log_widget.config(state="normal")
    log_widget.insert(tk.END, message + "\n")
    log_widget.see(tk.END)
    log_widget.config(state="disabled")


def choose_input_file(entry: tk.Entry) -> None:
    path = filedialog.askopenfilename(
        title="选择输入ARXML文件",
        filetypes=[("ARXML files", "*.arxml"), ("All files", "*.*")],
    )
    if path:
        entry.delete(0, tk.END)
        entry.insert(0, path)


def choose_output_file(entry: tk.Entry) -> None:
    path = filedialog.asksaveasfilename(
        title="选择输出ARXML文件",
        defaultextension=".arxml",
        filetypes=[("ARXML files", "*.arxml"), ("All files", "*.*")],
    )
    if path:
        entry.delete(0, tk.END)
        entry.insert(0, path)


def run_conversion(
    input_entry: tk.Entry, output_entry: tk.Entry, log_widget: scrolledtext.ScrolledText
) -> None:
    input_path = input_entry.get().strip()
    output_path = output_entry.get().strip()

    if not input_path:
        messagebox.showerror("错误", "请选择输入ARXML文件")
        return
    if not output_path:
        messagebox.showerror("错误", "请选择输出ARXML文件")
        return

    try:
        append_log(log_widget, f"开始处理: {input_path}")
        with open(input_path, "r", encoding="utf-8", errors="replace") as file:
            content = file.read()

        new_content, stats = transform_content(content)

        with open(output_path, "w", encoding="utf-8", newline="") as file:
            file.write(new_content)

        append_log(log_widget, f"输出文件: {output_path}")
        if stats["byte_order_replaced"] > 0:
            append_log(
                log_widget,
                f"[已替换] <BYTE-ORDER>...FIRST...</BYTE-ORDER> -> ...LAST...: {stats['byte_order_replaced']} 处",
            )
        if stats["category_replaced"] > 0:
            append_log(
                log_widget,
                f"[已替换] <CATEGORY>STRING</CATEGORY> -> <CATEGORY>utf8</CATEGORY>: {stats['category_replaced']} 处",
            )
        append_log(log_widget, "处理完成")
        messagebox.showinfo("完成", f"转换成功!\n输出文件:\n{output_path}")
    except Exception as exc:
        append_log(log_widget, f"处理失败: {exc}")
        messagebox.showerror("失败", f"转换失败:\n{exc}")


def main() -> None:
    root = tk.Tk()
    root.title("ARXML转换工具")
    root.geometry("900x450")
    root.resizable(False, False)

    tk.Label(root, text="输入ARXML:").grid(row=0, column=0, padx=10, pady=15, sticky="e")
    input_entry = tk.Entry(root, width=76)
    input_entry.grid(row=0, column=1, padx=5, pady=15)
    tk.Button(root, text="浏览...", command=lambda: choose_input_file(input_entry)).grid(
        row=0, column=2, padx=10, pady=15
    )

    tk.Label(root, text="输出ARXML:").grid(row=1, column=0, padx=10, pady=10, sticky="e")
    output_entry = tk.Entry(root, width=76)
    output_entry.grid(row=1, column=1, padx=5, pady=10)
    tk.Button(root, text="浏览...", command=lambda: choose_output_file(output_entry)).grid(
        row=1, column=2, padx=10, pady=10
    )

    tk.Button(
        root,
        text="开始转换",
        width=16,
        command=lambda: run_conversion(input_entry, output_entry, log_output),
    ).grid(row=2, column=1, pady=20)

    tk.Label(root, text="日志:").grid(row=3, column=0, padx=10, pady=5, sticky="ne")
    log_output = scrolledtext.ScrolledText(root, width=105, height=12, state="disabled")
    log_output.grid(row=3, column=1, columnspan=2, padx=5, pady=5, sticky="w")

    root.mainloop()


if __name__ == "__main__":
    main()
