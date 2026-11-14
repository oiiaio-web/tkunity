# -*- coding: utf-8 -*-
""".pyu 项目文件的读写与场景操作。

格式：8 字节魔数 ``TKU-PYU\\x00\\x01\\n`` + 一个 JSON 对象。
图片等二进制资源以 base64 内嵌在 ``assets`` 段，单文件自包含。

项目结构（v2）::

    {
      "meta":     {name, scene_width, scene_height, background, gravity, time_scale, tkunity_version},
      "entities": [{id, name, tag, active, parent, components: {...}}, ...],
      "assets":   {"images/a.png": "<base64>"},
      "prefabs":  {"ball": {name, components: {...}}, ...}
    }

实体通过 ``parent`` 字段构成层级（父物体的坐标变换会累加到子物体上）。
"""
from __future__ import annotations

import base64
import copy
import json
import os

from .components import new_component, new_transform, validate_component

__all__ = [
    "MAGIC", "PYU_VERSION", "new_project", "add_entity", "save", "load",
    "asset_to_photo", "photo_to_asset", "read_image_file", "embed_image",
    "project_name", "entity_by_id", "children_of", "root_entities",
    "entity_order", "descendants", "set_parent", "remove_entity", "clone_entity",
    "next_entity_id", "migrate", "save_prefab", "instantiate_prefab",
    "prefab_names", "unique_name",
]

MAGIC = b"TKU-PYU\x00\x01\n"
PYU_VERSION = "2026.11.4"

# tkinter PhotoImage 只吃 base64 的 PNG/GIF 数据
SUPPORTED_IMAGE_EXTS = (".png", ".gif")

DEFAULT_GRAVITY = 980.0


def new_project(name="未命名项目", scene_width=960, scene_height=640,
                background="#1e1e2e", gravity=DEFAULT_GRAVITY):
    """创建一个空项目字典。"""
    return {
        "meta": {
            "tkunity_version": PYU_VERSION,
            "name": name,
            "scene_width": int(scene_width),
            "scene_height": int(scene_height),
            "background": background,
            "gravity": float(gravity),
            "time_scale": 1.0,
        },
        "entities": [],
        "assets": {},   # relpath -> base64
        "prefabs": {},  # 预制体名 -> {name, components}
    }


# ---------------------------------------------------------------- 实体操作
def next_entity_id(project):
    return max([e.get("id", 0) for e in project.get("entities", [])], default=0) + 1


def entity_by_id(project, eid):
    for entity in project.get("entities", []):
        if entity.get("id") == eid:
            return entity
    return None


def children_of(project, eid):
    """直接子物体（按 id 升序）。"""
    kids = [e for e in project.get("entities", []) if e.get("parent") == eid]
    return sorted(kids, key=lambda e: e.get("id", 0))


def root_entities(project):
    ids = set(e.get("id") for e in project.get("entities", []))
    roots = [e for e in project.get("entities", []) if e.get("parent") not in ids]
    return sorted(roots, key=lambda e: e.get("id", 0))


def descendants(project, eid):
    """所有后代（深度优先）。"""
    out = []
    for kid in children_of(project, eid):
        out.append(kid)
        out.extend(descendants(project, kid.get("id")))
    return out


def entity_order(project):
    """深度优先的实体顺序（父物体总在子物体之前），绘制与层级面板都用它。"""
    out = []

    def walk(entity):
        out.append(entity)
        for kid in children_of(project, entity.get("id")):
            walk(kid)

    for root in root_entities(project):
        walk(root)
    # 兜底：理论上不会有孤儿，但数据损坏时也别丢实体
    seen = set(e.get("id") for e in out)
    for entity in project.get("entities", []):
        if entity.get("id") not in seen:
            out.append(entity)
    return out


def set_parent(project, child_id, parent_id):
    """设置父子关系，自动阻止「自己当自己父级」和成环。"""
    child = entity_by_id(project, child_id)
    if child is None:
        raise ValueError("找不到物体 id=%r" % (child_id,))
    if parent_id in (None, 0, "", "None"):
        child["parent"] = None
        return child
    parent = entity_by_id(project, parent_id)
    if parent is None:
        raise ValueError("找不到父物体 id=%r" % (parent_id,))
    if parent is child:
        raise ValueError("不能把物体设为自己的子物体")
    node = parent
    while node is not None:
        if node.get("id") == child_id:
            raise ValueError("会形成父子环")
        node = entity_by_id(project, node.get("parent"))
    child["parent"] = parent.get("id")
    return child


def add_entity(project, name, components=None, transform=None, entity_id=None,
               parent=None, tag="Untagged", active=True):
    """向项目追加一个实体，返回实体字典。

    components: {组件名: {字段值}}，Transform 会自动补齐。
    """
    comps = {}
    tf = dict(new_transform())
    if components and isinstance(components.get("Transform"), dict):
        tf.update(components["Transform"])
    if transform:
        tf.update(transform)
    ok, tf, err = validate_component("Transform", tf)
    if not ok:
        raise ValueError(err)
    comps["Transform"] = tf
    for cname, values in (components or {}).items():
        if cname == "Transform":
            continue
        comp = new_component(cname)
        if values:
            comp.update(values)
        ok, comp, err = validate_component(cname, comp)
        if not ok:
            raise ValueError(err)
        comps[cname] = comp
    entity = {
        "id": int(entity_id if entity_id is not None else next_entity_id(project)),
        "name": str(name),
        "tag": str(tag or "Untagged"),
        "active": bool(active),
        "parent": parent if parent not in (0, "", "None") else None,
        "components": comps,
    }
    project.setdefault("entities", []).append(entity)
    return entity


def remove_entity(project, eid, recursive=True):
    """删除实体；recursive=True 时连同所有子物体一起删除。返回被删除的 id 列表。"""
    entity = entity_by_id(project, eid)
    if entity is None:
        return []
    victims = [entity] + (descendants(project, eid) if recursive else [])
    ids = [e["id"] for e in victims]
    # 非递归时把子物体提为根
    for kid in children_of(project, eid):
        if not recursive:
            kid["parent"] = entity.get("parent")
    project["entities"] = [e for e in project["entities"] if e.get("id") not in ids]
    return ids


def unique_name(project, base):
    """在项目里生成不重名的物体名：ball / ball (1) / ball (2) ..."""
    names = set(e.get("name") for e in project.get("entities", []))
    if base not in names:
        return base
    i = 1
    while "%s (%d)" % (base, i) in names:
        i += 1
    return "%s (%d)" % (base, i)


def clone_entity(project, src, name=None, offset_x=20, offset_y=20, parent=None):
    """复制一个实体（含组件），返回新实体。"""
    if isinstance(src, int):
        src = entity_by_id(project, src)
    if src is None:
        raise ValueError("找不到要复制的物体")
    comps = copy.deepcopy(src.get("components", {}))
    tf = comps.setdefault("Transform", dict(new_transform()))
    tf["x"] = int(tf.get("x", 0)) + offset_x
    tf["y"] = int(tf.get("y", 0)) + offset_y
    new_name = unique_name(project, name or (src.get("name", "物体") + " (1)"))
    return add_entity(project, new_name, components=comps,
                      parent=parent if parent is not None else src.get("parent"),
                      tag=src.get("tag", "Untagged"), active=src.get("active", True))


# ---------------------------------------------------------------- 预制体
def prefab_names(project):
    return sorted(project.get("prefabs", {}).keys())


def save_prefab(project, eid, name=None):
    """把场景里的实体存成预制体（只保存组件，不保存 id / 父子关系）。"""
    entity = entity_by_id(project, eid)
    if entity is None:
        raise ValueError("找不到要保存的物体")
    pname = (name or entity.get("name") or "prefab").strip() or "prefab"
    project.setdefault("prefabs", {})[pname] = {
        "name": pname,
        "tag": entity.get("tag", "Untagged"),
        "components": copy.deepcopy(entity.get("components", {})),
    }
    return pname


def instantiate_prefab(project, name, x=None, y=None, parent=None):
    """在指定位置实例化预制体，返回新实体。"""
    prefab = project.get("prefabs", {}).get(name)
    if prefab is None:
        raise ValueError("找不到预制体: %s" % (name,))
    comps = copy.deepcopy(prefab.get("components", {}))
    tf = comps.setdefault("Transform", dict(new_transform()))
    if x is not None:
        tf["x"] = int(x)
    if y is not None:
        tf["y"] = int(y)
    return add_entity(project, unique_name(project, prefab.get("name", name)),
                      components=comps, parent=parent,
                      tag=prefab.get("tag", "Untagged"))


# ---------------------------------------------------------------- 资源
def read_image_file(path):
    """读取图片文件 -> (base64 字符串, 相对路径名)。非 PNG/GIF 返回 None。"""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_IMAGE_EXTS:
        return None
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode("ascii")
    name = "images/" + os.path.basename(path)
    return data, name


def embed_image(project, path):
    """把本地图片内嵌进项目 assets，返回资源名（供 Sprite.image 引用）。"""
    item = read_image_file(path)
    if item is None:
        raise ValueError("仅支持 PNG/GIF 图片: %s" % path)
    data, name = item
    project.setdefault("assets", {})[name] = data
    return name


def photo_to_asset(photo):
    """把 tkinter PhotoImage 序列化成 base64（用于复制/另存为）。"""
    try:
        return photo.zoom(1).write("", format="png")  # 仅在需要时使用
    except Exception:
        return None


def asset_to_photo(asset_b64):
    """base64 资源 -> tkinter.PhotoImage（需在有 tk 的进程中调用）。"""
    import tkinter as tk  # 延迟导入，保证无 GUI 环境下模块可导入
    return tk.PhotoImage(data=asset_b64)


# ---------------------------------------------------------------- 读写
def save(project, path):
    """保存项目到 .pyu 文件。"""
    blob = json.dumps(project, ensure_ascii=False, indent=1,
                      sort_keys=False, separators=(",", ": ")).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(MAGIC)
        fh.write(blob)


def migrate(project):
    """补齐旧版本项目缺失的字段（幂等）。"""
    meta = project.setdefault("meta", {})
    meta.setdefault("tkunity_version", PYU_VERSION)
    meta.setdefault("name", "未命名项目")
    meta.setdefault("scene_width", 960)
    meta.setdefault("scene_height", 640)
    meta.setdefault("background", "#1e1e2e")
    meta.setdefault("gravity", DEFAULT_GRAVITY)
    meta.setdefault("time_scale", 1.0)

    project.setdefault("entities", [])
    project.setdefault("assets", {})
    project.setdefault("prefabs", {})

    ids = set(e.get("id") for e in project["entities"])
    for entity in project["entities"]:
        entity.setdefault("id", 0)
        entity.setdefault("name", "物体")
        entity.setdefault("tag", "Untagged")
        entity.setdefault("active", True)
        entity.setdefault("components", {})
        comps = entity["components"]
        tf = comps.get("Transform")
        if not isinstance(tf, dict):
            tf = dict(new_transform())
            comps["Transform"] = tf
        tf.setdefault("scale", 1.0)
        tf.setdefault("rotation", 0.0)
        tf.setdefault("layer", 0)
        parent = entity.get("parent")
        if parent in (0, "", "None"):
            parent = None
        if parent is not None and parent not in ids:
            parent = None  # 父物体已被删除
        entity["parent"] = parent
    return project


def load(path):
    """加载 .pyu 文件。兼容无魔数的纯 JSON 文件与旧版字段。"""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(MAGIC):
        raw = raw[len(MAGIC):]
    project = json.loads(raw.decode("utf-8"))
    migrate(project)
    if not project["meta"].get("name"):
        project["meta"]["name"] = os.path.splitext(os.path.basename(path))[0]
    return project


def project_name(project):
    return project.get("meta", {}).get("name", "未命名项目")
