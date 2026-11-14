# -*- coding: utf-8 -*-
"""编辑器里的 3D 视口（纯 tkinter Canvas + 软件渲染，无第三方依赖）。

交互：
    左键拖动空白处      环绕旋转
    Shift + 左键拖动    平移视角
    滚轮                缩放
    左键点物体          选中
    左键拖动已选中物体  在地面（XZ 平面）上移动
    双击物体            聚焦
"""
from __future__ import annotations

import math
import tkinter as tk

from . import three, ui

__all__ = ["Scene3DView"]


class Scene3DView(tk.Frame):
    def __init__(self, master, on_select=None, on_change=None, on_status=None,
                 width=820, height=620):
        tk.Frame.__init__(self, master, bg=ui.COLORS["canvas_bg"])
        self.on_select = on_select
        self.on_change = on_change
        self.on_status = on_status
        self.project = {"entities": []}
        self.selection = None
        self.camera = three.Camera()
        self._drag = None
        self._auto_fit_done = False

        self.canvas = tk.Canvas(self, bg=ui.COLORS["canvas_bg"], highlightthickness=0,
                                width=width, height=height)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._zoom(1.1))
        self.canvas.bind("<Button-5>", lambda e: self._zoom(1 / 1.1))
        self.canvas.bind("<Shift-Button-1>", self._on_shift_press)
        self.canvas.bind("<Configure>", lambda e: self._redraw())

    # ------------------------------------------------------------ 对外接口
    def set_project(self, project):
        self.project = project
        if not self._auto_fit_done:
            self.fit()
            self._auto_fit_done = True
        self._redraw()

    def set_selection(self, eid):
        self.selection = eid
        self._redraw()

    def reset_view(self):
        self.camera = three.Camera()
        self._redraw()

    def fit(self):
        """让相机框住所有 3D 物体。"""
        xs, ys, zs = [], [], []
        for entity in self.project.get("entities", []):
            if not entity.get("components", {}).get("Mesh3D"):
                continue
            tf = three.transform3d_of(entity)
            xs.append(tf["x"])
            ys.append(tf["y"])
            zs.append(tf["z"])
        if not xs:
            self.camera = three.Camera()
            return
        center = (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
        spread = max(1.0, max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)))
        self.camera.target = center
        self.camera.distance = max(2.5, spread * 2.4)
        self._redraw()

    def focus_on(self, eid):
        entity = self._find(eid)
        if entity is None:
            return
        tf = three.transform3d_of(entity)
        self.camera.target = (tf["x"], tf["y"], tf["z"])
        self._redraw()

    # ------------------------------------------------------------ 绘制
    def _size(self):
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        return width, height

    def _redraw(self):
        try:
            width, height = self._size()
            three.render_scene(self.canvas, self.project, self.camera, width, height,
                               selected=self.selection)
            self._draw_hud(width, height)
        except tk.TclError:
            pass

    def _draw_hud(self, width, height):
        c = self.canvas
        count = sum(1 for e in self.project.get("entities", [])
                    if e.get("components", {}).get("Mesh3D"))
        c.create_text(12, 12, anchor="nw", fill=ui.COLORS["text_dim"],
                      font=("Segoe UI", 9),
                      text="3D 场景 · %d 个物体" % count)
        c.create_text(width - 12, 12, anchor="ne", fill=ui.COLORS["text_muted"],
                      font=("Segoe UI", 8),
                      text="yaw %.0f°  pitch %.0f°  距离 %.1f"
                           % (self.camera.yaw, self.camera.pitch, self.camera.distance))
        c.create_text(12, height - 12, anchor="sw", fill=ui.COLORS["text_muted"],
                      font=("Segoe UI", 8),
                      text="左键环绕 · Shift+左键平移 · 滚轮缩放 · 拖动选中物体移动")

    # ------------------------------------------------------------ 交互
    def _find(self, eid):
        for entity in self.project.get("entities", []):
            if entity.get("id") == eid:
                return entity
        return None

    def _pick(self, x, y):
        width, height = self._size()
        return three.pick(self.project, self.camera, width, height, x, y)

    def _on_shift_press(self, event):
        self._drag = {"mode": "pan", "x": event.x, "y": event.y}
        return "break"

    def _on_press(self, event):
        width, height = self._size()
        eid = self._pick(event.x, event.y)
        if eid is not None:
            if self.on_select is not None:
                self.on_select(eid)
            entity = self._find(eid)
            tf = three.transform3d_of(entity) if entity else None
            self._drag = {"mode": "move", "x": event.x, "y": event.y, "eid": eid,
                          "ox": tf["x"] if tf else 0.0, "oz": tf["z"] if tf else 0.0}
            if self.on_status is not None:
                self.on_status("已选中「%s」" % (entity.get("name") if entity else "?"))
            return "break"
        self._drag = {"mode": "orbit", "x": event.x, "y": event.y}
        return "break"

    def _on_drag(self, event):
        if not self._drag:
            return "break"
        drag = self._drag
        dx = event.x - drag["x"]
        dy = event.y - drag["y"]
        drag["x"], drag["y"] = event.x, event.y
        if drag["mode"] == "orbit":
            self.camera.orbit(-dx * 0.4, dy * 0.3)
            self._redraw()
        elif drag["mode"] == "pan":
            self.camera.pan(dx, dy)
            self._redraw()
        elif drag["mode"] == "move":
            self._move_entity(drag, dx, dy)
        return "break"

    def _move_entity(self, drag, dx, dy):
        entity = self._find(drag["eid"])
        if entity is None:
            return
        t3 = entity.get("components", {}).get("Transform3D")
        if t3 is None:
            return
        width, height = self._size()
        factor = (2.0 * self.camera.distance
                  * math.tan(math.radians(self.camera.fov / 2.0)) / max(1, height))
        eye, forward, right, up = self.camera.basis()
        flat = (forward[0], 0.0, forward[2])
        length = math.sqrt(flat[0] ** 2 + flat[2] ** 2) or 1.0
        wx = (right[0] * dx + flat[0] / length * dy) * factor
        wz = (right[2] * dx + flat[2] / length * dy) * factor
        t3["x"] = round(float(t3.get("x", 0) or 0) + wx, 2)
        t3["z"] = round(float(t3.get("z", 0) or 0) + wz, 2)
        self._redraw()
        if self.on_change is not None:
            self.on_change()

    def _on_release(self, event):
        self._drag = None
        return "break"

    def _on_double(self, event):
        eid = self._pick(event.x, event.y)
        if eid is not None:
            self.focus_on(eid)
        return "break"

    def _on_wheel(self, event):
        self._zoom(1.1 if event.delta > 0 else 1 / 1.1)
        return "break"

    def _zoom(self, factor):
        self.camera.zoom(factor)
        self._redraw()
