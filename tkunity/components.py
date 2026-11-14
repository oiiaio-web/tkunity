# -*- coding: utf-8 -*-
"""组件注册表与零件库。

每个组件描述一组字段（类型 / 默认值 / 取值范围），编辑器据此动态生成属性面板，
运行时据此执行行为，导出器据此生成 Java 渲染与物理代码。

组件列表（对齐 Unity 的概念命名）：
    Transform      位移 / 尺寸 / 旋转 / 缩放 / 绘制顺序（支持父子层级）
    Sprite         矩形 / 椭圆 / 图片精灵，含透明度
    Label          文本渲染（对齐方式可调）
    Animator       轻量补间动画：自转 / 脉冲 / 淡入淡出 / 平移 / 漂浮
    Rigidbody2D    2D 刚体：重力、速度、阻尼、弹性
    BoxCollider2D  轴对齐包围盒碰撞体，可设为触发器
    TapHandler     点击 / 触摸事件
    Timer          定时器（可重复 / 单次 / 自动启动）
    Script         生命周期脚本（on_start / on_update / on_tap / on_collision / on_destroy）
    Spawner        按间隔生成预制体实例
    Camera2D       跟随目标 + 缩放
"""
from __future__ import annotations

__all__ = [
    "SHAPES", "BODY_TYPES", "ANIM_EFFECTS", "TEXT_ALIGNS", "COMMON_TAGS",
    "COMPONENT_SCHEMAS", "COMPONENT_ORDER", "ADDABLE_COMPONENTS", "PARTS",
    "PART_SIZES", "TRANSFORM_FIELDS", "BUILTIN_ACTIONS", "ACTION_HELP",
    "new_transform", "new_component", "validate_component", "component_title",
    "clean_name",
]

# ---------------------------------------------------------------- 枚举定义
SHAPES = ["rect", "oval", "image"]
MESH_SHAPES = ["cube", "sphere", "plane", "pyramid", "cylinder"]
BODY_TYPES = ["dynamic", "kinematic", "static"]
ANIM_EFFECTS = ["none", "spin", "pulse", "fade", "slide", "float"]
TEXT_ALIGNS = ["center", "left", "right"]

# 常用标签（Unity 的 Tag），也允许用户自定义
COMMON_TAGS = ["Untagged", "Player", "Enemy", "Pickup", "Ground", "UI"]

# 内置动作（桌面预览与 APK 导出通用；导出时不支持自定义表达式）
BUILTIN_ACTIONS = [
    "none",
    "move-left", "move-right", "move-up", "move-down",
    "bounce", "stop", "jump", "destroy", "toggle", "restart",
    "spawn:<预制体名>",
]

ACTION_HELP = (
    "内置动作: none / move-left / move-right / move-up / move-down / bounce / "
    "stop / jump / destroy / toggle / restart / spawn:<预制体名> / print('文字')。"
    "桌面预览还支持 Python 表达式（x/y/w/h/vx/vy/self/scene/log/find/spawn 可用）。"
)

# ---------------------------------------------------------------- 组件表
COMPONENT_SCHEMAS = {
    "Transform": {
        "title": "变换",
        "fields": {
            "x":        {"type": "int",   "default": 0,    "hint": "X 坐标（相对父物体）"},
            "y":        {"type": "int",   "default": 0,    "hint": "Y 坐标（相对父物体）"},
            "width":    {"type": "int",   "default": 80,   "min": 0, "hint": "宽度（px）"},
            "height":   {"type": "int",   "default": 60,   "min": 0, "hint": "高度（px）"},
            "rotation": {"type": "float", "default": 0.0,  "hint": "旋转角度（度，顺时针）"},
            "scale":    {"type": "float", "default": 1.0,  "min": 0.01, "hint": "缩放倍数"},
            "layer":    {"type": "int",   "default": 0,    "hint": "绘制层级，越大越靠上"},
        },
    },
    "Sprite": {
        "title": "精灵",
        "fields": {
            "shape":   {"type": "choice", "options": SHAPES, "default": "rect", "hint": "形状"},
            "fill":    {"type": "color",  "default": "#4C8BF5", "hint": "填充色"},
            "outline": {"type": "color",  "default": "#123456", "hint": "描边色"},
            "image":   {"type": "file",   "default": "", "hint": "PNG/GIF 图片（shape=image 时）"},
            "opacity": {"type": "float",  "default": 1.0, "min": 0.0, "max": 1.0, "hint": "不透明度 0~1"},
        },
    },
    "Label": {
        "title": "文本",
        "fields": {
            "text":      {"type": "text", "default": "文本", "hint": "显示文字"},
            "font_size": {"type": "int",  "default": 18, "min": 1, "hint": "字号"},
            "color":     {"type": "color", "default": "#000000", "hint": "文字颜色"},
            "bold":      {"type": "bool", "default": False, "hint": "加粗"},
            "align":     {"type": "choice", "options": TEXT_ALIGNS, "default": "center", "hint": "对齐方式"},
        },
    },
    "Animator": {
        "title": "动画",
        "fields": {
            "effect":    {"type": "choice", "options": ANIM_EFFECTS, "default": "spin", "hint": "动画效果"},
            "speed":     {"type": "float", "default": 1.0, "min": 0.0, "hint": "播放速度"},
            "amplitude": {"type": "float", "default": 1.0, "min": 0.0, "hint": "幅度"},
            "auto_play": {"type": "bool",  "default": True, "hint": "自动播放"},
        },
    },
    "Rigidbody2D": {
        "title": "刚体",
        "fields": {
            "body_type":     {"type": "choice", "options": BODY_TYPES, "default": "dynamic", "hint": "刚体类型"},
            "velocity_x":    {"type": "float", "default": 0.0, "hint": "X 速度（px/s）"},
            "velocity_y":    {"type": "float", "default": 0.0, "hint": "Y 速度（px/s）"},
            "gravity_scale": {"type": "float", "default": 1.0, "hint": "重力倍数（0 = 失重）"},
            "drag":          {"type": "float", "default": 0.0, "min": 0.0, "hint": "阻尼（每秒衰减）"},
            "bounce":        {"type": "float", "default": 1.0, "min": 0.0, "max": 1.0, "hint": "弹性 0~1"},
            "fixed_rotation": {"type": "bool", "default": True, "hint": "锁定旋转"},
        },
    },
    "BoxCollider2D": {
        "title": "碰撞体",
        "fields": {
            "is_trigger": {"type": "bool", "default": False, "hint": "设为触发器（穿透并回调）"},
            "offset_x":   {"type": "int",  "default": 0, "hint": "碰撞体 X 偏移"},
            "offset_y":   {"type": "int",  "default": 0, "hint": "碰撞体 Y 偏移"},
            "width":      {"type": "int",  "default": 0, "min": 0, "hint": "碰撞体宽（0 = 跟随 Transform）"},
            "height":     {"type": "int",  "default": 0, "min": 0, "hint": "碰撞体高（0 = 跟随 Transform）"},
        },
    },
    "TapHandler": {
        "title": "点击事件",
        "fields": {
            "action": {"type": "text", "default": "none", "multiline": True,
                       "hint": "点击动作（见下方说明）"},
        },
    },
    "Timer": {
        "title": "定时器",
        "fields": {
            "interval_ms": {"type": "int",  "default": 1000, "min": 1, "hint": "触发间隔（毫秒）"},
            "action":      {"type": "text", "default": "none", "multiline": True,
                            "hint": "定时动作（见下方说明）"},
            "auto_start":  {"type": "bool", "default": True, "hint": "开始时自动计时"},
            "repeat":      {"type": "bool", "default": True, "hint": "重复触发（关闭则只触发一次）"},
        },
    },
    "Script": {
        "title": "脚本",
        "fields": {
            "name":        {"type": "text", "default": "MonoBehaviour", "hint": "脚本名（仅备注）"},
            "on_start":    {"type": "text", "default": "", "multiline": True, "hint": "开始：初始化代码"},
            "on_update":   {"type": "text", "default": "", "multiline": True, "hint": "每帧：dt 秒、x/y/vx/vy 可用"},
            "on_tap":      {"type": "text", "default": "", "multiline": True, "hint": "被点击"},
            "on_collision": {"type": "text", "default": "", "multiline": True, "hint": "碰撞：other 为对方实体"},
            "on_destroy":  {"type": "text", "default": "", "multiline": True, "hint": "销毁时"},
        },
    },
    "Spawner": {
        "title": "生成器",
        "fields": {
            "prefab":      {"type": "prefab", "default": "", "hint": "要生成的预制体"},
            "interval_ms": {"type": "int",  "default": 1000, "min": 16, "hint": "生成间隔（毫秒）"},
            "max_alive":   {"type": "int",  "default": 8, "min": 0, "hint": "最大存活数（0 = 不限）"},
            "offset_x":    {"type": "int",  "default": 0, "hint": "生成位置 X 偏移"},
            "offset_y":    {"type": "int",  "default": 0, "hint": "生成位置 Y 偏移"},
        },
    },
    "Camera2D": {
        "title": "摄像机",
        "fields": {
            "follow":  {"type": "entity", "default": "", "hint": "跟随的物体（留空 = 固定）"},
            "zoom":    {"type": "float",  "default": 1.0, "min": 0.1, "max": 8.0, "hint": "缩放倍数"},
            "smooth":  {"type": "float",  "default": 0.15, "min": 0.0, "max": 1.0, "hint": "跟随平滑 0~1"},
        },
    },
    # ------------------------------------------------------------ 3D
    "Transform3D": {
        "title": "3D 变换",
        "fields": {
            "x":     {"type": "float", "default": 0.0, "hint": "X 位置（世界单位）"},
            "y":     {"type": "float", "default": 0.5, "hint": "Y 位置（向上）"},
            "z":     {"type": "float", "default": 0.0, "hint": "Z 位置"},
            "rx":    {"type": "float", "default": 0.0, "hint": "绕 X 旋转（度）"},
            "ry":    {"type": "float", "default": 0.0, "hint": "绕 Y 旋转（度）"},
            "rz":    {"type": "float", "default": 0.0, "hint": "绕 Z 旋转（度）"},
            "scale": {"type": "float", "default": 1.0, "min": 0.05, "hint": "缩放倍数"},
        },
    },
    "Mesh3D": {
        "title": "3D 网格",
        "fields": {
            "shape":     {"type": "choice", "options": MESH_SHAPES, "default": "cube", "hint": "网格类型"},
            "color":     {"type": "color",  "default": "#89b4fa", "hint": "表面颜色"},
            "outline":   {"type": "color",  "default": "", "hint": "描边色（留空自动）"},
            "opacity":   {"type": "float",  "default": 1.0, "min": 0.0, "max": 1.0, "hint": "不透明度"},
            "wireframe": {"type": "bool",   "default": False, "hint": "只画线框"},
        },
    },
    "Camera3D": {
        "title": "3D 相机",
        "fields": {
            "yaw":      {"type": "float", "default": 35.0, "hint": "水平角（度）"},
            "pitch":    {"type": "float", "default": 22.0, "hint": "俯仰角（度）"},
            "distance": {"type": "float", "default": 6.0, "min": 0.5, "hint": "距离"},
            "fov":      {"type": "float", "default": 50.0, "min": 10.0, "max": 120.0, "hint": "视野角"},
            "target_x": {"type": "float", "default": 0.0, "hint": "注视点 X"},
            "target_y": {"type": "float", "default": 0.8, "hint": "注视点 Y"},
            "target_z": {"type": "float", "default": 0.0, "hint": "注视点 Z"},
        },
    },
}

# Inspector / 添加组件菜单里的展示顺序
COMPONENT_ORDER = [
    "Transform", "Sprite", "Label", "Animator", "Rigidbody2D", "BoxCollider2D",
    "TapHandler", "Timer", "Script", "Spawner", "Camera2D",
    "Transform3D", "Mesh3D", "Camera3D",
]

# 可被用户手动增删的组件（Transform 必备，不可删）
ADDABLE_COMPONENTS = [c for c in COMPONENT_ORDER if c != "Transform"]

TRANSFORM_FIELDS = COMPONENT_SCHEMAS["Transform"]["fields"]

# 零件库：编辑器左侧列表。每项 = (显示名, 附加组件字典, 默认尺寸)
PARTS = [
    ("矩形",       {"Sprite": {"shape": "rect"}}, (80, 60)),
    ("椭圆",       {"Sprite": {"shape": "oval"}}, (80, 60)),
    ("文本",       {"Label": {}}, (160, 40)),
    ("图片",       {"Sprite": {"shape": "image"}}, (120, 120)),
    ("点击触发器", {"TapHandler": {}}, (80, 60)),
    ("定时器",     {"Timer": {}}, (80, 60)),
    ("物理球",     {"Sprite": {"shape": "oval", "fill": "#f38ba8"},
                   "Rigidbody2D": {"velocity_x": 120, "velocity_y": -80},
                   "BoxCollider2D": {}}, (60, 60)),
    ("平台",       {"Sprite": {"shape": "rect", "fill": "#45475a"},
                   "BoxCollider2D": {}}, (240, 24)),
    ("脚本",       {"Script": {}}, (40, 40)),
    ("动画",       {"Sprite": {"shape": "rect", "fill": "#89b4fa"}, "Animator": {}}, (80, 80)),
    ("生成器",     {"Spawner": {}}, (40, 40)),
    ("摄像机",     {"Camera2D": {}}, (40, 40)),
    # ---- 3D 零件 ----
    ("立方体",     {"Transform3D": {}, "Mesh3D": {"shape": "cube"}}, (60, 60)),
    ("球体",       {"Transform3D": {}, "Mesh3D": {"shape": "sphere", "color": "#f9e2af"}}, (60, 60)),
    ("平面",       {"Transform3D": {"y": 0.0}, "Mesh3D": {"shape": "plane", "color": "#45475a"}}, (60, 60)),
    ("棱锥",       {"Transform3D": {}, "Mesh3D": {"shape": "pyramid", "color": "#f38ba8"}}, (60, 60)),
    ("圆柱",       {"Transform3D": {}, "Mesh3D": {"shape": "cylinder", "color": "#a6e3a1"}}, (60, 60)),
    ("3D 相机",    {"Camera3D": {}}, (40, 40)),
]

PART_SIZES = {name: size for name, _comps, size in PARTS}


def component_title(name):
    """组件的中文显示名（未知组件返回原名）。"""
    return COMPONENT_SCHEMAS.get(name, {}).get("title", name)


def clean_name(text, fallback="未命名"):
    """把用户输入的名字规范成安全的非空字符串。"""
    if text is None:
        return fallback
    text = str(text).replace("\n", " ").strip()
    return text or fallback


def new_transform(x=0, y=0, width=80, height=60, rotation=0.0, layer=0, scale=1.0):
    """创建一份 Transform 默认字段。"""
    t = {k: v["default"] for k, v in TRANSFORM_FIELDS.items()}
    t.update(x=x, y=y, width=width, height=height, rotation=rotation,
             layer=layer, scale=scale)
    return t


def new_component(name):
    """按注册表创建一份组件默认字段字典。"""
    schema = COMPONENT_SCHEMAS[name]
    return {k: v["default"] for k, v in schema["fields"].items()}


def _clamp(value, spec):
    lo, hi = spec.get("min"), spec.get("max")
    if lo is not None and value < lo:
        value = lo
    if hi is not None and value > hi:
        value = hi
    return value


def validate_component(name, values):
    """按注册表字段类型规范化（int/float 强转 + 范围裁剪）。

    返回 (ok, 修正后字典, 错误信息)。未提供的字段用默认值补齐。
    """
    schema = COMPONENT_SCHEMAS.get(name)
    if schema is None:
        return False, values, "未知组件: %s" % name
    out = {}
    for key, spec in schema["fields"].items():
        raw = values.get(key, spec["default"])
        ftype = spec["type"]
        if ftype == "int":
            try:
                out[key] = _clamp(int(float(raw)), spec)
            except (TypeError, ValueError):
                return False, values, "%s.%s 需要整数，得到 %r" % (name, key, raw)
        elif ftype == "float":
            try:
                out[key] = _clamp(float(raw), spec)
            except (TypeError, ValueError):
                return False, values, "%s.%s 需要数字，得到 %r" % (name, key, raw)
        elif ftype == "bool":
            out[key] = bool(raw)
        elif ftype == "choice":
            if raw not in spec.get("options", []):
                out[key] = spec["default"]
            else:
                out[key] = raw
        else:  # text / color / file / prefab / entity
            out[key] = str(raw) if raw is not None else spec["default"]
    return True, out, ""
