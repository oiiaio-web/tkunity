# -*- coding: utf-8 -*-
"""统一的界面主题（纯 tkinter，无第三方 UI 库）。

深色扁平风格 + 一个强调色，靠颜色、间距和字重做出层次感；
所有控件仍用标准 tk / ttk，方便在任意 Python + Tk 上运行。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

__all__ = [
    "COLORS", "FONTS", "apply_theme", "flat_button", "pill", "separator",
    "section_title", "card",
]

COLORS = {
    "bg":          "#15151f",
    "panel":       "#1c1c28",
    "panel_alt":   "#232333",
    "border":      "#2e2e40",
    "canvas_bg":   "#12121a",
    "text":        "#e6e6f0",
    "text_dim":    "#8b8ba3",
    "text_muted":  "#5f5f78",
    "accent":      "#7c5cff",
    "accent_dim":  "#5a41c4",
    "accent_text": "#ffffff",
    "ok":          "#37d67a",
    "warn":        "#ffb020",
    "err":         "#ff5c7a",
    "sel":         "#00e676",
    "grid":        "#26263a",
}

FONTS = {
    "title":   ("Segoe UI", 15, "bold"),
    "h2":      ("Segoe UI", 10, "bold"),
    "body":    ("Segoe UI", 9),
    "small":   ("Segoe UI", 8),
    "mono":    ("Consolas", 9),
    "mono_sm": ("Consolas", 8),
}


def apply_theme(root):
    """配置 ttk 控件样式，让 Treeview / 滚动条等跟深色主题一致。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Treeview",
                    background=COLORS["panel"],
                    fieldbackground=COLORS["panel"],
                    foreground=COLORS["text"],
                    borderwidth=0,
                    rowheight=24,
                    font=FONTS["body"])
    style.map("Treeview",
              background=[("selected", COLORS["accent_dim"])],
              foreground=[("selected", COLORS["accent_text"])])
    style.configure("Treeview.Heading",
                    background=COLORS["panel_alt"],
                    foreground=COLORS["text_dim"],
                    relief="flat")
    style.configure("TScrollbar",
                    background=COLORS["panel_alt"],
                    troughcolor=COLORS["panel"],
                    bordercolor=COLORS["panel"],
                    arrowcolor=COLORS["text_dim"],
                    width=10)
    style.map("TScrollbar", background=[("active", COLORS["accent_dim"])])
    style.configure("TCombobox",
                    fieldbackground=COLORS["panel_alt"],
                    background=COLORS["panel_alt"],
                    foreground=COLORS["text"],
                    arrowcolor=COLORS["text_dim"])
    style.configure("TCheckbutton", background=COLORS["panel"], foreground=COLORS["text"])
    style.configure("TSeparator", background=COLORS["border"])
    root.configure(bg=COLORS["bg"])
    return style


def flat_button(parent, text, command=None, kind="default", width=None, padx=12, pady=5):
    """扁平按钮；kind: primary / default / ghost / danger。"""
    palette = {
        "primary": (COLORS["accent"], COLORS["accent_text"], COLORS["accent_dim"]),
        "default": (COLORS["panel_alt"], COLORS["text"], COLORS["border"]),
        "ghost":   (COLORS["panel"], COLORS["text_dim"], COLORS["panel_alt"]),
        "danger":  (COLORS["panel_alt"], COLORS["err"], COLORS["err"]),
    }
    bg, fg, hover = palette.get(kind, palette["default"])
    btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                    activebackground=hover, activeforeground=fg,
                    relief=tk.FLAT, bd=0, padx=padx, pady=pady,
                    font=FONTS["body"], cursor="hand2",
                    highlightthickness=0)
    if width is not None:
        btn.configure(width=width)
    btn.bind("<Enter>", lambda e: btn.configure(bg=hover))
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    return btn


def pill(parent, text, color=None):
    """小标签胶囊，用来显示状态。"""
    return tk.Label(parent, text=text, bg=COLORS["panel_alt"],
                    fg=color or COLORS["text_dim"], font=FONTS["small"],
                    padx=8, pady=2)


def separator(parent, vertical=False):
    if vertical:
        return tk.Frame(parent, width=1, bg=COLORS["border"])
    return tk.Frame(parent, height=1, bg=COLORS["border"])


def section_title(parent, text, bg=None):
    wrap = tk.Frame(parent, bg=bg or COLORS["panel"])
    accent = tk.Frame(wrap, width=3, bg=COLORS["accent"])
    accent.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
    label = tk.Label(wrap, text=text, bg=bg or COLORS["panel"], fg=COLORS["text"],
                     font=FONTS["h2"], anchor="w")
    label.pack(side=tk.LEFT)
    return wrap


def card(parent, title=None):
    """返回一个深色卡片容器（内部再 pack 内容）。"""
    outer = tk.Frame(parent, bg=COLORS["panel"], highlightthickness=1,
                     highlightbackground=COLORS["border"])
    if title:
        head = tk.Frame(outer, bg=COLORS["panel_alt"])
        head.pack(fill=tk.X)
        tk.Label(head, text=title, bg=COLORS["panel_alt"], fg=COLORS["text_dim"],
                 font=FONTS["small"], anchor="w", padx=8, pady=4).pack(fill=tk.X)
    body = tk.Frame(outer, bg=COLORS["panel"])
    body.pack(fill=tk.BOTH, expand=True)
    return outer, body
