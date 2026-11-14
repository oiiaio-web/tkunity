# -*- coding: utf-8 -*-
"""场景几何与层级逻辑（纯函数，编辑器 / 运行时 / 导出器共用）。

约定：
- 实体的 Transform 坐标是相对父物体的局部坐标，左上角为原点；
- 父物体的 scale 会等比放大子物体的坐标与尺寸；
- 父物体的 rotation 不参与子物体位置计算（2D 简化，文档已注明）；
- 「绘制顺序」= 先按 Transform.layer 升序，同层再按层级深度优先顺序。
"""
from __future__ import annotations

from . import pyu

__all__ = [
    "world_transform", "collider_rect", "rect_of", "aabb_overlap",
    "aabb_penetration", "active_in_hierarchy", "draw_order", "hit_test",
    "camera_of", "animator_state", "center_of", "rotate_point",
]

_EPS = 1e-9


def world_transform(project, entity, _cache=None):
    """计算实体的世界变换（父级坐标 + 缩放累积）。

    返回 {"x","y","w","h","rotation","scale","layer","depth"}，均为绝对值。
    """
    if entity is None:
        return {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0,
                "rotation": 0.0, "scale": 1.0, "layer": 0, "depth": 0}
    if _cache is None:
        _cache = {}
    eid = entity.get("id")
    if eid in _cache:
        return _cache[eid]
    t = entity.get("components", {}).get("Transform", {})
    local = {
        "x": float(t.get("x", 0) or 0),
        "y": float(t.get("y", 0) or 0),
        "w": float(t.get("width", 0) or 0),
        "h": float(t.get("height", 0) or 0),
        "rotation": float(t.get("rotation", 0.0) or 0.0),
        "scale": float(t.get("scale", 1.0) or 1.0),
        "layer": int(t.get("layer", 0) or 0),
        "depth": 0,
    }
    if local["scale"] <= 0:
        local["scale"] = 0.01
    parent_id = entity.get("parent")
    parent = pyu.entity_by_id(project, parent_id) if parent_id is not None else None
    if parent is None:
        _cache[eid] = local
        return local
    p = world_transform(project, parent, _cache)
    out = {
        "x": p["x"] + local["x"] * p["scale"],
        "y": p["y"] + local["y"] * p["scale"],
        "w": local["w"] * p["scale"],
        "h": local["h"] * p["scale"],
        "rotation": local["rotation"],
        "scale": local["scale"] * p["scale"],
        "layer": local["layer"],
        "depth": p["depth"] + 1,
    }
    _cache[eid] = out
    return out


def rect_of(entity, project=None):
    """世界坐标下的包围盒 (x0, y0, x1, y1)。"""
    if project is None:
        t = entity.get("components", {}).get("Transform", {})
        s = float(t.get("scale", 1.0) or 1.0)
        x, y = float(t.get("x", 0) or 0), float(t.get("y", 0) or 0)
        w, h = float(t.get("width", 0) or 0) * s, float(t.get("height", 0) or 0) * s
    else:
        wt = world_transform(project, entity)
        x, y, w, h = wt["x"], wt["y"], wt["w"], wt["h"]
    return (x, y, x + w, y + h)


def collider_rect(entity, project=None):
    """碰撞体矩形；未配置 BoxCollider2D 时退化为 Transform 矩形。"""
    comps = entity.get("components", {})
    coll = comps.get("BoxCollider2D")
    if not coll:
        return rect_of(entity, project)
    if project is not None:
        wt = world_transform(project, entity)
        base_x, base_y, scale = wt["x"], wt["y"], wt["scale"]
        w = float(coll.get("width", 0) or 0) * scale or wt["w"]
        h = float(coll.get("height", 0) or 0) * scale or wt["h"]
        x = base_x + float(coll.get("offset_x", 0) or 0) * scale
        y = base_y + float(coll.get("offset_y", 0) or 0) * scale
        return (x, y, x + w, y + h)
    t = comps.get("Transform", {})
    w = float(coll.get("width", 0) or 0) or float(t.get("width", 0) or 0)
    h = float(coll.get("height", 0) or 0) or float(t.get("height", 0) or 0)
    x = float(t.get("x", 0) or 0) + float(coll.get("offset_x", 0) or 0)
    y = float(t.get("y", 0) or 0) + float(coll.get("offset_y", 0) or 0)
    return (x, y, x + w, y + h)


def aabb_overlap(a, b):
    return a[0] < b[2] - _EPS and b[0] < a[2] - _EPS and \
        a[1] < b[3] - _EPS and b[1] < a[3] - _EPS


def aabb_penetration(a, b):
    """最小平移向量 (dx, dy)：把 a 推出 b 所需的最短位移（只沿一个轴）。"""
    dx1 = b[2] - a[0]   # a 向右推出
    dx2 = a[2] - b[0]   # a 向左推出
    dy1 = b[3] - a[1]
    dy2 = a[3] - b[1]
    dx = dx1 if dx1 < dx2 else -dx2
    dy = dy1 if dy1 < dy2 else -dy2
    if abs(dx) <= abs(dy):
        return dx, 0.0
    return 0.0, dy


def active_in_hierarchy(project, entity):
    """自身与所有祖先都 active 才算激活。"""
    node = entity
    guard = 0
    while node is not None and guard < 256:
        if not node.get("active", True):
            return False
        parent_id = node.get("parent")
        node = pyu.entity_by_id(project, parent_id) if parent_id is not None else None
        guard += 1
    return True


def draw_order(project):
    """绘制顺序：layer 升序，同 layer 按层级深度优先顺序（父在前、子在后）。"""
    ordered = pyu.entity_order(project)
    cache = {}
    indexed = []
    for index, entity in enumerate(ordered):
        wt = world_transform(project, entity, cache)
        indexed.append((wt["layer"], index, entity))
    indexed.sort(key=lambda item: (item[0], item[1]))
    return [entity for _layer, _idx, entity in indexed]


def hit_test(project, x, y, accept=None):
    """返回该点最上层（绘制顺序最后）的激活实体 id。

    accept: 可选的过滤器，返回 False 的实体不参与命中（例如 2D 视图里排除 3D 物体）。
    """
    hit = None
    for entity in draw_order(project):
        if not active_in_hierarchy(project, entity):
            continue
        if accept is not None and not accept(entity):
            continue
        r = rect_of(entity, project)
        if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
            hit = entity
    return hit.get("id") if hit is not None else None


def center_of(project, entity):
    r = rect_of(entity, project)
    return ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0)


def camera_of(project):
    """返回第一个 Camera2D 组件所在的实体（没有则 None）。"""
    for entity in pyu.entity_order(project):
        if entity.get("components", {}).get("Camera2D"):
            return entity
    return None


def rotate_point(px, py, cx, cy, degrees):
    """绕 (cx, cy) 旋转 degrees 度（顺时针为正，与屏幕坐标一致）。"""
    if not degrees:
        return px, py
    import math
    rad = math.radians(degrees)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    dx, dy = px - cx, py - cy
    return (cx + dx * cos_a - dy * sin_a,
            cy + dx * sin_a + dy * cos_a)


def animator_state(anim, elapsed):
    """根据 Animator 组件计算绘制期偏移。

    返回 dict(dx, dy, drotation, dscale, opacity)：只影响绘制，不改数据。
    """
    state = {"dx": 0.0, "dy": 0.0, "drotation": 0.0, "dscale": 1.0, "opacity": 1.0}
    if not anim:
        return state
    if not anim.get("auto_play", True):
        return state
    import math
    effect = anim.get("effect", "none")
    speed = float(anim.get("speed", 1.0) or 0.0)
    amp = float(anim.get("amplitude", 1.0) or 0.0)
    t = elapsed * speed
    if effect == "spin":
        state["drotation"] = (t * 90.0) % 360.0
    elif effect == "pulse":
        state["dscale"] = 1.0 + 0.25 * amp * math.sin(t * 3.0)
    elif effect == "fade":
        state["opacity"] = max(0.0, min(1.0, 0.5 + 0.5 * math.sin(t * 2.0)))
    elif effect == "slide":
        state["dx"] = 20.0 * amp * math.sin(t * 2.0)
    elif effect == "float":
        state["dy"] = 12.0 * amp * math.sin(t * 2.5)
    return state
