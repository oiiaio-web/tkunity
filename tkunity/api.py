# -*- coding: utf-8 -*-
"""面向对象的建项目 API（无需打开编辑器即可用代码做游戏）。

示例::

    from tkunity import Project, GameObject

    p = Project("弹球")
    ball = GameObject("球", x=400, y=100, width=60, height=60)
    ball.add_sprite("oval", fill="#f38ba8")
    ball.add_rigidbody(velocity_x=160, velocity_y=-200, bounce=0.9)
    ball.add_collider()
    ball.add_script(on_update="if y > 600: restart()")
    p.add(ball)
    p.save("ball.pyu")
"""
from __future__ import annotations

import copy

from . import pyu, world
from .components import COMPONENT_SCHEMAS, new_component, clean_name

__all__ = ["Project", "GameObject", "save", "load"]


class GameObject(object):
    """场景中的一个物体。name/components 与 .pyu 实体一一对应。"""

    def __init__(self, name, x=0, y=0, width=80, height=60, layer=0,
                 tag="Untagged", active=True):
        self.name = clean_name(name, "物体")
        self.tag = tag
        self.active = bool(active)
        self.parent = None            # 父 GameObject（加入 Project 后生效）
        self._components = {}
        self._components["Transform"] = {
            "x": x, "y": y, "width": width, "height": height,
            "rotation": 0.0, "scale": 1.0, "layer": layer,
        }
        self._id = None               # 加入 Project 后赋值
        self._project = None

    # ---- 便捷增删组件 ----
    def add_sprite(self, shape="rect", fill="#4C8BF5", outline="#123456",
                   image="", opacity=1.0):
        return self.set_component("Sprite", shape=shape, fill=fill, outline=outline,
                                  image=image, opacity=opacity)

    def add_label(self, text="文本", font_size=18, color="#000000", bold=False,
                  align="center"):
        return self.set_component("Label", text=text, font_size=font_size, color=color,
                                  bold=bold, align=align)

    def add_tap(self, action="none"):
        return self.set_component("TapHandler", action=action)

    def add_timer(self, interval_ms=1000, action="none", auto_start=True, repeat=True):
        return self.set_component("Timer", interval_ms=interval_ms, action=action,
                                  auto_start=auto_start, repeat=repeat)

    def add_rigidbody(self, body_type="dynamic", velocity_x=0.0, velocity_y=0.0,
                      gravity_scale=1.0, drag=0.0, bounce=1.0):
        return self.set_component("Rigidbody2D", body_type=body_type,
                                  velocity_x=velocity_x, velocity_y=velocity_y,
                                  gravity_scale=gravity_scale, drag=drag, bounce=bounce)

    def add_collider(self, is_trigger=False, offset_x=0, offset_y=0, width=0, height=0):
        return self.set_component("BoxCollider2D", is_trigger=is_trigger,
                                  offset_x=offset_x, offset_y=offset_y,
                                  width=width, height=height)

    def add_script(self, on_start="", on_update="", on_tap="",
                   on_collision="", on_destroy="", name="MonoBehaviour"):
        return self.set_component("Script", name=name, on_start=on_start,
                                  on_update=on_update, on_tap=on_tap,
                                  on_collision=on_collision, on_destroy=on_destroy)

    def add_animator(self, effect="spin", speed=1.0, amplitude=1.0, auto_play=True):
        return self.set_component("Animator", effect=effect, speed=speed,
                                  amplitude=amplitude, auto_play=auto_play)

    def add_camera(self, follow="", zoom=1.0, smooth=0.15):
        return self.set_component("Camera2D", follow=follow, zoom=zoom, smooth=smooth)

    def add_spawner(self, prefab, interval_ms=1000, max_alive=8, offset_x=0, offset_y=0):
        return self.set_component("Spawner", prefab=prefab, interval_ms=interval_ms,
                                  max_alive=max_alive, offset_x=offset_x,
                                  offset_y=offset_y)

    def set_component(self, comp_name, **values):
        if comp_name not in COMPONENT_SCHEMAS:
            raise KeyError("未知组件: %s" % comp_name)
        comp = self._components.setdefault(comp_name, new_component(comp_name))
        comp.update(values)
        return self

    def remove_component(self, name):
        if name != "Transform" and name in self._components:
            del self._components[name]
        return self

    def has(self, name):
        return name in self._components

    def get(self, name, default=None):
        return self._components.get(name, default)

    @property
    def transform(self):
        return self._components["Transform"]

    # ---- 常用变换操作 ----
    def move(self, dx, dy):
        t = self.transform
        t["x"] += dx
        t["y"] += dy
        return self

    def set_position(self, x=None, y=None):
        if x is not None:
            self.transform["x"] = x
        if y is not None:
            self.transform["y"] = y
        return self

    def set_size(self, width=None, height=None):
        if width is not None:
            self.transform["width"] = width
        if height is not None:
            self.transform["height"] = height
        return self

    def set_rotation(self, degrees):
        self.transform["rotation"] = float(degrees)
        return self

    def set_parent(self, parent):
        """设置父物体（需要两者都已加入同一个 Project）。"""
        self.parent = parent
        if self._project is not None and self._id is not None:
            pyu.set_parent(self._project.to_dict(), self._id,
                           parent._id if parent is not None else None)
        return self

    def __getitem__(self, name):
        return self._components[name]

    def to_dict(self, entity_id=None):
        eid = self._id if entity_id is None else entity_id
        return {
            "id": eid,
            "name": self.name,
            "tag": self.tag,
            "active": bool(self.active),
            "parent": (self.parent._id if getattr(self, "parent", None) is not None else None),
            "components": self._components,
        }


class Project(object):
    """一个游戏项目，等价于一份 .pyu 文件（一个场景）。"""

    def __init__(self, name="未命名项目", scene_width=960, scene_height=640,
                 background="#1e1e2e", gravity=pyu.DEFAULT_GRAVITY):
        self._project = pyu.new_project(name, scene_width, scene_height, background, gravity)
        self.objects = []

    # ---- 元信息 ----
    @property
    def meta(self):
        return self._project["meta"]

    @property
    def name(self):
        return self._project["meta"].get("name", "未命名项目")

    @name.setter
    def name(self, value):
        self._project["meta"]["name"] = clean_name(value)

    def set_scene(self, width=None, height=None, background=None):
        meta = self._project["meta"]
        if width is not None:
            meta["scene_width"] = int(width)
        if height is not None:
            meta["scene_height"] = int(height)
        if background is not None:
            meta["background"] = background
        return self

    def set_physics(self, gravity=None, time_scale=None):
        meta = self._project["meta"]
        if gravity is not None:
            meta["gravity"] = float(gravity)
        if time_scale is not None:
            meta["time_scale"] = float(time_scale)
        return self

    # ---- 物体 ----
    def add(self, obj, parent=None):
        """把一个 GameObject 加入场景（可链式）。parent 为父 GameObject。"""
        if not isinstance(obj, GameObject):
            raise TypeError("Project.add 需要 GameObject")
        entity = obj.to_dict(pyu.next_entity_id(self._project))
        if parent is not None:
            if parent._id is None:
                raise ValueError("父物体还没有加入项目")
            entity["parent"] = parent._id
            obj.parent = parent
        self._project["entities"].append(entity)
        obj._id = entity["id"]
        obj._project = self
        self.objects.append(obj)
        return obj

    def add_many(self, *objects):
        """一次加入多个物体，返回最后一个（便于链式）。"""
        for obj in objects:
            self.add(obj)
        return self

    def remove(self, obj):
        eid = obj._id if isinstance(obj, GameObject) else obj
        ids = pyu.remove_entity(self._project, eid)
        self.objects = [o for o in self.objects if o._id not in ids]
        return self

    def find(self, name):
        """按名字查找实体字典（找不到返回 None）。"""
        for entity in self._project["entities"]:
            if entity.get("name") == name:
                return entity
        return None

    def all(self):
        return list(self._project["entities"])

    def tag(self, name):
        """按 tag 过滤实体列表。"""
        return [e for e in self._project["entities"] if e.get("tag") == name]

    def find_with_component(self, component):
        return [e for e in self._project["entities"]
                if component in e.get("components", {})]

    # ---- 预制体 ----
    def save_prefab(self, obj, name=None):
        """把物体存成预制体，返回预制体名。"""
        eid = obj._id if isinstance(obj, GameObject) else obj
        return pyu.save_prefab(self._project, eid, name)

    def instantiate(self, prefab, x=None, y=None, parent=None):
        """实例化预制体，返回新的 GameObject 包装（已加入项目）。"""
        entity = pyu.instantiate_prefab(self._project, prefab, x, y,
                                        parent._id if parent is not None else None)
        obj = self._wrap(entity)
        self.objects.append(obj)
        return obj

    @property
    def prefabs(self):
        return sorted(self._project.get("prefabs", {}).keys())

    def _wrap(self, entity):
        obj = GameObject(entity.get("name", "物体"))
        obj._components = entity.get("components", {})
        obj._id = entity.get("id")
        obj.tag = entity.get("tag", "Untagged")
        obj.active = entity.get("active", True)
        obj._project = self
        return obj

    # ---- 世界信息 ----
    def world_rect(self, obj):
        eid = obj._id if isinstance(obj, GameObject) else obj
        return world.rect_of(pyu.entity_by_id(self._project, eid), self._project)

    def children(self, obj):
        eid = obj._id if isinstance(obj, GameObject) else obj
        return [e for e in pyu.children_of(self._project, eid)]

    # ---- 资源 / 读写 ----
    def embed_image(self, path):
        """内嵌本地 PNG/GIF 图片，返回资源名。"""
        return pyu.embed_image(self._project, path)

    def to_dict(self):
        return self._project

    def save(self, path):
        pyu.save(self._project, path)
        return path

    def clone(self):
        """深拷贝一个项目（脚本批量生成关卡时好用）。"""
        other = Project(self.name)
        other._project = copy.deepcopy(self._project)
        return other


def save(project, path):
    """保存 Project（或直接传字典）到 .pyu 文件。"""
    if isinstance(project, Project):
        project = project.to_dict()
    pyu.save(project, path)
    return path


def load(path):
    """读取 .pyu 文件，返回项目字典（供运行时 / 编辑器使用）。"""
    return pyu.load(path)


def load_project(path):
    """读取 .pyu 文件，返回 Project 包装对象。"""
    data = pyu.load(path)
    project = Project(data["meta"].get("name", "未命名项目"))
    project._project = data
    for entity in data.get("entities", []):
        project.objects.append(project._wrap(entity))
    return project
