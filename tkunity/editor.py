# -*- coding: utf-8 -*-
"""Unity 风格的图形编辑器（纯 tkinter，零第三方依赖）。

- 深色扁平主题：统一的 ui 配色、圆角感的卡片、强调色按钮；
- 双模式：2D 场景（精灵 / 物理 / 摄像机）与 3D 场景（软件渲染的网格视口）；
- 开屏动画：启动时显示旋转立方体 + 进度条的 splash，可跳过；
- 层级树、Inspector 动态组件、撤销重做、控制台、预制体、缩放与网格吸附。

布局：
    顶部    品牌 + 2D/3D 切换 + 文件 / 编辑 / 运行 操作
    左侧    层级（父子树）+ 零件库 + 预制体
    中间    2D 画布 或 3D 视口
    右侧    Inspector
    底部    控制台 + 状态栏
"""
from __future__ import annotations

import copy
import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from . import __author__, __author_email__, __license__, __version__
from . import editor3d, export, pyu, three, ui, world
from .components import (
    ADDABLE_COMPONENTS, COMMON_TAGS, COMPONENT_ORDER, COMPONENT_SCHEMAS,
    PARTS, PART_SIZES, component_title, new_component, validate_component,
)

__all__ = ["launch_editor", "EditorApp", "GRID"]

GRID = 20
UNDO_LIMIT = 60
THREED_PARTS = ("立方体", "球体", "平面", "棱锥", "圆柱", "3D 相机")


class EditorApp(object):
    """编辑器主窗口。"""

    def __init__(self, root, file=None):
        self.root = root
        self.project = pyu.new_project("未命名项目")
        self.current_path = None
        self.selection = None
        self.pending_part = None
        self.mode = "2d"
        self.scale = 1.0
        self.snap = True
        self._photos = {}
        self._item_ids = {}
        self._drag = None
        self._prop_vars = {}
        self._prop_widgets = []
        self._undo = []
        self._redo = []
        self._preview = None
        self._dirty = False

        ui.apply_theme(root)
        root.title("tkunity 编辑器 v%s - oiiaio-web" % __version__)
        root.geometry("1420x880")
        root.minsize(1120, 680)

        self._build_header()
        self._build_statusbar()
        self._build_body()
        self._build_console()
        self._bind_shortcuts()
        root.protocol("WM_DELETE_WINDOW", self._quit)

        if file:
            self.open_path(file)
        else:
            self._refresh_all()

    # ------------------------------------------------------------ 顶部
    def _build_header(self):
        bar = tk.Frame(self.root, bg=ui.COLORS["panel"], height=58)
        bar.pack(side=tk.TOP, fill=tk.X)
        bar.pack_propagate(False)

        brand = tk.Frame(bar, bg=ui.COLORS["panel"])
        brand.pack(side=tk.LEFT, padx=(14, 18), pady=8)
        tk.Label(brand, text="◈", bg=ui.COLORS["panel"], fg=ui.COLORS["accent"],
                 font=("Segoe UI", 17, "bold")).pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(brand, text="tkunity", bg=ui.COLORS["panel"], fg=ui.COLORS["text"],
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)

        # 2D / 3D 切换
        switch = tk.Frame(bar, bg=ui.COLORS["panel_alt"])
        switch.pack(side=tk.LEFT, padx=(0, 16), pady=12)
        self.mode_buttons = {}
        for mode, label in (("2d", "2D 场景"), ("3d", "3D 场景")):
            btn = tk.Button(switch, text=label, command=lambda m=mode: self.set_mode(m),
                            bg=ui.COLORS["panel_alt"], fg=ui.COLORS["text_dim"],
                            activebackground=ui.COLORS["accent_dim"],
                            activeforeground=ui.COLORS["accent_text"],
                            relief=tk.FLAT, bd=0, padx=14, pady=6,
                            font=ui.FONTS["body"], cursor="hand2",
                            highlightthickness=0)
            btn.pack(side=tk.LEFT)
            self.mode_buttons[mode] = btn

        actions = tk.Frame(bar, bg=ui.COLORS["panel"])
        actions.pack(side=tk.LEFT, pady=12)
        buttons = [
            ("新建", self.new_project, "ghost"),
            ("打开", self.open_project, "ghost"),
            ("保存", self.save_project, "ghost"),
            ("另存为", self.save_project_as, "ghost"),
            (None, None, None),
            ("撤销", self.undo, "ghost"),
            ("重做", self.redo, "ghost"),
            (None, None, None),
            ("▶ 预览", self.preview, "primary"),
            ("导出 APK", self.export_apk, "default"),
        ]
        for text, cmd, kind in buttons:
            if text is None:
                tk.Frame(actions, width=1, bg=ui.COLORS["border"]).pack(
                    side=tk.LEFT, fill=tk.Y, padx=8, pady=4)
                continue
            ui.flat_button(actions, text, cmd, kind=kind, padx=10, pady=5).pack(
                side=tk.LEFT, padx=2)

        right = tk.Frame(bar, bg=ui.COLORS["panel"])
        right.pack(side=tk.RIGHT, padx=14, pady=12)
        self.zoom_widgets = tk.Frame(right, bg=ui.COLORS["panel"])
        self.zoom_widgets.pack(side=tk.LEFT, padx=(0, 8))
        ui.flat_button(self.zoom_widgets, "−", lambda: self.set_scale(self.scale / 1.25),
                       kind="ghost", padx=8, pady=4).pack(side=tk.LEFT)
        self.scale_label = tk.Label(self.zoom_widgets, text="100%", width=5,
                                    bg=ui.COLORS["panel"], fg=ui.COLORS["text_dim"],
                                    font=ui.FONTS["small"])
        self.scale_label.pack(side=tk.LEFT)
        ui.flat_button(self.zoom_widgets, "+", lambda: self.set_scale(self.scale * 1.25),
                       kind="ghost", padx=8, pady=4).pack(side=tk.LEFT)

        self.snap_var = tk.BooleanVar(value=True)
        self.snap_widget = tk.Checkbutton(right, text="吸附", variable=self.snap_var,
                                          command=lambda: setattr(self, "snap", self.snap_var.get()),
                                          bg=ui.COLORS["panel"], fg=ui.COLORS["text_dim"],
                                          selectcolor=ui.COLORS["panel_alt"],
                                          activebackground=ui.COLORS["panel"],
                                          activeforeground=ui.COLORS["text"],
                                          font=ui.FONTS["small"], bd=0, highlightthickness=0)
        self.snap_widget.pack(side=tk.LEFT, padx=6)
        ui.flat_button(right, "关于", self.about, kind="ghost").pack(side=tk.LEFT)

    # ------------------------------------------------------------ 主体
    def _build_body(self):
        body = tk.Frame(self.root, bg=ui.COLORS["bg"])
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(8, 0))

        # ---------------- 左栏
        left = tk.Frame(body, width=250, bg=ui.COLORS["panel"],
                        highlightthickness=1, highlightbackground=ui.COLORS["border"])
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        left.pack_propagate(False)

        head = tk.Frame(left, bg=ui.COLORS["panel_alt"], height=28)
        head.pack(fill=tk.X)
        head.pack_propagate(False)
        tk.Label(head, text="层级", bg=ui.COLORS["panel_alt"], fg=ui.COLORS["text_dim"],
                 font=ui.FONTS["small"], padx=8).pack(side=tk.LEFT)
        tk.Button(head, text="＋ 空物体", command=self.add_empty, bg=ui.COLORS["panel_alt"],
                  fg=ui.COLORS["accent"], relief=tk.FLAT, bd=0, font=ui.FONTS["small"],
                  activebackground=ui.COLORS["panel_alt"], cursor="hand2",
                  highlightthickness=0).pack(side=tk.RIGHT, padx=6)

        tree_wrap = tk.Frame(left, bg=ui.COLORS["panel"])
        tree_wrap.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))
        self.tree = ttk.Treeview(tree_wrap, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        self._section_label(left, "零件库")
        self.parts_list = tk.Listbox(left, height=8, exportselection=False,
                                     bg=ui.COLORS["panel"], fg=ui.COLORS["text"],
                                     selectbackground=ui.COLORS["accent_dim"],
                                     selectforeground=ui.COLORS["accent_text"],
                                     relief=tk.FLAT, bd=0, highlightthickness=0,
                                     activestyle="none", font=ui.FONTS["body"])
        for name, _comps, _size in PARTS:
            self.parts_list.insert(tk.END, "  " + name)
        self.parts_list.pack(fill=tk.X, padx=6)
        self.parts_list.bind("<<ListboxSelect>>", self._on_parts_select)
        self.parts_list.bind("<Double-Button-1>", self._on_parts_double)

        self._section_label(left, "预制体")
        self.prefab_list = tk.Listbox(left, height=4, exportselection=False,
                                      bg=ui.COLORS["panel"], fg=ui.COLORS["text_dim"],
                                      selectbackground=ui.COLORS["accent_dim"],
                                      selectforeground=ui.COLORS["accent_text"],
                                      relief=tk.FLAT, bd=0, highlightthickness=0,
                                      activestyle="none", font=ui.FONTS["body"])
        self.prefab_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 8))
        self.prefab_list.bind("<Double-Button-1>", self._on_prefab_double)

        # ---------------- 中间：2D 画布 / 3D 视口
        self.center = tk.Frame(body, bg=ui.COLORS["bg"])
        self.center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.view2d = tk.Frame(self.center, bg=ui.COLORS["canvas_bg"])
        self.canvas = tk.Canvas(self.view2d, bg=ui.COLORS["canvas_bg"], highlightthickness=0)
        vbar = tk.Scrollbar(self.view2d, orient=tk.VERTICAL, command=self.canvas.yview)
        hbar = tk.Scrollbar(self.view2d, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        self.view3d = tk.Frame(self.center, bg=ui.COLORS["canvas_bg"])
        self.view3d_widget = editor3d.Scene3DView(
            self.view3d, on_select=self._on_3d_select, on_change=self._on_3d_change,
            on_status=self._set_status)
        self.view3d_widget.pack(fill=tk.BOTH, expand=True)

        # ---------------- 右栏 Inspector
        right = tk.Frame(body, width=340, bg=ui.COLORS["panel"],
                         highlightthickness=1, highlightbackground=ui.COLORS["border"])
        right.pack(side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        right.pack_propagate(False)
        head_r = tk.Frame(right, bg=ui.COLORS["panel_alt"], height=28)
        head_r.pack(fill=tk.X)
        head_r.pack_propagate(False)
        tk.Label(head_r, text="Inspector", bg=ui.COLORS["panel_alt"], fg=ui.COLORS["text_dim"],
                 font=ui.FONTS["small"], padx=8).pack(side=tk.LEFT)
        ui.flat_button(head_r, "重置", self._refresh_props, kind="ghost",
                       padx=8, pady=1).pack(side=tk.RIGHT, padx=4)

        self.prop_canvas = tk.Canvas(right, bg=ui.COLORS["panel"], highlightthickness=0)
        prop_scroll = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.prop_canvas.yview)
        self.prop_frame = tk.Frame(self.prop_canvas, bg=ui.COLORS["panel"])
        self.prop_canvas.configure(yscrollcommand=prop_scroll.set)
        prop_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.prop_canvas.pack(fill=tk.BOTH, expand=True)
        self.prop_window = self.prop_canvas.create_window((0, 0), window=self.prop_frame, anchor="nw")
        self.prop_frame.bind("<Configure>", self._on_prop_configure)
        self.prop_canvas.bind("<Configure>", self._on_prop_canvas_configure)

        self.set_mode("2d")

    def _section_label(self, parent, text):
        row = tk.Frame(parent, bg=ui.COLORS["panel"])
        row.pack(fill=tk.X, pady=(10, 2), padx=8)
        tk.Frame(row, width=3, bg=ui.COLORS["accent"]).pack(side=tk.LEFT, fill=tk.Y, padx=(0, 6))
        tk.Label(row, text=text, bg=ui.COLORS["panel"], fg=ui.COLORS["text_dim"],
                 font=ui.FONTS["small"]).pack(side=tk.LEFT)

    def _build_console(self):
        wrap = tk.Frame(self.root, bg=ui.COLORS["panel"])
        wrap.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(6, 0))
        head = tk.Frame(wrap, bg=ui.COLORS["panel_alt"], height=24)
        head.pack(fill=tk.X)
        head.pack_propagate(False)
        tk.Label(head, text="控制台", bg=ui.COLORS["panel_alt"], fg=ui.COLORS["text_dim"],
                 font=ui.FONTS["small"], padx=8).pack(side=tk.LEFT)
        tk.Button(head, text="清空", command=self.clear_console, bg=ui.COLORS["panel_alt"],
                  fg=ui.COLORS["text_muted"], relief=tk.FLAT, bd=0, font=ui.FONTS["small"],
                  activebackground=ui.COLORS["panel_alt"], cursor="hand2",
                  highlightthickness=0).pack(side=tk.RIGHT, padx=8)
        self.console = tk.Text(wrap, height=4, bg="#0f0f17", fg=ui.COLORS["text_dim"],
                               insertbackground=ui.COLORS["text"], relief=tk.FLAT, bd=0,
                               font=ui.FONTS["mono_sm"], padx=8, pady=4)
        self.console.pack(fill=tk.X)
        self.console.configure(state=tk.DISABLED)

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=ui.COLORS["panel_alt"], height=26)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        bar.pack_propagate(False)
        self.status_dot = tk.Label(bar, text="●", bg=ui.COLORS["panel_alt"],
                                   fg=ui.COLORS["ok"], font=ui.FONTS["small"])
        self.status_dot.pack(side=tk.LEFT, padx=(10, 4))
        self.status = tk.Label(bar, text="就绪", anchor="w", bg=ui.COLORS["panel_alt"],
                               fg=ui.COLORS["text_dim"], font=ui.FONTS["small"])
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stats = tk.Label(bar, text="", bg=ui.COLORS["panel_alt"],
                              fg=ui.COLORS["text_muted"], font=ui.FONTS["small"])
        self.stats.pack(side=tk.RIGHT, padx=10)

    def _set_status(self, text):
        if getattr(self, "status", None) is not None:
            self.status.config(text=text)

    def _update_stats(self):
        entities = self.project.get("entities", [])
        meshes = sum(1 for e in entities if e.get("components", {}).get("Mesh3D"))
        self.stats.config(text="物体 %d · 3D %d · 模式 %s"
                               % (len(entities), meshes, self.mode.upper()))

    def log(self, text):
        self.console.configure(state=tk.NORMAL)
        self.console.insert(tk.END, str(text) + "\n")
        self.console.see(tk.END)
        self.console.configure(state=tk.DISABLED)

    def clear_console(self):
        self.console.configure(state=tk.NORMAL)
        self.console.delete("1.0", tk.END)
        self.console.configure(state=tk.DISABLED)

    # ------------------------------------------------------------ 模式
    def set_mode(self, mode):
        self.mode = mode
        if mode == "3d":
            self.view2d.pack_forget()
            self.view3d.pack(fill=tk.BOTH, expand=True)
            self.view3d_widget.set_project(self.project)
            self.zoom_widgets.pack_forget()
            self.snap_widget.pack_forget()
            self._set_status("3D 场景：左键拖动环绕，Shift+左键平移，滚轮缩放")
        else:
            self.view3d.pack_forget()
            self.view2d.pack(fill=tk.BOTH, expand=True)
            self.zoom_widgets.pack(side=tk.LEFT, padx=(0, 8))
            self.snap_widget.pack(side=tk.LEFT, padx=6)
            self.redraw_all()
            self._set_status("2D 场景")
        for key, btn in self.mode_buttons.items():
            active = key == mode
            btn.configure(bg=ui.COLORS["accent"] if active else ui.COLORS["panel_alt"],
                          fg=ui.COLORS["accent_text"] if active else ui.COLORS["text_dim"])
        self._update_stats()

    # ------------------------------------------------------------ 撤销 / 重做
    def push_undo(self):
        self._undo.append((copy.deepcopy(self.project), self.selection))
        if len(self._undo) > UNDO_LIMIT:
            del self._undo[0]
        self._redo = []
        self._dirty = True
        self._update_title()

    def undo(self):
        if not self._undo:
            self._set_status("没有可撤销的操作")
            return
        self._redo.append((copy.deepcopy(self.project), self.selection))
        self.project, self.selection = self._undo.pop()
        self._refresh_all()
        self._set_status("已撤销")

    def redo(self):
        if not self._redo:
            self._set_status("没有可重做的操作")
            return
        self._undo.append((copy.deepcopy(self.project), self.selection))
        self.project, self.selection = self._redo.pop()
        self._refresh_all()
        self._set_status("已重做")

    def _update_title(self):
        name = self.project["meta"].get("name", "未命名项目")
        mark = " •" if self._dirty else ""
        self.root.title("tkunity 编辑器 v%s - %s%s" % (__version__, name, mark))

    # ------------------------------------------------------------ 项目
    def new_project(self):
        if not self._confirm_discard():
            return
        self.push_undo()
        self.project = pyu.new_project("未命名项目")
        self.current_path = None
        self.selection = None
        self.pending_part = None
        self._photos.clear()
        self._dirty = False
        self._refresh_all()
        self._set_status("已新建项目")

    def _confirm_discard(self):
        if not self._dirty:
            return True
        return messagebox.askyesno("未保存", "当前项目有未保存的修改，确定放弃吗？")

    def open_project(self):
        if not self._confirm_discard():
            return
        path = filedialog.askopenfilename(
            title="打开 tkunity 项目", defaultextension=".pyu",
            filetypes=[("tkunity 项目", "*.pyu"), ("所有文件", "*.*")])
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            self.project = pyu.load(path)
        except Exception as exc:
            messagebox.showerror("打开失败", "无法读取 %s\n%s" % (path, exc))
            return
        self.current_path = path
        self.selection = None
        self.pending_part = None
        self._photos.clear()
        self._undo, self._redo = [], []
        self._dirty = False
        self._refresh_all()
        self._set_status("已打开: %s" % path)

    def save_project(self):
        if self.current_path:
            self._write_pyu(self.current_path)
        else:
            self.save_project_as()

    def save_project_as(self):
        path = filedialog.asksaveasfilename(
            title="保存 tkunity 项目", defaultextension=".pyu",
            initialfile=self.project["meta"].get("name", "game") + ".pyu",
            filetypes=[("tkunity 项目", "*.pyu"), ("所有文件", "*.*")])
        if path:
            self._write_pyu(path)

    def _write_pyu(self, path):
        try:
            pyu.save(self.project, path)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self.current_path = path
        self._dirty = False
        self._update_title()
        self._set_status("已保存: %s" % path)

    # ------------------------------------------------------------ 运行 / 导出
    def preview(self):
        if three.has_3d(self.project):
            self._preview_3d()
            return
        if self._preview is not None and self._preview[0].winfo_exists():
            self._preview[0].destroy()
        win = tk.Toplevel(self.root)
        win.title("预览 - %s" % self.project["meta"].get("name", "游戏"))
        win.configure(bg=ui.COLORS["bg"])
        from .runtime import Scene
        try:
            scene = Scene(win, self.project, on_log=self.log)
        except Exception as exc:
            messagebox.showerror("预览失败", str(exc))
            win.destroy()
            return
        scene.canvas.pack(fill="both", expand=True)
        bar = tk.Frame(win, bg=ui.COLORS["panel"])
        bar.pack(fill=tk.X)
        ui.flat_button(bar, "暂停 / 继续", lambda: self._toggle_pause(scene),
                       kind="ghost").pack(side=tk.LEFT, padx=4, pady=4)
        ui.flat_button(bar, "单步", scene.step, kind="ghost").pack(side=tk.LEFT, padx=4)
        ui.flat_button(bar, "重启", scene.restart, kind="ghost").pack(side=tk.LEFT, padx=4)
        ui.flat_button(bar, "关闭", win.destroy, kind="default").pack(side=tk.LEFT, padx=4)
        self._preview = (win, scene)
        win.protocol("WM_DELETE_WINDOW", lambda: (scene.stop(), win.destroy()))
        scene.start()
        self.log("[运行] 2D 预览已启动（%d 个物体）" % len(self.project["entities"]))

    def _preview_3d(self):
        if self._preview is not None and self._preview[0].winfo_exists():
            self._preview[0].destroy()
        from .runtime import Scene3DPreview
        win = tk.Toplevel(self.root)
        win.title("3D 预览 - %s" % self.project["meta"].get("name", "场景"))
        win.configure(bg=ui.COLORS["bg"])
        preview = Scene3DPreview(win, self.project, on_log=self.log)
        preview.canvas.pack(fill=tk.BOTH, expand=True)
        bar = tk.Frame(win, bg=ui.COLORS["panel"])
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        def toggle_orbit():
            preview.auto_orbit = not preview.auto_orbit
            self.log("[运行] 自动环绕 %s" % ("开启" if preview.auto_orbit else "关闭"))

        def close():
            preview.stop()
            win.destroy()

        ui.flat_button(bar, "自动环绕", toggle_orbit, kind="ghost").pack(side=tk.LEFT, padx=4, pady=4)
        ui.flat_button(bar, "重置视角", preview.restart, kind="ghost").pack(side=tk.LEFT, padx=4)
        ui.flat_button(bar, "关闭", close, kind="default").pack(side=tk.LEFT, padx=4)
        win.protocol("WM_DELETE_WINDOW", close)
        self._preview = (win, preview)
        preview.start()
        self.log("[运行] 3D 预览已启动（软件渲染）")

    def _toggle_pause(self, scene):
        if scene.paused:
            scene.resume()
            self.log("[运行] 继续")
        else:
            scene.pause()
            self.log("[运行] 暂停")

    def export_apk(self):
        if three.has_3d(self.project):
            messagebox.showinfo(
                "3D 场景",
                "检测到 3D 网格。APK 导出目前只支持 2D 场景，\n"
                "导出工程里会忽略这些 3D 物体（并给出警告）。")
        outdir = filedialog.askdirectory(title="选择导出目录（将生成 Android 工程）")
        if not outdir:
            return
        target = os.path.join(outdir, "android_" + self.project["meta"].get("name", "game"))
        try:
            warnings = []
            files = export.build(self.project, target, warnings=warnings)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        for warning in warnings:
            self.log("[导出警告] %s" % warning)
        messagebox.showinfo("导出成功",
                            "已生成 %d 个文件到:\n%s\n\n"
                            "下一步：设置 ANDROID_HOME 后运行 build_apk.bat / build_apk.sh"
                            % (len(files), target))
        self.log("[导出] %d 个文件 -> %s" % (len(files), target))
        self._set_status("已导出 Android 工程: %s" % target)

    def about(self):
        messagebox.showinfo(
            "关于 tkunity",
            "tkunity v%s\nUnity 风格 2D / 3D 游戏编辑器与运行时\n\n"
            "Apache License 2.0\nCopyright 2026 %s <%s>\n\n"
            "纯 Python 标准库实现（无 pygame / 无任何第三方依赖）\n"
            "2D：组件、父子层级、预制体、刚体物理、碰撞触发器、脚本、摄像机\n"
            "3D：软件渲染视口（立方体/球体/平面/棱锥/圆柱）、轨道相机\n"
            "可把 2D 场景导出为 Android APK 工程" %
            (__version__, __author__, __author_email__))

    def _quit(self):
        if not self._confirm_discard():
            return
        if self._preview is not None and self._preview[0].winfo_exists():
            if self._preview[1] is not None:
                self._preview[1].stop()
        self.root.destroy()

    # ------------------------------------------------------------ 场景辅助
    @property
    def scene_w(self):
        return int(self.project["meta"].get("scene_width", 960))

    @property
    def scene_h(self):
        return int(self.project["meta"].get("scene_height", 640))

    def _find(self, eid):
        return pyu.entity_by_id(self.project, eid)

    def _is_3d(self, entity):
        return bool(entity.get("components", {}).get("Mesh3D"))

    def set_scale(self, value):
        self.scale = max(0.25, min(4.0, value))
        self.scale_label.config(text="%d%%" % round(self.scale * 100))
        self.redraw_all()

    def _snap(self, value):
        if not self.snap:
            return int(round(value))
        return int(round(value / GRID) * GRID)

    def _refresh_all(self):
        self.redraw_all()
        self._refresh_hierarchy()
        self._refresh_prefabs()
        self._refresh_props()
        self.view3d_widget.set_project(self.project)
        if self.selection is not None:
            self.view3d_widget.set_selection(self.selection)
        self._update_title()
        self._update_stats()

    # ------------------------------------------------------------ 2D 画布
    def redraw_all(self):
        self.canvas.delete("all")
        self._item_ids.clear()
        sw, sh = self.scene_w * self.scale, self.scene_h * self.scale
        self.canvas.configure(scrollregion=(-40, -40, sw + 40, sh + 40),
                              background=ui.COLORS["canvas_bg"])
        self.canvas.create_rectangle(0, 0, sw, sh,
                                     fill=self.project["meta"].get("background", "#1e1e2e"),
                                     outline=ui.COLORS["border"], width=1, tags=("scene",))
        self._draw_grid()
        cache = {}
        for entity in world.draw_order(self.project):
            if self._is_3d(entity):
                continue
            self._draw_entity(entity, cache)
        self._draw_selection()

    def _draw_grid(self):
        sw, sh = self.scene_w * self.scale, self.scene_h * self.scale
        step = GRID * self.scale
        if step < 4:
            return
        for i in range(0, int(sw) + 1, max(1, int(step))):
            self.canvas.create_line(i, 0, i, sh, fill=ui.COLORS["grid"], tags=("grid",))
        for j in range(0, int(sh) + 1, max(1, int(step))):
            self.canvas.create_line(0, j, sw, j, fill=ui.COLORS["grid"], tags=("grid",))

    def _draw_entity(self, entity, cache):
        eid = entity.get("id")
        comps = entity.get("components", {})
        wt = world.world_transform(self.project, entity, cache)
        x, y = wt["x"] * self.scale, wt["y"] * self.scale
        w, h = wt["w"] * self.scale, wt["h"] * self.scale
        active = world.active_in_hierarchy(self.project, entity)
        ids = []
        sprite = comps.get("Sprite")
        if sprite is not None:
            shape = sprite.get("shape", "rect")
            fill = sprite.get("fill", "") if active else "#3a3a4a"
            outline = sprite.get("outline", "") if active else "#55556a"
            if shape == "image" and sprite.get("image"):
                photo = self._get_photo(sprite["image"])
                if photo is not None:
                    ids.append(self.canvas.create_image(x + w / 2, y + h / 2, image=photo,
                                                        state=tk.NORMAL if active else tk.DISABLED))
            elif shape == "oval":
                ids.append(self.canvas.create_oval(x, y, x + w, y + h, fill=fill,
                                                   outline=outline, width=2))
            else:
                ids.append(self.canvas.create_rectangle(x, y, x + w, y + h, fill=fill,
                                                        outline=outline, width=2))
            rot = float(wt["rotation"] or 0)
            if rot and shape != "image":
                for iid in ids:
                    self.canvas.delete(iid)
                ids = []
                pts = []
                for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h)):
                    pts.extend(world.rotate_point(px, py, x + w / 2, y + h / 2, rot))
                ids.append(self.canvas.create_polygon(*pts, fill=fill, outline=outline, width=2))
        else:
            ids.append(self.canvas.create_rectangle(x, y, x + w, y + h, fill="",
                                                    outline=ui.COLORS["border"], width=1,
                                                    dash=(3, 3)))
        label = comps.get("Label")
        if label and label.get("text"):
            font = ("Segoe UI", max(1, int(float(label.get("font_size", 18)) * self.scale)),
                    "bold" if label.get("bold") else "normal")
            ids.append(self.canvas.create_text(x + w / 2, y + h / 2, text=str(label.get("text")),
                                               font=font, fill=label.get("color", "#000000")))
        ids.append(self.canvas.create_text(x + 2, y - 2, text=entity.get("name", ""),
                                           anchor="sw", font=ui.FONTS["small"],
                                           fill=ui.COLORS["text_dim"] if active else ui.COLORS["err"]))
        if comps.get("Camera2D"):
            ids.append(self.canvas.create_text(x + w / 2, y + h / 2, text="◉",
                                               font=("Segoe UI", 12), fill=ui.COLORS["warn"]))
        self._item_ids[eid] = ids

    def _get_photo(self, asset_name):
        if not asset_name:
            return None
        if asset_name in self._photos:
            return self._photos[asset_name]
        b64 = self.project.get("assets", {}).get(asset_name)
        if not b64:
            return None
        try:
            photo = tk.PhotoImage(data=b64)
        except Exception:
            return None
        self._photos[asset_name] = photo
        return photo

    def _draw_selection(self):
        self.canvas.delete("sel")
        if self.selection is None:
            return
        entity = self._find(self.selection)
        if entity is None or self._is_3d(entity):
            return
        r = world.rect_of(entity, self.project)
        x, y = r[0] * self.scale, r[1] * self.scale
        w, h = (r[2] - r[0]) * self.scale, (r[3] - r[1]) * self.scale
        self.canvas.create_rectangle(x - 3, y - 3, x + w + 3, y + h + 3,
                                     outline=ui.COLORS["sel"], width=2, tags=("sel",))
        self.canvas.create_rectangle(x + w - 6, y + h - 6, x + w + 4, y + h + 4,
                                     fill=ui.COLORS["sel"], outline=ui.COLORS["sel"], tags=("sel",))

    def redraw_entity(self, entity):
        if entity is None or self._is_3d(entity):
            return
        eid = entity.get("id")
        for iid in self._item_ids.pop(eid, []):
            try:
                self.canvas.delete(iid)
            except Exception:
                pass
        cache = {}
        for ent in world.draw_order(self.project):
            if ent.get("id") == eid:
                self._draw_entity(ent, cache)
                break
        self._draw_selection()

    # ------------------------------------------------------------ 层级
    def _refresh_hierarchy(self):
        self.tree.delete(*self.tree.get_children())

        def add_nodes(entity):
            label = entity.get("name", "?")
            comps = entity.get("components", {})
            if self._is_3d(entity):
                label = "◇ " + label
            if not entity.get("active", True):
                label += "（未激活）"
            self.tree.insert("", "end", iid=str(entity.get("id")), text=label, open=True)
            for kid in pyu.children_of(self.project, entity.get("id")):
                add_nodes(kid)

        for root_entity in pyu.root_entities(self.project):
            add_nodes(root_entity)
        if self.selection is not None and self.tree.exists(str(self.selection)):
            self.tree.selection_set(str(self.selection))
            self.tree.see(str(self.selection))

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if sel:
            try:
                eid = int(sel[0])
            except ValueError:
                return
            self.selection = eid
            self._draw_selection()
            self.view3d_widget.set_selection(eid)
            self._refresh_props()

    # ------------------------------------------------------------ 放置
    def _on_parts_select(self, event):
        sel = self.parts_list.curselection()
        name = PARTS[sel[0]][0] if sel else None
        self.pending_part = name
        if name:
            if name in THREED_PARTS and self.mode != "3d":
                self._set_status("「%s」是 3D 零件，已切到 3D 场景" % name)
                self.set_mode("3d")
            self._set_status("放置「%s」：2D 点画布，3D 直接点放置" % name)

    def _on_parts_double(self, event):
        idx = self.parts_list.nearest(event.y)
        if idx is None or idx < 0:
            return
        name = PARTS[idx][0]
        if name in THREED_PARTS:
            self.set_mode("3d")
            self._place_part_3d(name)
            return
        size = PART_SIZES.get(name, (80, 60))
        self._place_part(name, self.scene_w // 2 - size[0] // 2,
                         self.scene_h // 2 - size[1] // 2)

    def _part_spec(self, name):
        for part in PARTS:
            if part[0] == name:
                return part
        return None

    def _place_part_3d(self, part_name):
        spec = self._part_spec(part_name)
        if spec is None:
            return
        _name, comps, _size = spec
        self.push_undo()
        target = self.view3d_widget.camera.target
        comps = copy.deepcopy(comps)
        if "Transform3D" in comps:
            comps["Transform3D"].setdefault("x", round(target[0], 2))
            comps["Transform3D"].setdefault("y", 0.5)
            comps["Transform3D"].setdefault("z", round(target[2], 2))
        entity = pyu.add_entity(self.project, pyu.unique_name(self.project, part_name),
                                components=comps,
                                transform={"x": 0, "y": 0, "width": 60, "height": 60})
        self.pending_part = None
        self._refresh_all()
        self.select(entity["id"])
        self.log("[编辑] 放置 3D 物体 %s" % entity["name"])

    def _place_part(self, part_name, x, y):
        spec = self._part_spec(part_name)
        if spec is None:
            return
        _name, comps, size = spec
        if part_name in THREED_PARTS:
            self._place_part_3d(part_name)
            return
        self.push_undo()
        parent = self.selection if self.selection is not None else None
        entity = pyu.add_entity(self.project, name=pyu.unique_name(self.project, part_name),
                                components=copy.deepcopy(comps),
                                transform={"x": x, "y": y, "width": size[0], "height": size[1]},
                                parent=parent)
        self.pending_part = None
        self._refresh_all()
        self.select(entity["id"])
        self.log("[编辑] 放置 %s" % entity["name"])
        self._set_status("已放置「%s」" % entity["name"])

    def add_empty(self):
        self.push_undo()
        parent = self.selection if self.selection is not None else None
        entity = pyu.add_entity(self.project, pyu.unique_name(self.project, "空物体"),
                                transform={"x": 0, "y": 0, "width": 40, "height": 40},
                                parent=parent)
        self._refresh_all()
        self.select(entity["id"])

    def _on_prefab_double(self, event):
        idx = self.prefab_list.nearest(event.y)
        if idx is None or idx < 0:
            return
        name = self.prefab_list.get(idx)
        self.push_undo()
        try:
            entity = pyu.instantiate_prefab(self.project, name,
                                            self.scene_w // 2, self.scene_h // 2)
        except Exception as exc:
            messagebox.showerror("预制体", str(exc))
            return
        self._refresh_all()
        self.select(entity["id"])
        self.log("[编辑] 实例化预制体 %s" % name)

    def _refresh_prefabs(self):
        self.prefab_list.delete(0, tk.END)
        for name in pyu.prefab_names(self.project):
            self.prefab_list.insert(tk.END, "  " + name)

    # ------------------------------------------------------------ 2D 交互
    def _on_canvas_press(self, event):
        x = self.canvas.canvasx(event.x) / self.scale
        y = self.canvas.canvasy(event.y) / self.scale
        if self.pending_part:
            self._place_part(self.pending_part, self._snap(x), self._snap(y))
            return
        eid = world.hit_test(self.project, x, y, accept=lambda e: not self._is_3d(e))
        if eid is None:
            self.select(None)
            return
        self.select(eid)
        entity = self._find(eid)
        r = world.rect_of(entity, self.project)
        if abs(x - r[2]) < 12 / self.scale and abs(y - r[3]) < 12 / self.scale:
            self._drag = {"eid": eid, "mode": "resize",
                          "ox": r[2] - r[0], "oy": r[3] - r[1], "sx": x, "sy": y}
        else:
            self._drag = {"eid": eid, "mode": "move",
                          "ox": float(entity["components"]["Transform"].get("x", 0)),
                          "oy": float(entity["components"]["Transform"].get("y", 0)),
                          "sx": x, "sy": y}
            self.push_undo()

    def _on_canvas_drag(self, event):
        if not self._drag:
            return
        x = self.canvas.canvasx(event.x) / self.scale
        y = self.canvas.canvasy(event.y) / self.scale
        d = self._drag
        entity = self._find(d["eid"])
        if entity is None:
            self._drag = None
            return
        t = entity["components"]["Transform"]
        parent = pyu.entity_by_id(self.project, entity.get("parent"))
        pscale = 1.0
        if parent is not None:
            pscale = world.world_transform(self.project, parent).get("scale", 1.0) or 1.0
        if d["mode"] == "move":
            nx = d["ox"] + (x - d["sx"]) / pscale
            ny = d["oy"] + (y - d["sy"]) / pscale
            t["x"], t["y"] = float(self._snap(nx)), float(self._snap(ny))
        else:
            nw = max(GRID / 2.0, d["ox"] + (x - d["sx"]) / pscale)
            nh = max(GRID / 2.0, d["oy"] + (y - d["sy"]) / pscale)
            t["width"], t["height"] = float(self._snap(nw)) or GRID, float(self._snap(nh)) or GRID
        self.redraw_all()
        self._refresh_props()

    def _on_canvas_release(self, event):
        self._drag = None

    # ------------------------------------------------------------ 3D 交互
    def _on_3d_select(self, eid):
        self.selection = eid
        self._refresh_props()
        self._refresh_hierarchy()
        self.view3d_widget.set_selection(eid)
        self._update_stats()

    def _on_3d_change(self):
        self._dirty = True
        self._update_title()
        self._refresh_props()

    def select(self, eid):
        self.selection = eid
        self._draw_selection()
        self.view3d_widget.set_selection(eid)
        self._refresh_props()
        if eid is not None and self.tree.exists(str(eid)):
            self.tree.selection_set(str(eid))
            self.tree.see(str(eid))

    def nudge(self, dx, dy):
        if self.selection is None:
            return
        entity = self._find(self.selection)
        if entity is None:
            return
        self.push_undo()
        if self._is_3d(entity) and entity["components"].get("Transform3D"):
            t3 = entity["components"]["Transform3D"]
            t3["x"] = round(float(t3.get("x", 0)) + dx / 40.0, 2)
            t3["z"] = round(float(t3.get("z", 0)) + dy / 40.0, 2)
            self.view3d_widget._redraw()
        else:
            t = entity["components"]["Transform"]
            t["x"] = float(t.get("x", 0)) + dx
            t["y"] = float(t.get("y", 0)) + dy
            self.redraw_all()
        self._refresh_props()

    # ------------------------------------------------------------ 增删改
    def delete_selection(self):
        if self.selection is None:
            return
        entity = self._find(self.selection)
        if entity is None:
            self.selection = None
            return
        self.push_undo()
        ids = pyu.remove_entity(self.project, self.selection)
        self.log("[编辑] 删除 %s（含子物体 %d 个）" % (entity.get("name"), len(ids) - 1))
        self.selection = None
        self._refresh_all()
        self._set_status("已删除「%s」" % entity.get("name"))

    def duplicate_selection(self):
        if self.selection is None:
            return
        src = self._find(self.selection)
        if src is None:
            return
        self.push_undo()
        if self._is_3d(src) and src["components"].get("Transform3D"):
            comps = copy.deepcopy(src["components"])
            comps["Transform3D"]["x"] = round(float(comps["Transform3D"].get("x", 0)) + 1.0, 2)
            entity = pyu.add_entity(self.project, pyu.unique_name(self.project, src["name"] + " (1)"),
                                    components=comps)
        else:
            entity = pyu.clone_entity(self.project, src, offset_x=GRID, offset_y=GRID)
        self._refresh_all()
        self.select(entity["id"])
        self._set_status("已复制「%s」" % src.get("name"))

    def add_component(self, comp_name):
        entity = self._find(self.selection)
        if entity is None or comp_name in entity["components"]:
            return
        self.push_undo()
        entity["components"][comp_name] = new_component(comp_name)
        self._refresh_all()
        self.log("[编辑] %s 添加组件 %s" % (entity.get("name"), comp_name))

    def remove_component(self, comp_name):
        entity = self._find(self.selection)
        if entity is None or comp_name == "Transform":
            return
        self.push_undo()
        entity["components"].pop(comp_name, None)
        self._refresh_all()

    def save_prefab(self):
        entity = self._find(self.selection)
        if entity is None:
            return
        name = simpledialog.askstring("保存预制体", "预制体名称：",
                                      initialvalue=entity.get("name", "prefab"))
        if not name:
            return
        self.push_undo()
        prefab = pyu.save_prefab(self.project, entity["id"], name.strip())
        self._refresh_prefabs()
        self.log("[编辑] 已保存预制体 %s" % prefab)

    # ------------------------------------------------------------ Inspector
    def _on_prop_configure(self, event):
        self.prop_canvas.configure(scrollregion=self.prop_canvas.bbox("all"))

    def _on_prop_canvas_configure(self, event):
        self.prop_canvas.itemconfigure(self.prop_window, width=event.width)

    def _clear_props(self):
        for widget in self._prop_widgets:
            try:
                widget.destroy()
            except Exception:
                pass
        self._prop_widgets = []
        self._prop_vars = {}

    def _refresh_props(self):
        self._clear_props()
        entity = self._find(self.selection) if self.selection is not None else None
        if entity is None:
            tk.Label(self.prop_frame, text="未选中物体\n\n在层级里点一个物体，或从零件库放一个进来",
                     bg=ui.COLORS["panel"], fg=ui.COLORS["text_muted"], justify="left",
                     font=ui.FONTS["body"]).pack(anchor="w", pady=14, padx=10)
            self._update_stats()
            return

        f = self.prop_frame
        panel = ui.COLORS["panel"]

        def section(text, remove=None):
            bar = tk.Frame(f, bg=panel)
            bar.pack(fill=tk.X, pady=(10, 2))
            tk.Frame(bar, width=3, bg=ui.COLORS["accent"]).pack(side=tk.LEFT, fill=tk.Y, padx=(6, 6))
            tk.Label(bar, text=text, bg=panel, fg=ui.COLORS["text"],
                     font=ui.FONTS["h2"]).pack(side=tk.LEFT)
            if remove is not None:
                tk.Button(bar, text="移除", font=ui.FONTS["small"], fg=ui.COLORS["err"],
                          bg=panel, relief=tk.FLAT, bd=0, command=remove, cursor="hand2",
                          activebackground=panel, activeforeground=ui.COLORS["err"],
                          highlightthickness=0).pack(side=tk.RIGHT, padx=6)
            self._prop_widgets.append(bar)

        def row(label, widget_builder):
            line = tk.Frame(f, bg=panel)
            line.pack(fill=tk.X, pady=1, padx=(10, 6))
            tk.Label(line, text=label, bg=panel, width=11, anchor="w",
                     fg=ui.COLORS["text_dim"], font=ui.FONTS["small"]).pack(side=tk.LEFT)
            widget_builder(line)
            self._prop_widgets.append(line)

        def entry(parent, var):
            tk.Entry(parent, textvariable=var, width=16, bg=ui.COLORS["panel_alt"],
                     fg=ui.COLORS["text"], insertbackground=ui.COLORS["text"],
                     relief=tk.FLAT, bd=0, highlightthickness=0).pack(side=tk.LEFT, ipady=3)

        # ---- 基础
        section("物体")
        name_var = tk.StringVar(value=entity.get("name", ""))
        self._prop_vars[("name", None)] = name_var
        row("名称", lambda l: entry(l, name_var))

        tag_var = tk.StringVar(value=entity.get("tag", "Untagged"))
        self._prop_vars[("tag", None)] = tag_var
        row("标签", lambda l: tk.OptionMenu(l, tag_var, *COMMON_TAGS).pack(side=tk.LEFT))

        active_var = tk.BooleanVar(value=bool(entity.get("active", True)))
        self._prop_vars[("active", None)] = active_var
        row("激活", lambda l: tk.Checkbutton(l, variable=active_var, bg=panel,
                                             selectcolor=ui.COLORS["panel_alt"],
                                             activebackground=panel, bd=0,
                                             highlightthickness=0).pack(side=tk.LEFT))

        parent = pyu.entity_by_id(self.project, entity.get("parent"))
        candidates = ["(无)"] + [e.get("name", "") for e in pyu.entity_order(self.project)
                                 if e.get("id") != entity.get("id")]
        parent_var = tk.StringVar(value=parent.get("name") if parent else "(无)")
        self._prop_vars[("parent", None)] = parent_var
        row("父物体", lambda l: tk.OptionMenu(l, parent_var, *candidates).pack(side=tk.LEFT))

        # ---- 组件
        for comp_name in COMPONENT_ORDER:
            if comp_name == "Transform":
                comp = entity["components"].get("Transform")
            else:
                comp = entity["components"].get(comp_name)
            if comp is None:
                continue
            section("%s  ·  %s" % (component_title(comp_name), comp_name),
                    None if comp_name == "Transform" else (lambda c=comp_name: self.remove_component(c)))
            self._build_component_rows(entity, comp_name, comp, row)

        # ---- 操作
        section("操作")
        ops = tk.Frame(f, bg=panel)
        ops.pack(fill=tk.X, pady=6, padx=(10, 6))
        ui.flat_button(ops, "应用", self.apply_props, kind="primary").pack(side=tk.LEFT, padx=2)
        ui.flat_button(ops, "复制", self.duplicate_selection, kind="ghost").pack(side=tk.LEFT, padx=2)
        ui.flat_button(ops, "删除", self.delete_selection, kind="danger").pack(side=tk.LEFT, padx=2)
        self._prop_widgets.append(ops)
        ui.flat_button(f, "存为预制体", self.save_prefab, kind="ghost").pack(
            anchor="w", padx=(10, 6), pady=(0, 4))

        add_row = tk.Frame(f, bg=panel)
        add_row.pack(fill=tk.X, pady=(8, 10), padx=(10, 6))
        available = [c for c in ADDABLE_COMPONENTS if c not in entity["components"]]
        if available:
            add_var = tk.StringVar(value=available[0])
            tk.OptionMenu(add_row, add_var, *available).pack(side=tk.LEFT)
            ui.flat_button(add_row, "添加组件",
                           lambda: self.add_component(add_var.get()), kind="default").pack(
                side=tk.LEFT, padx=6)
            self._prop_vars["_add"] = add_var
        else:
            tk.Label(add_row, text="所有组件都已添加", bg=panel,
                     fg=ui.COLORS["text_muted"], font=ui.FONTS["small"]).pack(side=tk.LEFT)
        self._prop_widgets.append(add_row)
        self._update_stats()

    def _build_component_rows(self, entity, comp_name, comp, row):
        schema = COMPONENT_SCHEMAS[comp_name]["fields"]
        for key, spec in schema.items():
            value = comp.get(key, spec.get("default"))
            ftype = spec["type"]
            label = spec.get("hint", key)

            if ftype == "bool":
                var = tk.BooleanVar(value=bool(value))
                self._prop_vars[(comp_name, key)] = var
                row(label, lambda l, v=var: tk.Checkbutton(
                    l, variable=v, bg=ui.COLORS["panel"],
                    selectcolor=ui.COLORS["panel_alt"], activebackground=ui.COLORS["panel"],
                    bd=0, highlightthickness=0).pack(side=tk.LEFT))
                continue

            var = tk.StringVar()
            var.set("" if value is None else str(value))
            self._prop_vars[(comp_name, key)] = var

            if spec.get("multiline"):
                line = tk.Frame(self.prop_frame, bg=ui.COLORS["panel"])
                line.pack(fill=tk.X, pady=1, padx=(10, 6))
                tk.Label(line, text=label, bg=ui.COLORS["panel"], width=11, anchor="w",
                         fg=ui.COLORS["text_dim"], font=ui.FONTS["small"]).pack(
                    side=tk.LEFT, anchor="n")
                txt = tk.Text(line, height=4, width=24, font=ui.FONTS["mono_sm"],
                              bg=ui.COLORS["panel_alt"], fg=ui.COLORS["text"],
                              insertbackground=ui.COLORS["text"], relief=tk.FLAT, bd=0)
                txt.insert("1.0", str(value or ""))
                txt.pack(side=tk.LEFT)
                self._prop_vars[(comp_name, key)] = txt
                self._prop_widgets.append(line)
            elif ftype == "choice":
                row(label, lambda l, v=var, s=spec: tk.OptionMenu(l, v, *s["options"]).pack(side=tk.LEFT))
            elif ftype == "color":
                def mk_color(l, v=var, s=spec):
                    def pick():
                        _rgb, hexcolor = colorchooser.askcolor(
                            color=v.get() or s.get("default") or "#888888")
                        if hexcolor:
                            v.set(hexcolor)
                            swatch.config(bg=hexcolor, text=hexcolor)
                    current = v.get() or ""
                    swatch = tk.Button(l, text=current or "选择颜色",
                                       bg=current if current.startswith("#") else ui.COLORS["panel_alt"],
                                       fg=ui.COLORS["text"], width=9, relief=tk.FLAT,
                                       bd=0, command=pick, cursor="hand2",
                                       activebackground=ui.COLORS["panel_alt"])
                    swatch.pack(side=tk.LEFT)
                row(label, mk_color)
            elif ftype == "file":
                def mk_file(l, v=var):
                    def browse():
                        path = filedialog.askopenfilename(
                            title="选择图片 (PNG/GIF)",
                            filetypes=[("图片", "*.png *.gif"), ("所有文件", "*.*")])
                        if not path:
                            return
                        try:
                            asset = pyu.embed_image(self.project, path)
                        except Exception as exc:
                            messagebox.showerror("图片", str(exc))
                            return
                        v.set(asset)
                    tk.Entry(l, textvariable=v, width=13, bg=ui.COLORS["panel_alt"],
                             fg=ui.COLORS["text"], relief=tk.FLAT, bd=0,
                             highlightthickness=0).pack(side=tk.LEFT, ipady=3)
                    ui.flat_button(l, "浏览", browse, kind="ghost", padx=6, pady=2).pack(side=tk.LEFT)
                row(label, mk_file)
            elif ftype == "prefab":
                names = pyu.prefab_names(self.project) or [""]
                if var.get() not in names:
                    names = [var.get()] + names
                row(label, lambda l, v=var, n=names: tk.OptionMenu(l, v, *n).pack(side=tk.LEFT))
            elif ftype == "entity":
                names = ["(无)"] + [e.get("name", "") for e in pyu.entity_order(self.project)
                                    if e.get("id") != entity.get("id")]
                current = var.get() or "(无)"
                if current not in names:
                    names = [current] + names
                var.set(current)
                row(label, lambda l, v=var, n=names: tk.OptionMenu(l, v, *n).pack(side=tk.LEFT))
            else:
                row(label, lambda l, v=var: tk.Entry(
                    l, textvariable=v, width=16, bg=ui.COLORS["panel_alt"],
                    fg=ui.COLORS["text"], insertbackground=ui.COLORS["text"],
                    relief=tk.FLAT, bd=0, highlightthickness=0).pack(side=tk.LEFT, ipady=3))

    def apply_props(self):
        entity = self._find(self.selection)
        if entity is None:
            return
        self.push_undo()
        if ("name", None) in self._prop_vars:
            entity["name"] = pyu.unique_name(
                {"entities": [e for e in self.project["entities"] if e is not entity]},
                str(self._prop_vars[("name", None)].get()).strip() or "物体")
        if ("tag", None) in self._prop_vars:
            entity["tag"] = self._prop_vars[("tag", None)].get()
        if ("active", None) in self._prop_vars:
            entity["active"] = bool(self._prop_vars[("active", None)].get())
        if ("parent", None) in self._prop_vars:
            target = self._prop_vars[("parent", None)].get()
            try:
                if target in ("(无)", "", None):
                    pyu.set_parent(self.project, entity["id"], None)
                else:
                    for cand in self.project["entities"]:
                        if cand.get("name") == target:
                            pyu.set_parent(self.project, entity["id"], cand["id"])
                            break
            except ValueError as exc:
                messagebox.showerror("父子关系", str(exc))

        for key_item, var in list(self._prop_vars.items()):
            if not isinstance(key_item, tuple) or len(key_item) != 2:
                continue
            comp_name, key = key_item
            if comp_name in ("name", "tag", "active", "parent"):
                continue
            comp = entity["components"].get(comp_name)
            if comp is None:
                continue
            spec = COMPONENT_SCHEMAS[comp_name]["fields"].get(key)
            if spec is None:
                continue
            if isinstance(var, tk.Text):
                comp[key] = var.get("1.0", "end").rstrip("\n")
                continue
            raw = var.get()
            if isinstance(var, tk.BooleanVar):
                comp[key] = bool(raw)
                continue
            if spec["type"] in ("int", "float"):
                ok, fixed, err = validate_component(comp_name, {key: raw})
                if ok:
                    comp[key] = fixed[key]
                else:
                    messagebox.showerror("属性错误", err)
                    return
            elif spec["type"] == "entity":
                comp[key] = "" if raw == "(无)" else raw
            else:
                comp[key] = raw
        self._refresh_all()
        self._set_status("已应用属性")

    # ------------------------------------------------------------ 快捷键
    def _bind_shortcuts(self):
        self.root.bind("<Delete>", lambda e: self.delete_selection())
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-y>", lambda e: self.redo())
        self.root.bind("<Control-d>", lambda e: self.duplicate_selection())
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Escape>", lambda e: self._cancel_pending())
        self.root.bind("<Control-Key-1>", lambda e: self.set_mode("2d"))
        self.root.bind("<Control-Key-2>", lambda e: self.set_mode("3d"))
        for key, dx, dy in (("Left", -GRID, 0), ("Right", GRID, 0),
                            ("Up", 0, -GRID), ("Down", 0, GRID)):
            self.root.bind("<%s>" % key, lambda e, dx=dx, dy=dy: self.nudge(dx, dy))

    def _cancel_pending(self):
        self.pending_part = None
        self.parts_list.selection_clear(0, tk.END)


def launch_editor(file=None, splash=True):
    """启动编辑器：先播开屏动画，再显示主窗口。"""
    from . import splash as splash_mod

    root = tk.Tk()
    root.withdraw()
    app = EditorApp(root, file)

    if not splash or not splash_mod.splash_enabled():
        root.deiconify()
        return root

    def done():
        try:
            root.deiconify()
            root.lift()
            root.focus_force()
        except tk.TclError:
            pass

    splash_mod.show_splash(root, duration_ms=1500, on_done=done, version=__version__)
    root.mainloop()
    return root
