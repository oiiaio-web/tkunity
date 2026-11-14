# -*- coding: utf-8 -*-
"""纯标准库的软件 3D 渲染核心（只用 math + tkinter Canvas，零第三方依赖）。

内容：
- 向量 / 旋转矩阵 / 透视投影等数学工具；
- 内置网格：cube / sphere / plane / pyramid / cylinder；
- 画家算法渲染：按面深度排序、方向光着色、可选线框；
- 拾取：把面投影成多边形做点在多边形内判断。

坐标约定（与 Unity 类似）：
- 右手系，+X 向右、+Y 向上、+Z 向前（朝向观察者）；
- 旋转单位为角度，先绕 X、再绕 Y、最后绕 Z（Euler XYZ）。
"""
from __future__ import annotations

import math

__all__ = [
    "MESHES", "Mesh", "Camera", "View", "mesh_of", "camera_from_project",
    "has_3d", "transform3d_of", "entity_vertices", "render_scene", "pick",
    "hex_to_rgb", "rgb_to_hex", "shade", "project_point", "screen_radius",
    "SIZES",
]

# 3D 零件的默认缩放（世界单位）
SIZES = {
    "cube": 1.0,
    "sphere": 1.0,
    "plane": 1.0,
    "pyramid": 1.2,
    "cylinder": 1.0,
}

SHAPE_LABELS = {
    "cube": "立方体",
    "sphere": "球体",
    "plane": "平面",
    "pyramid": "棱锥",
    "cylinder": "圆柱",
}


class Mesh(object):
    """顶点 + 面（顶点索引）的简单网格。"""

    __slots__ = ("name", "vertices", "faces", "closed")

    def __init__(self, name, vertices, faces, closed=True):
        self.name = name
        self.vertices = vertices
        self.faces = faces
        self.closed = closed


def _cube():
    v = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5),
         (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]
    f = [(0, 1, 2, 3),   # 后
         (4, 5, 6, 7),   # 前
         (0, 4, 7, 3),   # 左
         (1, 5, 6, 2),   # 右
         (3, 2, 6, 7),   # 上
         (0, 1, 5, 4)]   # 下
    return Mesh("cube", v, f)


def _plane():
    v = [(-0.5, 0.0, -0.5), (0.5, 0.0, -0.5), (0.5, 0.0, 0.5), (-0.5, 0.0, 0.5)]
    return Mesh("plane", v, [(0, 1, 2, 3)], closed=False)


def _pyramid():
    v = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5), (-0.5, -0.5, 0.5),
         (0.0, 0.7, 0.0)]
    f = [(0, 1, 2, 3),
         (0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
    return Mesh("pyramid", v, f)


def _sphere(segments=12, rings=8):
    verts = [(0.0, 0.5, 0.0)]
    for i in range(1, rings):
        phi = math.pi * i / rings
        y = 0.5 * math.cos(phi)
        r = 0.5 * math.sin(phi)
        for j in range(segments):
            theta = 2.0 * math.pi * j / segments
            verts.append((r * math.cos(theta), y, r * math.sin(theta)))
    verts.append((0.0, -0.5, 0.0))
    faces = []
    top = 0
    bottom = len(verts) - 1
    for j in range(segments):
        faces.append((top, 1 + j, 1 + (j + 1) % segments))
    for i in range(rings - 2):
        base = 1 + i * segments
        nxt = base + segments
        for j in range(segments):
            a = base + j
            b = base + (j + 1) % segments
            c = nxt + (j + 1) % segments
            d = nxt + j
            faces.append((a, b, c, d))
    base = 1 + (rings - 2) * segments
    for j in range(segments):
        faces.append((bottom, base + (j + 1) % segments, base + j))
    return Mesh("sphere", verts, faces)


def _cylinder(segments=12):
    verts = []
    for y in (0.5, -0.5):
        for j in range(segments):
            theta = 2.0 * math.pi * j / segments
            verts.append((0.5 * math.cos(theta), y, 0.5 * math.sin(theta)))
    faces = []
    for j in range(segments):
        a = j
        b = (j + 1) % segments
        c = segments + (j + 1) % segments
        d = segments + j
        faces.append((a, b, c, d))
    faces.append(tuple(range(segments)))
    faces.append(tuple(range(segments, segments * 2)))
    return Mesh("cylinder", verts, faces)


MESHES = {
    "cube": _cube(),
    "plane": _plane(),
    "pyramid": _pyramid(),
    "sphere": _sphere(),
    "cylinder": _cylinder(),
}


def mesh_of(shape):
    return MESHES.get(shape, MESHES["cube"])


# ---------------------------------------------------------------- 数学
def _norm(v):
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length < 1e-9:
        return (0.0, 0.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def rotate_xyz(point, rx, ry, rz):
    """按角度（度）依次绕 X、Y、Z 旋转。"""
    x, y, z = point
    if rx:
        a = math.radians(rx)
        ca, sa = math.cos(a), math.sin(a)
        y, z = y * ca - z * sa, y * sa + z * ca
    if ry:
        a = math.radians(ry)
        ca, sa = math.cos(a), math.sin(a)
        x, z = x * ca + z * sa, -x * sa + z * ca
    if rz:
        a = math.radians(rz)
        ca, sa = math.cos(a), math.sin(a)
        x, y = x * ca - y * sa, x * sa + y * ca
    return (x, y, z)


class Camera(object):
    """轨道相机：围绕 target 旋转，distance 控制远近。"""

    def __init__(self, yaw=35.0, pitch=22.0, distance=6.0,
                 target=(0.0, 0.6, 0.0), fov=50.0, near=0.1):
        self.yaw = float(yaw)
        self.pitch = float(pitch)
        self.distance = max(0.5, float(distance))
        self.target = tuple(float(c) for c in target)
        self.fov = float(fov)
        self.near = float(near)

    def copy(self):
        return Camera(self.yaw, self.pitch, self.distance, self.target, self.fov, self.near)

    @property
    def eye(self):
        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)
        cos_p = math.cos(pitch)
        return (self.target[0] + self.distance * cos_p * math.sin(yaw),
                self.target[1] + self.distance * math.sin(pitch),
                self.target[2] + self.distance * cos_p * math.cos(yaw))

    def basis(self):
        eye = self.eye
        forward = _norm(_sub(self.target, eye))
        world_up = (0.0, 1.0, 0.0)
        right = _cross(forward, world_up)
        if abs(right[0]) + abs(right[1]) + abs(right[2]) < 1e-6:
            right = (1.0, 0.0, 0.0)
        right = _norm(right)
        up = _norm(_cross(right, forward))
        return eye, forward, right, up

    def orbit(self, dyaw, dpitch):
        self.yaw = (self.yaw + dyaw) % 360.0
        self.pitch = max(-85.0, min(85.0, self.pitch + dpitch))

    def zoom(self, factor):
        self.distance = max(0.6, min(80.0, self.distance * factor))

    def pan(self, dx, dy):
        eye, forward, right, up = self.basis()
        scale = self.distance * 0.0016
        self.target = (self.target[0] - right[0] * dx * scale + up[0] * dy * scale,
                       self.target[1] - right[1] * dx * scale + up[1] * dy * scale,
                       self.target[2] - right[2] * dx * scale + up[2] * dy * scale)


class View(object):
    """把世界坐标投影到画布坐标。"""

    def __init__(self, camera, width, height):
        self.camera = camera
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.eye, self.forward, self.right, self.up = camera.basis()
        self.focal = (self.height / 2.0) / math.tan(math.radians(camera.fov) / 2.0)

    def project(self, point):
        rel = _sub(point, self.eye)
        x = _dot(rel, self.right)
        y = _dot(rel, self.up)
        z = _dot(rel, self.forward)
        if z <= self.camera.near:
            return None
        sx = self.width / 2.0 + self.focal * x / z
        sy = self.height / 2.0 - self.focal * y / z
        return sx, sy, z

    def scale_at(self, depth):
        if depth <= self.camera.near:
            return 0.0
        return self.focal / depth


def project_point(view, point):
    return view.project(point)


def screen_radius(view, point, radius):
    res = view.project(point)
    if res is None:
        return 0.0
    return max(2.0, res[2] and view.scale_at(res[2]) * radius)


# ---------------------------------------------------------------- 场景数据
def transform3d_of(entity):
    """取实体的 3D 变换；没有 Transform3D 时退化到 Transform 的 x/y。"""
    comps = entity.get("components", {})
    t3 = comps.get("Transform3D")
    base = comps.get("Transform", {})
    if t3:
        return {
            "x": float(t3.get("x", 0) or 0),
            "y": float(t3.get("y", 0) or 0),
            "z": float(t3.get("z", 0) or 0),
            "rx": float(t3.get("rx", 0) or 0),
            "ry": float(t3.get("ry", 0) or 0),
            "rz": float(t3.get("rz", 0) or 0),
            "scale": float(t3.get("scale", 1.0) or 1.0),
            "size": 1.0,
        }
    return {
        "x": float(base.get("x", 0) or 0) / 40.0,
        "y": 0.5,
        "z": float(base.get("y", 0) or 0) / 40.0,
        "rx": 0.0, "ry": 0.0, "rz": 0.0,
        "scale": max(0.05, float(base.get("width", 40) or 40) / 40.0),
        "size": 1.0,
    }


def has_3d(project):
    """项目里是否有 3D 物体（带 Mesh3D 组件）。"""
    for entity in (project or {}).get("entities", []):
        if entity.get("components", {}).get("Mesh3D"):
            return True
    return False


def entity_vertices(entity):
    """返回实体网格的世界坐标顶点列表。"""
    mesh_comp = entity.get("components", {}).get("Mesh3D") or {}
    mesh = mesh_of(mesh_comp.get("shape", "cube"))
    tf = transform3d_of(entity)
    scale = tf["scale"] * SIZES.get(mesh.name, 1.0)
    out = []
    for vx, vy, vz in mesh.vertices:
        rx, ry, rz = rotate_xyz((vx * scale, vy * scale, vz * scale),
                                tf["rx"], tf["ry"], tf["rz"])
        out.append((rx + tf["x"], ry + tf["y"], rz + tf["z"]))
    return out


def camera_from_project(project, width, height):
    """优先使用场景里的 Camera3D，否则用默认轨道相机。"""
    for entity in (project or {}).get("entities", []):
        cam = entity.get("components", {}).get("Camera3D")
        if cam:
            return Camera(
                yaw=float(cam.get("yaw", 35) or 0),
                pitch=float(cam.get("pitch", 22) or 0),
                distance=float(cam.get("distance", 6) or 6),
                target=(float(cam.get("target_x", 0) or 0),
                        float(cam.get("target_y", 0.8) or 0),
                        float(cam.get("target_z", 0) or 0)),
                fov=float(cam.get("fov", 50) or 50),
            )
    return Camera()


# ---------------------------------------------------------------- 颜色
def hex_to_rgb(value):
    text = (value or "#888888").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return (136, 136, 136)
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return (136, 136, 136)


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % (max(0, min(255, int(rgb[0]))),
                              max(0, min(255, int(rgb[1]))),
                              max(0, min(255, int(rgb[2]))))


def shade(color, factor):
    r, g, b = hex_to_rgb(color)
    return rgb_to_hex((r * factor, g * factor, b * factor))


# ---------------------------------------------------------------- 渲染
_LIGHT = _norm((0.45, 0.9, 0.35))


def _face_shade(world_verts, face):
    if len(face) < 3:
        return 1.0
    a = world_verts[face[0]]
    b = world_verts[face[1]]
    c = world_verts[face[2]]
    n = _norm(_cross(_sub(b, a), _sub(c, a)))
    return 0.35 + 0.65 * abs(_dot(n, _LIGHT))


def render_scene(canvas, project, camera, width, height, selected=None,
                 show_grid=True, show_axes=True, tag_prefix="3d"):
    """把 3D 场景画到 canvas 上；返回每个实体的投影中心 {eid: (sx, sy, depth)}。"""
    canvas.delete("all")
    view = View(camera, width, height)
    canvas.create_rectangle(0, 0, width, height, fill="#12121a", outline="")

    if show_grid:
        _draw_grid(canvas, view, width, height)
    if show_axes:
        _draw_axes(canvas, view)

    items = []
    centers = {}
    for entity in project.get("entities", []):
        comps = entity.get("components", {})
        mesh_comp = comps.get("Mesh3D")
        if not mesh_comp:
            continue
        if not entity.get("active", True):
            continue
        verts = entity_vertices(entity)
        tf = transform3d_of(entity)
        projected = [view.project(v) for v in verts]
        mesh = mesh_of(mesh_comp.get("shape", "cube"))
        color = mesh_comp.get("color", "#89b4fa")
        opacity = float(mesh_comp.get("opacity", 1.0) or 1.0)
        wire = bool(mesh_comp.get("wireframe"))
        for face in mesh.faces:
            if any(projected[i] is None for i in face):
                continue
            depth = sum(projected[i][2] for i in face) / float(len(face))
            poly = []
            for i in face:
                poly.extend(projected[i][:2])
            factor = _face_shade(verts, face)
            fill = shade(color, max(0.12, factor))
            outline = mesh_comp.get("outline", "") or shade(color, factor * 0.55)
            items.append((depth, poly, fill, outline, wire, opacity, entity.get("id")))
        center = view.project((tf["x"], tf["y"], tf["z"]))
        if center is not None:
            centers[entity.get("id")] = center
        if entity.get("id") == selected:
            _draw_selection_cube(canvas, view, entity, verts)

    items.sort(key=lambda item: item[0], reverse=True)
    bg = hex_to_rgb("#12121a")
    for depth, poly, fill, outline, wire, opacity, eid in items:
        if wire:
            canvas.create_polygon(*poly, fill="", outline=fill, width=1,
                                  tags=("%s_face" % tag_prefix,))
            continue
        r, g, b = hex_to_rgb(fill)
        alpha = max(0.0, min(1.0, opacity))
        blended = rgb_to_hex((r * alpha + bg[0] * (1 - alpha),
                              g * alpha + bg[1] * (1 - alpha),
                              b * alpha + bg[2] * (1 - alpha)))
        canvas.create_polygon(*poly, fill=blended, outline=outline, width=1,
                              tags=("%s_face" % tag_prefix,))
    return centers


def _draw_grid(canvas, view, width, height):
    size = 10
    for i in range(-size, size + 1):
        line = []
        for j in (0, 1):
            start = view.project((float(i), 0.0, -size if j == 0 else size))
            end = view.project((float(i), 0.0, size if j == 0 else -size))
            if start and end:
                line.extend([start[0], start[1], end[0], end[1]])
                canvas.create_line(*line, fill="#2a2a3a", width=1)
            line = []
        a = view.project((-size, 0.0, float(i)))
        b = view.project((size, 0.0, float(i)))
        if a and b:
            canvas.create_line(a[0], a[1], b[0], b[1], fill="#2a2a3a", width=1)


def _draw_axes(canvas, view):
    origin = view.project((0.0, 0.0, 0.0))
    if origin is None:
        return
    for point, color in (((1.6, 0.0, 0.0), "#f38ba8"),
                         ((0.0, 1.6, 0.0), "#a6e3a1"),
                         ((0.0, 0.0, 1.6), "#89b4fa")):
        other = view.project(point)
        if other is not None:
            canvas.create_line(origin[0], origin[1], other[0], other[1],
                               fill=color, width=2)


def _draw_selection_cube(canvas, view, entity, verts):
    edges = [(0, 1), (1, 2), (2, 3), (3, 0),
             (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
    if len(verts) < 8:
        return
    for a, b in edges:
        pa = view.project(verts[a])
        pb = view.project(verts[b])
        if pa and pb:
            canvas.create_line(pa[0], pa[1], pb[0], pb[1], fill="#00e676", width=2)


def _point_in_poly(x, y, poly):
    inside = False
    count = len(poly) // 2
    j = count - 1
    for i in range(count):
        xi, yi = poly[2 * i], poly[2 * i + 1]
        xj, yj = poly[2 * j], poly[2 * j + 1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def pick(project, camera, width, height, x, y):
    """屏幕坐标拾取：返回最靠前的实体 id。"""
    view = View(camera, width, height)
    best = None
    best_depth = 1e18
    for entity in project.get("entities", []):
        if not entity.get("components", {}).get("Mesh3D"):
            continue
        if not entity.get("active", True):
            continue
        verts = entity_vertices(entity)
        mesh = mesh_of(entity["components"]["Mesh3D"].get("shape", "cube"))
        for face in mesh.faces:
            pts = []
            depth = 0.0
            ok = True
            for i in face:
                res = view.project(verts[i])
                if res is None:
                    ok = False
                    break
                pts.extend(res[:2])
                depth += res[2]
            if not ok or not _point_in_poly(x, y, pts):
                continue
            depth /= float(len(face))
            if depth < best_depth:
                best_depth = depth
                best = entity.get("id")
    return best
