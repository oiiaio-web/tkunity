# -*- coding: utf-8 -*-
"""命令行入口。

用法：
    tkunity                         # 启动图形编辑器
    tkunity edit [文件.pyu]         # 同上，可带文件
    tkunity new 游戏.pyu            # 新建一个空项目
    tkunity run 游戏.pyu            # 直接运行（桌面预览）
    tkunity build 游戏.pyu -o 输出目录   # 导出 Android APK 工程
    tkunity validate 游戏.pyu       # 校验项目（组件 / 父子环 / 预制体引用）
    tkunity info                    # 环境信息
"""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__


def _print_error(msg):
    sys.stderr.write("[tkunity] 错误: %s\n" % msg)


def cmd_edit(args):
    from .editor import launch_editor
    launch_editor(args.file, splash=not getattr(args, "no_splash", False))


def cmd_new(args):
    from . import pyu
    if os.path.exists(args.output):
        _print_error("文件已存在: %s" % args.output)
        return 1
    project = pyu.new_project(args.name or os.path.splitext(os.path.basename(args.output))[0],
                              args.width, args.height, args.background)
    pyu.save(project, args.output)
    print("[tkunity] 已创建项目: %s" % os.path.abspath(args.output))
    print("  下一步: tkunity edit %s" % args.output)
    return 0


def cmd_run(args):
    from . import pyu, three, ui
    from .runtime import Scene, Scene3DPreview
    if not os.path.isfile(args.input):
        _print_error("找不到项目文件: %s" % args.input)
        return 1
    project = pyu.load(args.input)
    import tkinter as tk
    root = tk.Tk()
    ui.apply_theme(root)
    root.title("tkunity - %s" % project["meta"].get("name", "游戏"))
    is3d = three.has_3d(project)
    if is3d:
        preview = Scene3DPreview(root, project)
        preview.canvas.pack(fill=tk.BOTH, expand=True)
        bar = tk.Frame(root, bg=ui.COLORS["panel"])
        bar.pack(fill=tk.X)
        ui.flat_button(bar, "自动环绕",
                       lambda: setattr(preview, "auto_orbit", not preview.auto_orbit),
                       kind="ghost").pack(side=tk.LEFT, padx=4, pady=4)
        ui.flat_button(bar, "重置视角", preview.restart, kind="ghost").pack(side=tk.LEFT, padx=4)
        ui.flat_button(bar, "退出", root.destroy, kind="default").pack(side=tk.LEFT, padx=4)
        root.protocol("WM_DELETE_WINDOW", lambda: (preview.stop(), root.destroy()))
        preview.start()
        root.mainloop()
        return 0
    scene = Scene(root, project)
    scene.canvas.pack(fill="both", expand=True)
    bar = tk.Frame(root, bg=ui.COLORS["panel"])
    bar.pack(fill=tk.X)
    ui.flat_button(bar, "暂停 / 继续",
                   lambda: (scene.resume() if scene.paused else scene.pause()),
                   kind="ghost").pack(side=tk.LEFT, padx=4, pady=4)
    ui.flat_button(bar, "重启", scene.restart, kind="ghost").pack(side=tk.LEFT, padx=4)
    ui.flat_button(bar, "退出", root.destroy, kind="default").pack(side=tk.LEFT, padx=4)
    root.protocol("WM_DELETE_WINDOW", lambda: (scene.stop(), root.destroy()))
    scene.start()
    root.mainloop()
    return 0


def cmd_build(args):
    from . import export, pyu
    if not os.path.isfile(args.input):
        _print_error("找不到项目文件: %s" % args.input)
        return 1
    project = pyu.load(args.input)
    outdir = args.output or os.path.join(
        os.path.dirname(os.path.abspath(args.input)),
        "android_build_" + project["meta"].get("name", "game"))
    warnings = []
    files = export.build(project, outdir, package=args.package, warnings=warnings)
    print("[tkunity] 已生成 Android 工程（%d 个文件）:" % len(files))
    for f in files:
        print("   ", f)
    if warnings:
        print("\n[tkunity] 脚本编译警告（这些钩子不会在 APK 里执行）:")
        for w in warnings:
            print("   - %s" % w)
    print("\n下一步:")
    print("  1) 安装 JDK 17 与 Android SDK，并设置 ANDROID_HOME")
    print("     （或在该目录创建 local.properties: sdk.dir=你的SDK路径）")
    print("  2) Windows: 双击 build_apk.bat   或   执行 ./build_apk.sh")
    print("  3) 产物: app/build/outputs/apk/debug/app-debug.apk")
    return 0


def cmd_validate(args):
    """校验项目结构，返回 0 表示没问题。"""
    from . import pyu
    from .components import COMPONENT_SCHEMAS, validate_component
    if not os.path.isfile(args.input):
        _print_error("找不到项目文件: %s" % args.input)
        return 1
    project = pyu.load(args.input)
    issues = []
    names = {}
    for entity in project["entities"]:
        names.setdefault(entity.get("name"), []).append(entity.get("id"))
        comps = entity.get("components", {})
        if "Transform" not in comps:
            issues.append("%s: 缺少 Transform" % entity.get("name"))
        for cname, values in comps.items():
            if cname not in COMPONENT_SCHEMAS:
                issues.append("%s: 未知组件 %s" % (entity.get("name"), cname))
                continue
            ok, _fixed, err = validate_component(cname, values)
            if not ok:
                issues.append("%s: %s" % (entity.get("name"), err))
    for name, ids in names.items():
        if len(ids) > 1:
            issues.append("名字重复: %s x%d" % (name, len(ids)))
    # 父子环
    for entity in project["entities"]:
        seen = set()
        node = entity
        while node is not None and node.get("parent") is not None:
            if node["id"] in seen:
                issues.append("父子成环: %s" % entity.get("name"))
                break
            seen.add(node["id"])
            node = pyu.entity_by_id(project, node.get("parent"))
        if node is None:
            issues.append("父物体不存在: %s" % entity.get("name"))
    prefabs = set(pyu.prefab_names(project))
    for entity in project["entities"]:
        spawner = entity.get("components", {}).get("Spawner")
        if spawner and spawner.get("prefab") and spawner["prefab"] not in prefabs:
            issues.append("%s: 生成器引用了不存在的预制体 %s"
                          % (entity.get("name"), spawner["prefab"]))
        camera = entity.get("components", {}).get("Camera2D")
        if camera and camera.get("follow") and camera["follow"] not in names:
            issues.append("%s: 摄像机跟随目标不存在: %s"
                          % (entity.get("name"), camera["follow"]))

    # 脚本能否导出到 APK（ScriptVM 支持的语法子集）
    from .script import compile_project
    _programs, script_warnings = compile_project(project)
    for warning in script_warnings:
        issues.append("脚本无法导出到 APK —— %s" % warning)

    print("[tkunity] 项目: %s" % project["meta"].get("name"))
    print("  物体 %d 个 / 预制体 %d 个 / 资源 %d 个"
          % (len(project["entities"]), len(prefabs), len(project.get("assets", {}))))
    meshes = [e for e in project["entities"]
              if e.get("components", {}).get("Mesh3D")]
    if meshes:
        print("  含 %d 个 3D 物体：桌面端可编辑/预览，APK 导出会跳过它们" % len(meshes))
    if issues:
        print("  发现 %d 个问题:" % len(issues))
        for issue in issues:
            print("   - %s" % issue)
        return 1
    print("  校验通过 ✓")
    return 0


def cmd_info(args):
    import tkinter
    from .components import COMPONENT_SCHEMAS, PARTS
    print("tkunity %s" % __version__)
    print("Python: %s" % sys.version.split()[0])
    print("tkinter: %s (Tk %s)" % (tkinter.__file__, tkinter.TkVersion))
    print("平台: %s" % sys.platform)
    print("组件: %d 种（%s）" % (len(COMPONENT_SCHEMAS), " / ".join(COMPONENT_SCHEMAS)))
    print("零件: %s" % " / ".join(p[0] for p in PARTS))
    return 0


def _add_help_alias(parser):
    """为 parser 增加 -help 别名（与内置 -h / --help 功能一致）。"""
    parser.add_argument("-help", action="help",
                        help="显示帮助并退出（同 -h / --help）")


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="tkunity",
        description="tkunity %s - Unity 风格 2D / 3D 游戏编辑器（纯标准库，可导出 Android APK 工程）" % __version__,
    )
    _add_help_alias(parser)
    sub = parser.add_subparsers(dest="command")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    parser.add_argument("--no-splash", action="store_true", default=False,
                        help="启动编辑器时不显示开屏动画")

    p_edit = sub.add_parser("edit", help="启动图形编辑器（可带 .pyu 文件）")
    _add_help_alias(p_edit)
    p_edit.add_argument("file", nargs="?", default=None)
    p_edit.add_argument("--no-splash", action="store_true", default=False,
                        help="不显示开屏动画")
    p_edit.set_defaults(func=cmd_edit)

    p_new = sub.add_parser("new", help="新建一个空项目")
    _add_help_alias(p_new)
    p_new.add_argument("output", help="输出文件（.pyu）")
    p_new.add_argument("--name", default=None, help="项目名")
    p_new.add_argument("--width", type=int, default=960)
    p_new.add_argument("--height", type=int, default=640)
    p_new.add_argument("--background", default="#1e1e2e")
    p_new.set_defaults(func=cmd_new)

    p_run = sub.add_parser("run", help="直接运行项目（桌面预览窗口）")
    _add_help_alias(p_run)
    p_run.add_argument("input", help="项目文件（.pyu）")
    p_run.set_defaults(func=cmd_run)

    p_build = sub.add_parser("build", help="把 .pyu 游戏导出为 Android APK 工程")
    _add_help_alias(p_build)
    p_build.add_argument("input", help="项目文件（.pyu）")
    p_build.add_argument("-o", "--output", default=None, help="输出目录")
    p_build.add_argument("--package", default="com.oiiaio.tkunity", help="Android 包名")
    p_build.set_defaults(func=cmd_build)

    p_val = sub.add_parser("validate", help="校验项目（组件 / 父子环 / 引用）")
    _add_help_alias(p_val)
    p_val.add_argument("input", help="项目文件（.pyu）")
    p_val.set_defaults(func=cmd_validate)

    p_info = sub.add_parser("info", help="显示环境信息")
    _add_help_alias(p_info)
    p_info.set_defaults(func=cmd_info)

    return parser


def show_help():
    """打印主帮助文本（等价命令行 tkunity -h / -help / --help）。"""
    _build_parser().print_help()


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) is None or not hasattr(args, "func"):
        cmd_edit(argparse.Namespace(file=None))
        return 0
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
