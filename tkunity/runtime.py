# -*- coding: utf-8 -*-
"""tkinter 游戏运行时：读取 .pyu 项目字典，在 Canvas 上渲染并驱动行为。

特性（对齐 Unity 的工作方式）：
- 层级父子关系：子物体跟随父物体位移与缩放；
- 刚体物理：重力、速度、阻尼、弹性，静态/动态/运动学三种刚体；
- 碰撞体：AABB 碰撞，可设为触发器，进入时触发 on_collision；
- 生命周期脚本：on_start / on_update / on_tap / on_collision / on_destroy；
- 定时器与生成器（按预制体批量生成实例）；
- 摄像机跟随与缩放、动画补间、输入轴；
- 暂停 / 单步 / 重启，日志回调。

脚本用受限命名空间执行（桌面预览专用）；导出 APK 时只保留内置动作。

另外提供 3D 预览窗口 ``Scene3DPreview``（软件渲染，复用 three.py）。
"""
from __future__ import annotations

import copy
import math
import tkinter as tk

from . import pyu, three, ui, world
from .components import BUILTIN_ACTIONS

__all__ = ["Scene", "EntityRuntime", "run_preview", "Scene3DPreview",
           "TICK_MS", "execute_action_expression", "SAFE_BUILTINS"]

TICK_MS = 16
ACTION_SPEED = 240.0     # 内置移动动作的速度（px/s）
JUMP_SPEED = 430.0       # jump 动作的初速度（px/s）
GRAVITY_DEFAULT = 980.0

SAFE_BUILTINS = {
    "print": print, "abs": abs, "min": min, "max": max, "round": round,
    "int": int, "float": float, "str": str, "len": len, "range": range,
    "bool": bool, "sum": sum, "sorted": sorted, "pow": pow, "divmod": divmod,
}


class EntityRef(str):
    """``other`` 变量：既是实体名字符串（与 APK 行为一致），也保留 .get() 取字段。"""

    def __new__(cls, entity):
        name = "" if entity is None else str(entity.get("name", ""))
        obj = str.__new__(cls, name)
        obj.entity = entity
        return obj

    def get(self, key, default=None):
        if self.entity is None:
            return default
        return self.entity.get(key, default)

    def __getitem__(self, key):
        if self.entity is None:
            raise KeyError(key)
        return self.entity[key]


def _entity_ref(entity):
    return None if entity is None else EntityRef(entity)

_SAFE_GLOBALS = {"__builtins__": SAFE_BUILTINS, "math": math}


def _safe_ns(**extra):
    ns = dict(_SAFE_GLOBALS)
    ns.update(extra)
    return ns


def execute_action_expression(entity, action, scene=None):
    """执行一段动作表达式并回写 Transform（兼容旧 API）。

    注入变量：x / y / width / w / height / h / self / scene。
    返回 True 表示执行成功。
    """
    t = entity.get("components", {}).get("Transform", {})
    ns = _safe_ns(self=entity, scene=scene,
                  x=t.get("x", 0), y=t.get("y", 0),
                  width=t.get("width", 0), height=t.get("height", 0),
                  w=t.get("width", 0), h=t.get("height", 0))
    try:
        exec(action, ns)
    except Exception as exc:
        print("[tkunity] 表达式执行出错 %r: %s" % (action, exc))
        return False
    try:
        t["x"] = float(ns.get("x", t.get("x", 0)))
        t["y"] = float(ns.get("y", t.get("y", 0)))
        t["width"] = float(ns.get("width", t.get("width", 0)))
        t["height"] = float(ns.get("height", t.get("height", 0)))
    except (TypeError, ValueError):
        return False
    return True


class EntityRuntime(object):
    """单个实体的运行时状态（速度、计时器、生成器配额）。"""

    def __init__(self, scene, entity):
        self.scene = scene
        self.entity = entity
        self.id = entity.get("id")
        comps = entity.get("components", {})
        rb = comps.get("Rigidbody2D") or {}
        self.vx = float(rb.get("velocity_x", 0) or 0)
        self.vy = float(rb.get("velocity_y", 0) or 0)
        self.timer_elapsed = 0.0
        self.timer_done = False
        self.spawn_elapsed = 0.0
        self.started = False
        self.dead = False
        self.children = []      # Spawner 生成的实例 id
        self.touching = set()   # 触发器接触中的对方 id

    def sync_velocity(self):
        rb = self.entity.get("components", {}).get("Rigidbody2D")
        if rb is not None:
            rb["velocity_x"] = round(self.vx, 3)
            rb["velocity_y"] = round(self.vy, 3)


class Scene(object):
    """把一个项目字典渲染到 Tk Canvas 上，并驱动游戏循环。"""

    def __init__(self, master, project, tick_ms=TICK_MS, on_log=None,
                 copy_project=True, show_grid=True):
        self.master = master
        self._source = copy.deepcopy(project) if copy_project else project
        self.project = copy.deepcopy(project) if copy_project else project
        pyu.migrate(self.project)
        self.meta = self.project.get("meta", {})
        self.width = int(self.meta.get("scene_width", 960) or 960)
        self.height = int(self.meta.get("scene_height", 640) or 640)
        self.gravity = float(self.meta.get("gravity", GRAVITY_DEFAULT) or 0.0)
        self.time_scale = float(self.meta.get("time_scale", 1.0) or 1.0)
        self.tick_ms = tick_ms
        self.show_grid = show_grid

        self.canvas = tk.Canvas(master, width=self.width, height=self.height,
                                highlightthickness=0,
                                background=self.meta.get("background", "#1e1e2e"))
        self._photos = {}
        self.logs = []
        self.on_log = on_log
        self.runtimes = {}
        self.elapsed = 0.0
        self.dt = 0.0
        self.paused = False
        self._running = False
        self._tick_after = None
        self._contacts = set()
        self._keys = set()
        self._destroy_queue = []
        self.zoom = 1.0
        self._cam_x = self.width / 2.0
        self._cam_y = self.height / 2.0

        self.camera = world.camera_of(self.project)
        if self.camera is not None:
            self.zoom = float(self.camera["components"]["Camera2D"].get("zoom", 1.0) or 1.0)

        self._build()
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<KeyPress>", self._on_key_press)
        self.canvas.bind("<KeyRelease>", self._on_key_release)
        try:
            self.canvas.focus_set()
        except Exception:
            pass

    # ------------------------------------------------------------ 构建
    def _build(self):
        self.runtimes = {}
        for entity in pyu.entity_order(self.project):
            self.runtimes[entity.get("id")] = EntityRuntime(self, entity)

    def _active(self, rt):
        return not rt.dead and world.active_in_hierarchy(self.project, rt.entity)

    # ------------------------------------------------------------ 生命周期
    def start(self):
        if self._running:
            return
        self._running = True
        self.paused = False
        self.elapsed = 0.0
        for rt in self.runtimes.values():
            if self._active(rt) and not rt.started:
                rt.started = True
                self._run_script(rt, "on_start")
        self.render()
        self._tick()

    def stop(self):
        self._running = False
        if self._tick_after is not None:
            try:
                self.canvas.after_cancel(self._tick_after)
            except Exception:
                pass
            self._tick_after = None

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def step(self):
        """暂停状态下推进一帧（调试用）。"""
        self.dt = self.tick_ms / 1000.0 * self.time_scale
        self.elapsed += self.dt
        self.simulate()
        self.render()

    def restart(self):
        was_running = self._running
        self.stop()
        self.project = copy.deepcopy(self._source)
        pyu.migrate(self.project)
        self._photos = {}
        self.logs = []
        self.elapsed = 0.0
        self.dt = 0.0
        self._contacts = set()
        self._destroy_queue = []
        self.camera = world.camera_of(self.project)
        self._build()
        if was_running:
            self._running = False
            self.start()
        else:
            self.render()

    def _tick(self):
        if not self._running:
            return
        if not self.paused:
            self.dt = self.tick_ms / 1000.0 * self.time_scale
            self.elapsed += self.dt
            self.simulate()
            self.render()
        self._tick_after = self.canvas.after(self.tick_ms, self._tick)

    # ------------------------------------------------------------ 模拟
    def simulate(self):
        for rt in list(self.runtimes.values()):
            if not self._active(rt):
                continue
            self._integrate(rt)
            self._run_script(rt, "on_update")
            self._update_timer(rt)
            self._update_spawner(rt)
        self._collide()
        self._flush_destroy()
        self._update_camera()

    def _integrate(self, rt):
        comps = rt.entity.get("components", {})
        t = comps.setdefault("Transform", {})
        rb = comps.get("Rigidbody2D")
        body = (rb or {}).get("body_type", "dynamic")
        if rb is not None:
            if body == "static":
                return
            if body == "dynamic":
                gscale = float(rb.get("gravity_scale", 1.0) or 0.0)
                rt.vy += self.gravity * gscale * self.dt
                drag = float(rb.get("drag", 0.0) or 0.0)
                if drag > 0:
                    factor = max(0.0, 1.0 - drag * self.dt)
                    rt.vx *= factor
                    rt.vy *= factor
        if rt.vx or rt.vy:
            t["x"] = float(t.get("x", 0) or 0) + rt.vx * self.dt
            t["y"] = float(t.get("y", 0) or 0) + rt.vy * self.dt
            self._clamp_scene(rt, rb)
        rt.sync_velocity()

    def _clamp_scene(self, rt, rb):
        """没有碰撞体时，物体碰到场景边界反弹（保持旧版 demo 的行为）。"""
        if rb is not None and rt.entity.get("components", {}).get("BoxCollider2D"):
            return
        t = rt.entity["components"]["Transform"]
        s = float(t.get("scale", 1.0) or 1.0)
        w = float(t.get("width", 0) or 0) * s
        h = float(t.get("height", 0) or 0) * s
        bounce = float((rb or {}).get("bounce", 1.0) or 0.0)
        x, y = float(t.get("x", 0) or 0), float(t.get("y", 0) or 0)
        if x < 0:
            x = 0
            rt.vx = abs(rt.vx) * bounce
        elif x + w > self.width:
            x = self.width - w
            rt.vx = -abs(rt.vx) * bounce
        if y < 0:
            y = 0
            rt.vy = abs(rt.vy) * bounce
        elif y + h > self.height:
            y = self.height - h
            rt.vy = -abs(rt.vy) * bounce
        t["x"], t["y"] = x, y

    def _update_timer(self, rt):
        timer = rt.entity.get("components", {}).get("Timer")
        if not timer or rt.timer_done:
            return
        if not timer.get("auto_start", True):
            return
        interval = max(1.0, float(timer.get("interval_ms", 1000) or 1000)) / 1000.0
        rt.timer_elapsed += self.dt
        if rt.timer_elapsed >= interval:
            rt.timer_elapsed -= interval
            self._run_action(rt, timer.get("action", "none"))
            if not timer.get("repeat", True):
                rt.timer_done = True

    def _update_spawner(self, rt):
        spawner = rt.entity.get("components", {}).get("Spawner")
        if not spawner:
            return
        prefab = str(spawner.get("prefab", "") or "").strip()
        if not prefab:
            return
        interval = max(16.0, float(spawner.get("interval_ms", 1000) or 1000)) / 1000.0
        max_alive = int(spawner.get("max_alive", 0) or 0)
        rt.spawn_elapsed += self.dt
        if rt.spawn_elapsed < interval:
            return
        rt.spawn_elapsed -= interval
        alive = [cid for cid in rt.children
                 if cid in self.runtimes and not self.runtimes[cid].dead]
        rt.children = alive
        if max_alive and len(alive) >= max_alive:
            return
        wt = world.world_transform(self.project, rt.entity)
        x = wt["x"] + float(spawner.get("offset_x", 0) or 0)
        y = wt["y"] + float(spawner.get("offset_y", 0) or 0)
        child = self.spawn(prefab, x, y)
        if child is not None:
            rt.children.append(child.get("id"))

    # ------------------------------------------------------------ 碰撞
    def _collide(self):
        entries = []
        for rt in self.runtimes.values():
            if not self._active(rt):
                continue
            coll = rt.entity.get("components", {}).get("BoxCollider2D")
            if coll is None:
                continue
            entries.append((rt, world.collider_rect(rt.entity, self.project),
                            bool(coll.get("is_trigger", False))))
        seen = set()
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                rt_a, rect_a, trig_a = entries[i]
                rt_b, rect_b, trig_b = entries[j]
                if not world.aabb_overlap(rect_a, rect_b):
                    continue
                key = (rt_a.id, rt_b.id)
                seen.add(key)
                if trig_a or trig_b:
                    if rt_b.id not in rt_a.touching:
                        rt_a.touching.add(rt_b.id)
                        self._run_script(rt_a, "on_collision", {"other": rt_b.entity})
                    if rt_a.id not in rt_b.touching:
                        rt_b.touching.add(rt_a.id)
                        self._run_script(rt_b, "on_collision", {"other": rt_a.entity})
                else:
                    self._resolve(rt_a, rt_b)
        for key in list(self._contacts - seen):
            for rt_id, other_id in (key, (key[1], key[0])):
                rt = self.runtimes.get(rt_id)
                if rt:
                    rt.touching.discard(other_id)
        self._contacts = seen

    def _resolve(self, rt_a, rt_b):
        body_a = (rt_a.entity.get("components", {}).get("Rigidbody2D") or {}).get("body_type", "static")
        body_b = (rt_b.entity.get("components", {}).get("Rigidbody2D") or {}).get("body_type", "static")
        if body_a == "static" and body_b == "static":
            return
        rect_a = world.collider_rect(rt_a.entity, self.project)
        rect_b = world.collider_rect(rt_b.entity, self.project)
        dx, dy = world.aabb_penetration(rect_a, rect_b)
        a_moves = body_a == "dynamic"
        b_moves = body_b == "dynamic"
        if not a_moves and not b_moves:
            return
        if a_moves and not b_moves:
            self._shift(rt_a, dx, dy)
            self._bounce_axis(rt_a, dx, dy)
        elif b_moves and not a_moves:
            self._shift(rt_b, -dx, -dy)
            self._bounce_axis(rt_b, -dx, -dy)
        else:
            self._shift(rt_a, dx / 2.0, dy / 2.0)
            self._shift(rt_b, -dx / 2.0, -dy / 2.0)
            self._bounce_axis(rt_a, dx, dy)
            self._bounce_axis(rt_b, -dx, -dy)

    def _shift(self, rt, dx, dy):
        t = rt.entity["components"]["Transform"]
        t["x"] = float(t.get("x", 0) or 0) + float(dx)
        t["y"] = float(t.get("y", 0) or 0) + float(dy)

    def _bounce_axis(self, rt, dx, dy):
        rb = rt.entity.get("components", {}).get("Rigidbody2D") or {}
        bounce = float(rb.get("bounce", 1.0) or 0.0)
        if abs(dx) > abs(dy):
            rt.vx = -rt.vx * bounce
        else:
            rt.vy = -rt.vy * bounce
        rt.sync_velocity()

    # ------------------------------------------------------------ 动作 / 脚本
    def _run_action(self, rt, action):
        action = (action or "none").strip()
        if not action or action == "none" or rt.dead:
            return
        low = action.lower()
        if low.startswith("spawn:"):
            name = action.split(":", 1)[1].strip()
            t = rt.entity.get("components", {}).get("Transform", {})
            self.spawn(name, float(t.get("x", 0) or 0), float(t.get("y", 0) or 0))
            return
        if low == "move-left":
            rt.vx, rt.vy = -ACTION_SPEED, 0.0
        elif low == "move-right":
            rt.vx, rt.vy = ACTION_SPEED, 0.0
        elif low == "move-up":
            rt.vx, rt.vy = 0.0, -ACTION_SPEED
        elif low == "move-down":
            rt.vx, rt.vy = 0.0, ACTION_SPEED
        elif low == "jump":
            rt.vy = -JUMP_SPEED
        elif low == "bounce":
            if abs(rt.vx) < 1e-6 and abs(rt.vy) < 1e-6:
                rt.vx, rt.vy = ACTION_SPEED, ACTION_SPEED
        elif low == "stop":
            rt.vx = rt.vy = 0.0
        elif low == "destroy":
            self.destroy(rt.entity)
            return
        elif low == "toggle":
            rt.entity["active"] = not rt.entity.get("active", True)
            return
        elif low == "restart":
            self.restart()
            return
        elif low.startswith("print("):
            code = action
            self._exec(rt, code)
            return
        else:
            self._exec(rt, action)
            return
        rt.sync_velocity()

    def _run_script(self, rt, hook, extra=None):
        script = rt.entity.get("components", {}).get("Script")
        if not script:
            return
        code = (script.get(hook) or "").strip()
        if not code:
            return
        self._exec(rt, code, extra)

    def _exec(self, rt, code, extra=None):
        """在受限命名空间中执行代码，并把结果写回实体。"""
        comps = rt.entity.get("components", {})
        t = comps.get("Transform", {})
        ns = _safe_ns(
            self=rt.entity, scene=self, entity=rt.entity,
            dt=self.dt, time=self.elapsed,
            x=float(t.get("x", 0) or 0), y=float(t.get("y", 0) or 0),
            width=float(t.get("width", 0) or 0), height=float(t.get("height", 0) or 0),
            w=float(t.get("width", 0) or 0), h=float(t.get("height", 0) or 0),
            vx=rt.vx, vy=rt.vy,
            rotation=float(t.get("rotation", 0) or 0),
            scale=float(t.get("scale", 1.0) or 1.0),
            log=self.log, find=self.find, spawn=self.spawn, destroy=self.destroy,
            other=_entity_ref((extra or {}).get("other")),
            name=rt.entity.get("name", ""), tag=rt.entity.get("tag", "Untagged"),
        )
        try:
            exec(compile(code, "<tkunity-script>", "exec"), ns)
        except Exception as exc:
            self.log("[脚本错误] %s: %s" % (rt.entity.get("name", "?"), exc))
            return False
        try:
            t["x"] = float(ns.get("x", t.get("x", 0)))
            t["y"] = float(ns.get("y", t.get("y", 0)))
            t["width"] = float(ns.get("width", t.get("width", 0)))
            t["height"] = float(ns.get("height", t.get("height", 0)))
            t["rotation"] = float(ns.get("rotation", t.get("rotation", 0)))
            t["scale"] = float(ns.get("scale", t.get("scale", 1.0)))
            rt.vx = float(ns.get("vx", rt.vx))
            rt.vy = float(ns.get("vy", rt.vy))
        except (TypeError, ValueError):
            return False
        rt.sync_velocity()
        return True

    # ------------------------------------------------------------ 场景操作
    def find(self, name):
        """按名字查找实体字典（找不到返回 None）。"""
        for entity in self.project.get("entities", []):
            if entity.get("name") == name:
                return entity
        return None

    def spawn(self, prefab_name, x=None, y=None, parent=None):
        """实例化预制体（运行期），返回新实体字典；失败返回 None。"""
        try:
            entity = pyu.instantiate_prefab(self.project, prefab_name, x, y, parent)
        except Exception as exc:
            self.log("[生成失败] %s" % exc)
            return None
        rt = EntityRuntime(self, entity)
        self.runtimes[entity["id"]] = rt
        rt.started = True
        self._run_script(rt, "on_start")
        return entity

    def destroy(self, target):
        """销毁实体（延迟到本帧末执行，避免遍历中修改）。"""
        eid = target.get("id") if isinstance(target, dict) else getattr(target, "id", None)
        if eid is None:
            return
        rt = self.runtimes.get(eid)
        if rt is None or rt.dead:
            return
        rt.dead = True
        self._destroy_queue.append(eid)

    def _flush_destroy(self):
        while self._destroy_queue:
            eid = self._destroy_queue.pop(0)
            rt = self.runtimes.get(eid)
            if rt is None:
                continue
            self._run_script(rt, "on_destroy")
            for rt2 in self.runtimes.values():
                if rt2 is not rt and rt2.entity.get("parent") == eid:
                    rt2.entity["parent"] = rt.entity.get("parent")
            self.project["entities"] = [e for e in self.project["entities"]
                                        if e.get("id") != eid]
            self.runtimes.pop(eid, None)

    def log(self, message):
        """写一条运行日志（编辑器控制台会显示）。"""
        text = str(message)
        self.logs.append(text)
        if len(self.logs) > 200:
            del self.logs[:-200]
        if self.on_log is not None:
            try:
                self.on_log(text)
            except Exception:
                pass

    # ------------------------------------------------------------ 输入
    def _on_key_press(self, event):
        self._keys.add((event.keysym or "").lower())

    def _on_key_release(self, event):
        self._keys.discard((event.keysym or "").lower())

    def axis(self, name="horizontal"):
        """读取输入轴：horizontal / vertical，返回 -1 / 0 / 1。"""
        keys = self._keys
        if name in ("horizontal", "x"):
            return (1 if keys & {"right", "d"} else 0) - (1 if keys & {"left", "a"} else 0)
        return (1 if keys & {"down", "s"} else 0) - (1 if keys & {"up", "w"} else 0)

    def _on_click(self, event):
        wx = (event.x - self.width / 2.0) / self.zoom + self._cam_x
        wy = (event.y - self.height / 2.0) / self.zoom + self._cam_y
        eid = world.hit_test(self.project, wx, wy)
        if eid is None:
            return
        rt = self.runtimes.get(eid)
        if rt is None:
            return
        self.canvas.focus_set()
        tap = rt.entity.get("components", {}).get("TapHandler")
        if tap:
            self._run_action(rt, tap.get("action", "none"))
        self._run_script(rt, "on_tap", {"other": None})

    # ------------------------------------------------------------ 摄像机
    def _update_camera(self):
        cam = self.camera
        if cam is None:
            return
        comp = cam["components"]["Camera2D"]
        self.zoom = max(0.1, float(comp.get("zoom", 1.0) or 1.0))
        target_name = str(comp.get("follow", "") or "").strip()
        if not target_name:
            return
        target = self.find(target_name)
        if target is None or target.get("id") not in self.runtimes:
            return
        cx, cy = world.center_of(self.project, target)
        smooth = max(0.0, min(1.0, float(comp.get("smooth", 0.15) or 0.0)))
        k = 1.0 - smooth if smooth < 1.0 else 1.0
        self._cam_x += (cx - self._cam_x) * k
        self._cam_y += (cy - self._cam_y) * k

    # ------------------------------------------------------------ 渲染
    def _sx(self, wx):
        return (wx - self._cam_x) * self.zoom + self.width / 2.0

    def _sy(self, wy):
        return (wy - self._cam_y) * self.zoom + self.height / 2.0

    def _sl(self, wl):
        return wl * self.zoom

    def render(self):
        c = self.canvas
        c.delete("all")
        c.configure(background=self.meta.get("background", "#1e1e2e"))
        cache = {}
        if self.show_grid:
            self._draw_grid()
        for entity in world.draw_order(self.project):
            if not world.active_in_hierarchy(self.project, entity):
                continue
            rt = self.runtimes.get(entity.get("id"))
            self._draw_entity(entity, rt, cache)

    def _draw_grid(self):
        step = 40
        x0 = self._sx(0)
        y0 = self._sy(0)
        x1 = self._sx(self.width)
        y1 = self._sy(self.height)
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=self.meta.get("background", "#1e1e2e"),
                                     outline="", tags=("scene",))
        for gx in range(0, self.width + 1, step):
            sx = self._sx(gx)
            self.canvas.create_line(sx, y0, sx, y1, fill="#33333a", tags=("grid",))
        for gy in range(0, self.height + 1, step):
            sy = self._sy(gy)
            self.canvas.create_line(x0, sy, x1, sy, fill="#33333a", tags=("grid",))

    def _get_photo(self, asset_name):
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

    def _draw_entity(self, entity, rt, cache):
        comps = entity.get("components", {})
        t = comps.get("Transform", {})
        wt = world.world_transform(self.project, entity, cache)
        anim = world.animator_state(comps.get("Animator"), self.elapsed)
        scale = anim["dscale"]
        x = wt["x"] + anim["dx"]
        y = wt["y"] + anim["dy"]
        w = wt["w"] * scale
        h = wt["h"] * scale
        rotation = wt["rotation"] + anim["drotation"]
        cx, cy = x + w / 2.0, y + h / 2.0

        sx, sy = self._sx(x), self._sy(y)
        sw, sh = self._sl(w), self._sl(h)
        sprite = comps.get("Sprite")
        if sprite is not None:
            opacity = float(sprite.get("opacity", 1.0) or 0.0) * anim["opacity"]
            self._draw_sprite(sprite, sx, sy, sw, sh, rotation, opacity, cx, cy)
        label = comps.get("Label")
        if label and label.get("text"):
            align = label.get("align", "center")
            anchor = {"center": "center", "left": "w", "right": "e"}.get(align, "center")
            lx = {"center": sx + sw / 2.0, "left": sx + 2, "right": sx + sw - 2}.get(align, sx + sw / 2.0)
            ly = sy + sh / 2.0
            if rotation:
                lx, ly = world.rotate_point(lx, ly, self._sx(cx), self._sy(cy), rotation)
            font = ("Helvetica", max(1, int(float(label.get("font_size", 18) or 18) * self.zoom)),
                    "bold" if label.get("bold") else "normal")
            self.canvas.create_text(lx, ly, text=str(label.get("text", "")), anchor=anchor,
                                    font=font, fill=label.get("color", "#000000"),
                                    tags=("ent%d" % entity.get("id"),))

    def _draw_sprite(self, sprite, sx, sy, sw, sh, rotation, opacity, world_cx, world_cy):
        shape = sprite.get("shape", "rect")
        fill = sprite.get("fill", "")
        outline = sprite.get("outline", "")
        eid = None
        if shape == "image":
            photo = self._get_photo(str(sprite.get("image", "") or ""))
            if photo is not None:
                self.canvas.create_image(sx + sw / 2.0, sy + sh / 2.0, image=photo,
                                         tags=("image",))
                return
            if not fill:
                return
        if shape == "oval" and not rotation:
            self.canvas.create_oval(sx, sy, sx + sw, sy + sh, fill=fill or "",
                                    outline=outline or "", width=2)
            return
        if rotation:
            pts = []
            for px, py in ((sx, sy), (sx + sw, sy), (sx + sw, sy + sh), (sx, sy + sh)):
                pts.extend(world.rotate_point(px, py, self._sx(world_cx), self._sy(world_cy), rotation))
            self.canvas.create_polygon(*pts, fill=fill or "", outline=outline or "", width=2)
            return
        self.canvas.create_rectangle(sx, sy, sx + sw, sy + sh, fill=fill or "",
                                     outline=outline or "", width=2)


def run_preview(master, project, **kwargs):
    """在给定 master（Toplevel/Tk）上启动一局游戏，返回 Scene。"""
    scene = Scene(master, project, **kwargs)
    scene.canvas.pack(fill="both", expand=True)
    scene.start()
    return scene


class Scene3DPreview(object):
    """3D 场景的桌面预览：软件渲染 + 可选的自动环绕。"""

    def __init__(self, master, project, width=900, height=640, auto_orbit=True,
                 fps=30, on_log=None):
        self.master = master
        self.project = project
        self.width = width
        self.height = height
        self.camera = three.camera_from_project(project, width, height)
        self.auto_orbit = bool(auto_orbit)
        self.fps = max(5, int(fps))
        self.on_log = on_log
        self.running = False
        self.elapsed = 0.0
        self.canvas = tk.Canvas(master, width=width, height=height,
                                bg=ui.COLORS["canvas_bg"], highlightthickness=0)
        self._after = None

    @property
    def has_3d(self):
        return three.has_3d(self.project)

    def start(self):
        if self.running:
            return
        self.running = True
        self._frame()

    def stop(self):
        self.running = False
        if self._after is not None:
            try:
                self.canvas.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def restart(self):
        self.camera = three.camera_from_project(self.project, self.width, self.height)
        self.elapsed = 0.0
        self._render()

    def _render(self):
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        three.render_scene(self.canvas, self.project, self.camera, w, h)

    def _frame(self):
        if not self.running:
            return
        self.elapsed += 1.0 / self.fps
        if self.auto_orbit:
            self.camera.yaw = (self.camera.yaw + 1.2) % 360.0
        for entity in self.project.get("entities", []):
            anim = entity.get("components", {}).get("Animator")
            if anim and anim.get("auto_play", True) and anim.get("effect") == "spin":
                t3 = entity.get("components", {}).get("Transform3D")
                if t3 is not None:
                    speed = float(anim.get("speed", 1.0) or 1.0)
                    t3["ry"] = (float(t3.get("ry", 0) or 0) + 90.0 * speed / self.fps) % 360.0
        try:
            self._render()
        except tk.TclError:
            return
        self._after = self.canvas.after(int(1000 / self.fps), self._frame)
