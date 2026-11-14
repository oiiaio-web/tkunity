# -*- coding: utf-8 -*-
"""开屏动画（纯 tkinter 绘制，无图片素材、无第三方依赖）。

效果：深色渐变背景 + 一个旋转的线框立方体 + 标题淡入 + 进度条，
约 1.6 秒后自动关闭；点击窗口或按 Esc 可跳过。
"""
from __future__ import annotations

import math
import time
import tkinter as tk

from . import three
from . import ui

__all__ = ["show_splash", "SplashScreen", "splash_enabled"]

DEFAULT_DURATION_MS = 1600


def splash_enabled(argv=None, env=None):
    """是否显示开屏：--no-splash 参数或 TKUNITY_NO_SPLASH 环境变量可关闭。"""
    import os
    import sys
    argv = sys.argv if argv is None else argv
    env = os.environ if env is None else env
    if "--no-splash" in argv or "-no-splash" in argv:
        return False
    if str(env.get("TKUNITY_NO_SPLASH", "")).strip() in ("1", "true", "yes", "on"):
        return False
    return True


def _mix(color_a, color_b, t):
    ra, ga, ba = three.hex_to_rgb(color_a)
    rb, gb, bb = three.hex_to_rgb(color_b)
    t = max(0.0, min(1.0, t))
    return three.rgb_to_hex((ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t))


class SplashScreen(object):
    """独立的无边框开屏窗口。"""

    def __init__(self, root, duration_ms=DEFAULT_DURATION_MS, on_done=None,
                 width=560, height=340, version=None):
        self.root = root
        self.duration = max(200, int(duration_ms))
        self.on_done = on_done
        self.width = width
        self.height = height
        self.version = version
        self.start = time.time()
        self.closed = False

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=ui.COLORS["bg"])
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 40)
        self.win.geometry("%dx%d+%d+%d" % (width, height, x, y))

        self.canvas = tk.Canvas(self.win, width=width, height=height,
                                bg=ui.COLORS["bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.win.bind("<Button-1>", lambda e: self.close())
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.bind("<Key>", lambda e: self.close())
        try:
            self.win.focus_force()
        except tk.TclError:
            pass

        self._draw(0.0)
        self.win.after(16, self._tick)

    # ------------------------------------------------------------ 动画
    def _tick(self):
        if self.closed:
            return
        progress = min(1.0, (time.time() - self.start) * 1000.0 / self.duration)
        try:
            self._draw(progress)
        except tk.TclError:
            return
        if progress >= 1.0:
            self.close()
        else:
            self.win.after(16, self._tick)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if self.on_done is not None:
            self.on_done()

    # ------------------------------------------------------------ 绘制
    def _draw(self, progress):
        c = self.canvas
        c.delete("all")
        w, h = self.width, self.height
        # 背景渐变
        bands = 24
        for i in range(bands):
            t = i / float(bands - 1)
            color = _mix("#0d0d15", "#1a1a2b", t)
            c.create_rectangle(0, h * i / bands, w, h * (i + 1) / bands + 1,
                               fill=color, outline=color)
        # 顶部说明
        appear = min(1.0, max(0.0, (progress - 0.05) / 0.35))
        _fade = _mix(ui.COLORS["bg"], ui.COLORS["text"], appear)

        # 旋转立方体
        cube = three.MESHES["cube"]
        angle_y = 20.0 + progress * 520.0
        angle_x = 18.0 + progress * 40.0
        scale = 1.05 * (0.75 + 0.25 * min(1.0, progress * 3.0))
        center_x = w * 0.5
        center_y = h * 0.46
        view = three.View(three.Camera(yaw=0, pitch=0, distance=3.3,
                                       target=(0, 0, 0), fov=48), w, h)
        projected = []
        world = []
        for vx, vy, vz in cube.vertices:
            px, py, pz = three.rotate_xyz((vx * scale, vy * scale, vz * scale),
                                          angle_x, angle_y, 0.0)
            # 平移到画面中心：投影前把相机目标平移，比手动偏移更自然
            world.append((px, py, pz))
            projected.append(view.project((px, py, pz)))

        faces = sorted(cube.faces,
                       key=lambda f: -sum((projected[i][2] if projected[i] else 0) for i in f))
        accent = ui.COLORS["accent"]
        for face in faces:
            if any(projected[i] is None for i in face):
                continue
            pts = []
            for i in face:
                pts.extend(projected[i][:2])
            factor = three._face_shade(world, face) * 0.9
            color = _mix("#0d0d15", accent, min(1.0, factor) * 0.85 + 0.1 * appear)
            c.create_polygon(*pts, fill="", outline=color, width=1)
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                     (0, 4), (1, 5), (2, 6), (3, 7)):
            if projected[a] and projected[b]:
                c.create_line(projected[a][0], projected[a][1],
                              projected[b][0], projected[b][1],
                              fill=_mix(accent, "#ffffff", 0.15), width=2)

        # 标题
        title = "tkunity"
        c.create_text(center_x, h * 0.72, text=title, fill=_fade,
                      font=("Segoe UI", int(26 + 3 * appear), "bold"))
        subtitle = "Unity 风格 2D / 3D 游戏编辑器"
        c.create_text(center_x, h * 0.72 + 34, text=subtitle,
                      fill=_mix(ui.COLORS["bg"], ui.COLORS["text_dim"], appear),
                      font=("Segoe UI", 10))

        # 进度条
        bar_w, bar_h = int(w * 0.46), 4
        bar_x0 = (w - bar_w) // 2
        bar_y = int(h * 0.86)
        c.create_rectangle(bar_x0, bar_y, bar_x0 + bar_w, bar_y + bar_h,
                           fill=ui.COLORS["panel_alt"], outline="")
        filled = int(bar_w * max(0.02, progress))
        c.create_rectangle(bar_x0, bar_y, bar_x0 + filled, bar_y + bar_h,
                           fill=ui.COLORS["accent"], outline="")

        # 版本 & 跳过提示
        if self.version:
            c.create_text(w - 12, h - 12, text="v%s" % self.version, anchor="se",
                          fill=ui.COLORS["text_muted"], font=("Segoe UI", 8))
        c.create_text(12, h - 12, text="点击 / Esc 跳过", anchor="sw",
                      fill=_mix("#0d0d15", ui.COLORS["text_muted"], appear * 0.9),
                      font=("Segoe UI", 8))


def show_splash(root, duration_ms=DEFAULT_DURATION_MS, on_done=None, version=None):
    """显示开屏动画；无法创建窗口时直接回调，不影响主流程。"""
    try:
        return SplashScreen(root, duration_ms=duration_ms, on_done=on_done, version=version)
    except Exception:
        if on_done is not None:
            on_done()
        return None
