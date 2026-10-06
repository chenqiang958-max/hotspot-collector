# -*- coding: utf-8 -*-
from __future__ import annotations
import hashlib, hmac, json, os, secrets, sys, time, traceback

SECRET = "CHANGE-ME-hotspot-2026-请改成你自己的一长串随机字符-abcdEFGH1234"
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_HERE = os.path.dirname(os.path.abspath(__file__))
_HISTORY_FILE = os.path.join(_HERE, "已生成的激活码.json")

# 粉色主题
PINK = "#E91E63"
PINK_DEEP = "#C2185B"
PINK_SOFT = "#F8BBD0"
PINK_PALE = "#FCE4EC"
PINK_CARD = "#FFF5F8"
INK = "#3A2430"
INK_SOFT = "#8A6473"
WHITE = "#FFFFFF"
OK = "#2E7D32"


def _rand_seg():
    return "".join(secrets.choice(_ALPHABET) for _ in range(4))


def _sign(payload):
    mac = hmac.new(SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return "".join(_ALPHABET[b % len(_ALPHABET)] for b in mac[:8])


def make_code():
    body = "{}-{}-{}".format(_rand_seg(), _rand_seg(), _rand_seg())
    return "{}-{}".format(body, _sign(body)[:4])


def load_history():
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(items):
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _safe_filename(name):
    import re
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = name.strip(". ")
    return name[:60] if name else ""


def write_code_txt(note_val, code):
    fname = _safe_filename(note_val)
    if not fname:
        return None
    out_dir = os.path.join(_HERE, "激活码文档")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, fname + ".txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("激活码：{}\n\n".format(code))
        f.write("（发给：{}）\n".format(note_val))
        f.write("一个激活码只能激活一台电脑。\n")
    return path


def _font(size, bold=False):
    w = "bold" if bold else "normal"
    return ("Microsoft YaHei", size, w)


def run_tk():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, simpledialog

    app = tk.Tk()
    app.title("发码工具 · 卖家专用")
    app.geometry("900x640")
    app.minsize(760, 520)
    app.configure(bg=PINK_PALE)

    style = ttk.Style(app)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure(
        "Pink.Treeview",
        background=WHITE,
        fieldbackground=WHITE,
        foreground=INK,
        rowheight=32,
        font=("Microsoft YaHei", 11),
        borderwidth=0,
    )
    style.configure(
        "Pink.Treeview.Heading",
        background=PINK,
        foreground=WHITE,
        font=("Microsoft YaHei", 11, "bold"),
        relief="flat",
        padding=8,
    )
    style.map("Pink.Treeview", background=[("selected", PINK_SOFT)], foreground=[("selected", PINK_DEEP)])
    style.map("Pink.Treeview.Heading", background=[("active", PINK_DEEP)])

    header = tk.Frame(app, bg=PINK)
    header.pack(fill="x")
    tk.Label(header, text="发码工具", bg=PINK, fg=WHITE, font=_font(24, True)).pack(pady=(18, 2))
    tk.Label(
        header,
        text="卖家专用 · 请勿把本文件夹发给客户",
        bg=PINK,
        fg=PINK_SOFT,
        font=_font(12),
    ).pack(pady=(0, 16))

    wrap = tk.Frame(app, bg=PINK_PALE)
    wrap.pack(fill="both", expand=True, padx=18, pady=16)

    card = tk.Frame(wrap, bg=PINK_CARD, highlightbackground=PINK_SOFT, highlightthickness=1)
    card.pack(fill="x", pady=(0, 12))

    row = tk.Frame(card, bg=PINK_CARD)
    row.pack(fill="x", padx=16, pady=14)
    tk.Label(row, text="一次生成", bg=PINK_CARD, fg=INK, font=_font(13, True)).pack(side="left")
    e_count = tk.Entry(
        row, width=6, font=_font(14), justify="center",
        bd=0, highlightthickness=2, highlightbackground=PINK_SOFT, highlightcolor=PINK,
        fg=PINK_DEEP, bg=WHITE, insertbackground=PINK,
    )
    e_count.insert(0, "1")
    e_count.pack(side="left", padx=10, ipady=6)
    tk.Label(row, text="个激活码", bg=PINK_CARD, fg=INK_SOFT, font=_font(13)).pack(side="left")
    # 生成按钮放在数量右侧，保证始终可见

    def pink_btn(parent, text, cmd, bg=PINK, fg=WHITE, width=12):
        b = tk.Button(
            parent, text=text, command=cmd, font=_font(12, True),
            bg=bg, fg=fg, activebackground=PINK_DEEP, activeforeground=WHITE,
            bd=0, relief="flat", cursor="hand2", padx=14, pady=8,
        )
        return b

    list_card = tk.Frame(wrap, bg=PINK_CARD, highlightbackground=PINK_SOFT, highlightthickness=1)

    title_row = tk.Frame(list_card, bg=PINK_CARD)
    title_row.pack(fill="x", padx=16, pady=(12, 6))
    tk.Label(title_row, text="已生成的激活码", bg=PINK_CARD, fg=INK, font=_font(14, True)).pack(side="left")
    status = tk.Label(title_row, text="", bg=PINK_CARD, fg=PINK, font=_font(12))
    status.pack(side="right")

    tree_wrap = tk.Frame(list_card, bg=PINK_CARD)
    tree_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 8))
    scroll = ttk.Scrollbar(tree_wrap)
    scroll.pack(side="right", fill="y")
    cols = ("idx", "code", "note", "time")
    tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", height=12, style="Pink.Treeview", yscrollcommand=scroll.set)
    scroll.config(command=tree.yview)
    tree.heading("idx", text="序号")
    tree.heading("code", text="激活码")
    tree.heading("note", text="发给谁")
    tree.heading("time", text="生成时间")
    tree.column("idx", width=70, anchor="center")
    tree.column("code", width=280, anchor="center")
    tree.column("note", width=180, anchor="w")
    tree.column("time", width=160, anchor="center")
    tree.pack(fill="both", expand=True)

    def refresh():
        for i in tree.get_children():
            tree.delete(i)
        items = load_history()
        for i, it in enumerate(reversed(items), 1):
            tree.insert("", "end", values=(
                len(items) - i + 1,
                it.get("code", ""),
                it.get("note", "") or "（未填写）",
                it.get("time", ""),
            ))
        status.config(text="共 {} 个".format(len(items)))

    def gen():
        try:
            n = int((e_count.get() or "1").strip() or "1")
        except Exception:
            n = 1
        n = max(1, min(100, n))
        history = load_history()
        now = time.strftime("%Y-%m-%d %H:%M")
        for _ in range(n):
            history.append({"code": make_code(), "note": "", "time": now})
        save_history(history)
        refresh()
        try:
            app.clipboard_clear()
            app.clipboard_append("\n".join(x["code"] for x in history[-n:]))
        except Exception:
            pass
        messagebox.showinfo("生成完成", "已生成 {} 个激活码，并已复制到剪贴板。".format(n))

    def copy_sel():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中点选一行激活码。")
            return
        code = tree.item(sel[0], "values")[1]
        app.clipboard_clear()
        app.clipboard_append(code)
        messagebox.showinfo("已复制", "激活码已复制：\n{}".format(code))

    def set_note():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中点选一行。")
            return
        code = tree.item(sel[0], "values")[1]
        val = simpledialog.askstring("填写发给谁", "请输入买家备注（将同时生成同名 txt 文档）", parent=app)
        if val is None:
            return
        history = load_history()
        for it in history:
            if it.get("code") == code:
                it["note"] = val
        save_history(history)
        if val.strip():
            write_code_txt(val, code)
        refresh()

    def export_txt():
        history = load_history()
        if not history:
            messagebox.showinfo("提示", "还没有激活码可以导出。")
            return
        path = filedialog.asksaveasfilename(
            title="导出激活码清单",
            defaultextension=".txt",
            initialfile="激活码清单.txt",
            filetypes=[("文本文件", "*.txt")],
        )
        if not path:
            return
        lines = ["激活码清单", "=" * 40]
        for it in history:
            lines.append("{}    发给：{}    （{}）".format(
                it.get("code", ""), it.get("note") or "未填写", it.get("time", "")))
        open(path, "w", encoding="utf-8").write("\n".join(lines))
        messagebox.showinfo("已导出", "清单已保存到：\n{}".format(path))

    btns = tk.Frame(wrap, bg=PINK_PALE)
    btns.pack(fill="x", pady=(12, 0))
    pink_btn(row, "生成激活码", gen).pack(side="right", padx=(8, 0))
    pink_btn(row, "导出清单", export_txt, bg="#F06292").pack(side="right")

    btns.pack(side="bottom", fill="x", pady=(12, 0))
    pink_btn(btns, "生成激活码", gen).pack(side="left", expand=True, fill="x")
    pink_btn(btns, "复制选中", copy_sel, bg=OK).pack(side="left", padx=8)
    pink_btn(btns, "填写发给谁", set_note, bg="#AD1457").pack(side="left")
    pink_btn(btns, "导出清单", export_txt, bg="#F06292").pack(side="left", padx=8)
    list_card.pack(fill="both", expand=True)

    refresh()
    app.mainloop()


def main():
    try:
        run_tk()
    except Exception:
        print(traceback.format_exc())
        try:
            input("发码窗口启动失败，请按回车关闭...")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
