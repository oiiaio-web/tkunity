# -*- coding: utf-8 -*-
"""tkunity - 纯标准库的 Unity 风格 2D 游戏编辑器与运行时，可把 .pyu 游戏导出为 Android APK 工程。

核心概念对齐 Unity：GameObject（物体）+ Component（组件）+ 父子层级 + 预制体（Prefab），
内置刚体物理、AABB 碰撞/触发器、生命周期脚本、摄像机、动画与生成器。

Apache License 2.0 | Copyright 2026 oiiaio-web <3926580760@qq.com>
"""
from __future__ import annotations

from .api import GameObject, Project, load, load_project, save
from .components import (
    ADDABLE_COMPONENTS, BUILTIN_ACTIONS, COMPONENT_SCHEMAS, COMPONENT_ORDER,
    PARTS, clean_name,
)
from .pyu import PYU_VERSION, new_project
from . import world

__version__ = "2026.11.4"
__author__ = "oiiaio-web"
__author_email__ = "3926580760@qq.com"
__license__ = "Apache-2.0"

__all__ = [
    "__version__", "__author__", "__author_email__", "__license__",
    "PYU_VERSION", "Project", "GameObject", "load", "load_project", "save",
    "new_project", "PARTS", "COMPONENT_SCHEMAS", "COMPONENT_ORDER",
    "ADDABLE_COMPONENTS", "BUILTIN_ACTIONS", "world", "clean_name", "help",
]


def help():
    """打印 tkunity 命令帮助（等价命令行 tkunity -h / -help / --help）。"""
    from .cli import show_help
    show_help()
