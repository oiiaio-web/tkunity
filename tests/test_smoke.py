# -*- coding: utf-8 -*-
"""tkunity 冒烟测试：直接 python tests/test_smoke.py 运行（无需第三方依赖）。

覆盖：.pyu 往返与迁移、组件校验、父子层级、预制体、导出工程、导出 Java 结构、
命令行校验、运行时物理 / 触发器 / 生成器 / 脚本（有 Tk 时）。
"""
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tkunity import Project, GameObject, load, save, world
from tkunity import components, pyu
from tkunity import export
from tkunity.components import validate_component

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  [OK] %s" % name)
    else:
        FAILED.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def tk_root():
    """有显示环境时返回 Tk 根窗口，否则 None。"""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        return root
    except Exception:
        return None


# ---------------------------------------------------------------- 基础
def test_pyu_roundtrip():
    print("test_pyu_roundtrip")
    p = Project(name="测试", scene_width=800, scene_height=600, background="#0f0f1a")
    ball = GameObject("ball", x=100, y=100, width=50, height=50)
    ball.add_sprite("oval", fill="#ff0000", outline="#ffff00")
    ball.add_timer(16, "bounce")
    ball.add_tap("print('hi')")
    p.add(ball)

    label = GameObject("title", x=10, y=10, width=300, height=40)
    label.add_label("你好 tkunity", font_size=24, color="#ffffff", bold=True)
    p.add(label)

    path = os.path.join(tempfile.mkdtemp(), "t.pyu")
    save(p, path)
    with open(path, "rb") as fh:
        raw = fh.read()
    check("魔数头", raw.startswith(pyu.MAGIC))

    proj = load(path)
    check("meta 完整", proj["meta"]["scene_width"] == 800 and proj["meta"]["background"] == "#0f0f1a")
    check("实体数=2", len(proj["entities"]) == 2)
    e0 = proj["entities"][0]
    check("Transform 字段", e0["components"]["Transform"]["x"] == 100)
    check("Timer 字段", e0["components"]["Timer"]["action"] == "bounce")
    check("Label 字段", proj["entities"][1]["components"]["Label"]["text"] == "你好 tkunity")
    check("新字段 tag/active/parent", e0.get("tag") == "Untagged" and e0.get("active") is True
          and e0.get("parent") is None)
    check("prefabs 段", "prefabs" in proj)


def test_migrate_old_project():
    print("test_migrate_old_project")
    old = {
        "meta": {"name": "老项目", "scene_width": 320, "scene_height": 240},
        "entities": [
            {"id": 1, "name": "旧物体",
             "components": {"Transform": {"x": 5, "y": 6, "width": 10, "height": 10,
                                          "rotation": 0.0, "layer": 0}}},
        ],
    }
    path = os.path.join(tempfile.mkdtemp(), "old.pyu")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(old, fh, ensure_ascii=False)
    proj = load(path)
    e = proj["entities"][0]
    check("补齐 tag", e.get("tag") == "Untagged")
    check("补齐 scale", e["components"]["Transform"].get("scale") == 1.0)
    check("补齐 gravity", proj["meta"].get("gravity", 0) > 0)


def test_validate_component():
    print("test_validate_component")
    ok, fixed, err = validate_component("Transform", {"x": "42", "width": "3.7"})
    check("int 强转", ok and fixed["x"] == 42 and fixed["width"] == 3 and err == "", err)
    ok, _, err = validate_component("Transform", {"x": "abc"})
    check("非法 int 拒绝", not ok and "整数" in err, err)
    ok, fixed, err = validate_component("Sprite", {"shape": "oval"})
    check("choice 合法", ok and fixed["shape"] == "oval", err)
    ok, fixed, err = validate_component("Sprite", {"shape": "triangle"})
    check("choice 非法回退默认", ok and fixed["shape"] == "rect", err)
    ok, fixed, err = validate_component("Sprite", {"opacity": 9})
    check("float 上限裁剪", ok and fixed["opacity"] == 1.0, err)
    ok, fixed, err = validate_component("Rigidbody2D", {"body_type": "kinematic"})
    check("刚体类型", ok and fixed["body_type"] == "kinematic", err)
    ok, fixed, err = validate_component("BoxCollider2D", {"is_trigger": 1})
    check("触发器 bool", ok and fixed["is_trigger"] is True, err)
    ok, _, err = validate_component("NoSuchComponent", {})
    check("未知组件拒绝", not ok and "未知" in err, err)


def test_image_embed():
    print("test_image_embed")
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    p = Project(name="图片测试")
    d = tempfile.mkdtemp()
    img = os.path.join(d, "dot.png")
    with open(img, "wb") as fh:
        fh.write(png)
    name = p.embed_image(img)
    check("资源已内嵌", name in p.to_dict()["assets"])
    photo_ok = True
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        photo = pyu.asset_to_photo(p.to_dict()["assets"][name])
        photo_ok = photo.width() == 1
        root.destroy()
    except Exception as exc:
        if "display" in str(exc).lower() or "no display" in str(exc).lower():
            print("      （无显示环境，跳过 PhotoImage 实测）")
        else:
            photo_ok = False
            print("      [photo 解析异常] %s" % exc)
    check("base64 可被 PhotoImage 解析", photo_ok)


# ---------------------------------------------------------------- 层级 / 物理模型
def test_hierarchy():
    print("test_hierarchy")
    p = Project(name="层级", scene_width=800, scene_height=600)
    parent = GameObject("父", x=100, y=50, width=40, height=40)
    parent.transform["scale"] = 2.0
    p.add(parent)
    child = GameObject("子", x=10, y=10, width=20, height=20)
    p.add(child, parent=parent)

    proj = p.to_dict()
    r = world.rect_of(child._project._project["entities"][1], proj)
    check("子物体世界坐标", (r[0], r[1]) == (120.0, 70.0), str(r))
    check("子物体世界尺寸", (r[2] - r[0], r[3] - r[1]) == (40.0, 40.0), str(r))

    order = [e["name"] for e in world.draw_order(proj)]
    check("父在前子在后", order.index("父") < order.index("子"), str(order))

    eid_parent = proj["entities"][0]["id"]
    eid_child = proj["entities"][1]["id"]
    check("层级命中测试", world.hit_test(proj, 125, 75) == eid_child)

    try:
        pyu.set_parent(proj, eid_parent, eid_child)
        cycle_ok = False
    except ValueError:
        cycle_ok = True
    check("禁止父子成环", cycle_ok)

    pyu.set_parent(proj, eid_child, None)
    check("解除父子", pyu.entity_by_id(proj, eid_child)["parent"] is None)

    ids = pyu.remove_entity(proj, eid_parent)
    check("级联删除", ids == [eid_parent] and len(proj["entities"]) == 1, str(ids))


def test_prefab():
    print("test_prefab")
    p = Project(name="预制体")
    ball = GameObject("球", 10, 10, 30, 30)
    ball.add_sprite("oval", fill="#ff0000")
    p.add(ball)
    name = p.save_prefab(ball, "ball")
    check("预制体已保存", name in p.prefabs, str(p.prefabs))
    inst = p.instantiate("ball", 100, 200)
    check("实例化成功", inst is not None and len(p.to_dict()["entities"]) == 2)
    check("实例位置", inst.transform["x"] == 100 and inst.transform["y"] == 200)
    check("实例名字不重复", inst.name != "球", inst.name)


# ---------------------------------------------------------------- 导出
def _strip_literals(src):
    src = re.sub(r'"(?:\\.|[^"\\])*"', '""', src)
    src = re.sub(r"'(?:\\.|[^'\\])*'", "''", src)
    return src


def test_export():
    print("test_export")
    p = Project(name="导出测试", scene_width=640, scene_height=480, background="#1e1e2e")
    ball = GameObject("ball", x=100, y=100, width=40, height=40)
    ball.add_sprite("oval", fill="#f38ba8", outline="#f9e2af")
    ball.add_timer(16, "bounce")
    ball.add_rigidbody(bounce=0.8)
    ball.add_collider()
    ball.add_animator("spin")
    ball.add_camera(follow="ball", zoom=1.2)
    p.add(ball)
    p.save_prefab(ball, "ball")

    outdir = os.path.join(tempfile.mkdtemp(), "android")
    files = export.build(p.to_dict(), outdir)
    check("文件数>=13", len(files) >= 13, str(len(files)))

    rel = lambda f: os.path.relpath(f, outdir).replace(os.sep, "/")
    must = ["settings.gradle", "build.gradle", "app/build.gradle",
            "app/src/main/AndroidManifest.xml",
            "app/src/main/java/com/oiiaio/tkunity/GameView.java",
            "app/src/main/java/com/oiiaio/tkunity/MainActivity.java",
            "app/src/main/assets/game.pyu",
            "build_apk.bat", "build_apk.sh"]
    for m in must:
        found = any(rel(f) == m for f in files)
        check("生成 %s" % m, found)

    pyu_path = os.path.join(outdir, "app", "src", "main", "assets", "game.pyu")
    with open(pyu_path, "rb") as fh:
        raw = fh.read()
    check("导出 pyu 魔数", raw.startswith(pyu.MAGIC))
    data = json.loads(raw[len(pyu.MAGIC):].decode("utf-8"))
    check("导出 pyu JSON 合法", data["meta"]["name"] == "导出测试")
    check("导出含预制体", "ball" in data.get("prefabs", {}))

    with open(os.path.join(outdir, "app", "build.gradle"), encoding="utf-8") as fh:
        gb = fh.read()
    check("app 无 dependencies 块", "dependencies {" not in gb)

    with open(os.path.join(outdir, "app", "src", "main", "java",
                           "com", "oiiaio", "tkunity", "GameView.java"), encoding="utf-8") as fh:
        jv = fh.read()
    check("Java 包名", "package com.oiiaio.tkunity;" in jv)
    check("Java 无 androidx 依赖", "androidx" not in jv)
    for feature in ("Rigidbody2D", "BoxCollider2D", "Camera2D", "Spawner",
                    "Animator", "prefabs", "onTouchEvent"):
        check("Java 支持 %s" % feature, feature in jv)

    stripped = _strip_literals(jv)
    check("Java 花括号配平", stripped.count("{") == stripped.count("}"),
          "%d vs %d" % (stripped.count("{"), stripped.count("}")))
    check("Java 圆括号配平", stripped.count("(") == stripped.count(")"),
          "%d vs %d" % (stripped.count("("), stripped.count(")")))

    # --- 脚本导出到 APK ---
    check("生成 ScriptVM.java", any(rel(f).endswith("ScriptVM.java") for f in files))
    with open(os.path.join(outdir, "app", "src", "main", "java",
                           "com", "oiiaio", "tkunity", "ScriptVM.java"), encoding="utf-8") as fh:
        svm = fh.read()
    check("ScriptVM 无 androidx 依赖", "androidx" not in svm)
    vm_stripped = _strip_literals(svm)
    check("ScriptVM 括号配平", vm_stripped.count("{") == vm_stripped.count("}")
          and vm_stripped.count("(") == vm_stripped.count(")"))
    check("GameView 调用脚本钩子", 'runHook(hit, "on_tap"' in jv and '"on_update"' in jv)

    # --- .bat 必须是纯 ASCII（否则 CMD 按 GBK 解析会截断命令）---
    bat_path = os.path.join(outdir, "build_apk.bat")
    with open(bat_path, "rb") as fh:
        bat_bytes = fh.read()
    check("bat 纯 ASCII", all(b < 128 for b in bat_bytes))
    check("bat 无 BOM", not bat_bytes.startswith(b"\xef\xbb\xbf"))
    check("bat 首行 @echo off", bat_bytes.startswith(b"@echo off"))

    # --- gradle 兼容性 ---
    with open(os.path.join(outdir, "gradle.properties"), encoding="utf-8") as fh:
        gp = fh.read()
    check("gradle 允许中文路径", "android.overridePathCheck=true" in gp)
    with open(os.path.join(outdir, "settings.gradle"), encoding="utf-8") as fh:
        sg = fh.read()
    check("settings 用 PREFER_SETTINGS", "RepositoriesMode.PREFER_SETTINGS" in sg
          and "FAIL_ON_PROJECT_REPOS" not in sg)


def test_script_compiler():
    print("test_script_compiler")
    from tkunity import script as sc

    prog = sc.compile_script("x = x + 1\nif x > 2:\n    log('big ' + str(x))")
    check("编译产出 AST", prog and prog["stmts"][0]["t"] == "assign")

    env = {"x": 1}
    class Host(object):
        def __init__(self):
            self.logs = []

        def call(self, fn, args):
            if fn == "log":
                self.logs.append(args[0])
                return None
            if fn == "str":
                value = args[0]
                if isinstance(value, float) and value.is_integer():
                    return str(int(value))
                return str(value)
            return None

        def log(self, message):
            self.logs.append(message)

    host = Host()
    sc.evaluate(prog, env, host)
    check("参考求值器执行", env["x"] == 2, str(env))

    env2 = {"x": 5}
    host2 = Host()
    sc.evaluate(sc.compile_script("if x > 2:\n    log('big ' + str(x))"), env2, host2)
    check("字符串拼接与调用", host2.logs == ["big 5"], str(host2.logs))

    env3 = {"x": 0}
    sc.evaluate(sc.compile_script("for i in range(4):\n    x += i"), env3, Host())
    check("for/range", env3["x"] == 6, str(env3))

    env4 = {"x": 0}
    sc.evaluate(sc.compile_script("i = 0\nwhile i < 3:\n    i += 1\n    if i == 2:\n        continue\n    x += 1"), env4, Host())
    check("while/continue", env4["x"] == 2, str(env4))

    for bad in ("import os", "def f():\n    pass", "x = [1, 2]", "x = a.b", "x = d['k']"):
        try:
            sc.compile_script(bad)
            ok = False
        except sc.ScriptError:
            ok = True
        check("拒绝不支持的语法: %s" % bad.split("\n")[0], ok)

    # 项目级编译：能警告、能跳过
    p = Project(name="脚本项目")
    obj = GameObject("对象", 10, 10, 20, 20)
    obj.add_sprite("rect")
    obj.add_script(on_update="x += 1", on_tap="print('unsupported call')")
    p.add(obj)
    programs, warnings = sc.compile_project(p.to_dict())
    eid = str(p.to_dict()["entities"][0]["id"])
    check("compile_project 收集钩子", eid in programs and "on_update" in programs[eid])
    check("compile_project 收集警告", len(warnings) == 1 and "on_tap" in warnings[0], str(warnings))


# ---------------------------------------------------------------- 命令行
def test_cli():
    print("test_cli")
    from tkunity import cli
    d = tempfile.mkdtemp()
    path = os.path.join(d, "cli.pyu")
    check("new 命令", cli.main(["new", path, "--name", "命令行"]) == 0)
    check("文件已生成", os.path.isfile(path))
    check("validate 通过", cli.main(["validate", path]) == 0)

    data = load(path)
    data["entities"].append({"id": 9, "name": "坏物体",
                             "components": {"Transform": {"x": 0, "y": 0, "width": 10, "height": 10},
                                            "Ghost": {}}})
    with open(path, "wb") as fh:
        fh.write(pyu.MAGIC + json.dumps(data).encode("utf-8"))
    check("validate 能报错", cli.main(["validate", path]) == 1)

    # 脚本超出 APK 子集时，validate 也要报出来
    data = load(path)
    data["entities"] = [{"id": 1, "name": "脚本物体", "tag": "Untagged", "active": True,
                         "parent": None,
                         "components": {"Transform": {"x": 0, "y": 0, "width": 10, "height": 10,
                                                      "rotation": 0.0, "scale": 1.0, "layer": 0},
                                        "Script": {"name": "s", "on_update": "import os"}}}]
    with open(path, "wb") as fh:
        fh.write(pyu.MAGIC + json.dumps(data, ensure_ascii=False).encode("utf-8"))
    check("validate 报告脚本问题", cli.main(["validate", path]) == 1)


# ---------------------------------------------------------------- 运行时
def test_runtime_engine():
    print("test_runtime_engine")
    root = tk_root()
    if root is None:
        print("  （无显示环境，跳过运行时集成测试）")
        return
    try:
        from tkunity.runtime import Scene
        p = Project(name="引擎", scene_width=400, scene_height=300, gravity=1000)

        ground = GameObject("地面", 0, 260, 400, 40)
        ground.add_sprite("rect").add_collider()
        p.add(ground)

        ball = GameObject("球", 180, 0, 40, 40)
        ball.add_sprite("oval")
        ball.add_rigidbody(gravity_scale=1.0, bounce=0.0).add_collider()
        p.add(ball)

        zone = GameObject("区域", 0, 240, 400, 60)
        zone.add_collider(is_trigger=True)
        zone.add_script(on_collision="log('enter ' + str(other.get('name')))")
        p.add(zone)

        coin = GameObject("金币", 0, 0, 10, 10)
        coin.add_sprite("oval")
        p.add(coin)
        p.save_prefab(coin, "coin")
        p.remove(coin)

        spawner = GameObject("刷子", 10, 10, 10, 10)
        spawner.add_spawner("coin", interval_ms=100, max_alive=3)
        p.add(spawner)

        scene = Scene(root, p.to_dict())
        scene.start()
        scene.stop()
        for _ in range(200):
            scene.step()

        ball_entity = scene.find("球")
        y = ball_entity["components"]["Transform"]["y"]
        check("重力下落并被地面挡住", 200 <= y <= 260, "y=%.1f" % y)
        check("触发器回调触发", any("enter" in line for line in scene.logs), str(scene.logs[:3]))
        coins = [e for e in scene.project["entities"] if e["name"].startswith("coin")]
        check("生成器生成实例", len(coins) >= 1, str([e["name"] for e in scene.project["entities"]]))
        check("spawner 有数量上限", len(coins) <= 3, "coins=%d" % len(coins))

        scene.pause()
        scene.step()
        scene.resume()
        scene.restart()
        check("重启后恢复物体数", len(scene.project["entities"]) == 4)
        scene.stop()
    finally:
        root.destroy()


def test_actions_and_scripts():
    print("test_actions_and_scripts")
    root = tk_root()
    if root is None:
        print("  （无显示环境，跳过动作/脚本测试）")
        return
    try:
        from tkunity.runtime import Scene, execute_action_expression
        p = Project(name="动作", scene_width=400, scene_height=300)
        hero = GameObject("英雄", 100, 100, 40, 40)
        hero.add_sprite("rect")
        hero.add_script(on_update="x += 10 * dt\nif x > 300: vx = 0",
                        on_start="log('started')")
        p.add(hero)
        scene = Scene(root, p.to_dict())
        scene.start()
        scene.stop()
        scene.dt = 0.1
        scene.elapsed = 0.1
        scene.simulate()
        x_after = scene.find("英雄")["components"]["Transform"]["x"]
        check("脚本 on_update 生效", x_after > 100, "x=%s" % x_after)
        check("脚本 on_start 日志", any("started" in line for line in scene.logs))

        entity = scene.find("英雄")
        rt = scene.runtimes[entity["id"]]
        scene._run_action(rt, "jump")
        check("jump 动作", rt.vy < 0, str(rt.vy))
        scene._run_action(rt, "stop")
        check("stop 动作", rt.vx == 0 and rt.vy == 0)
        scene._run_action(rt, "none")
        check("none 动作不报错", True)

        ent = {"components": {"Transform": {"x": 1, "y": 2, "width": 3, "height": 4}}}
        ok = execute_action_expression(ent, "x += 5")
        check("表达式动作兼容", ok and ent["components"]["Transform"]["x"] == 6)
        check("坏表达式返回 False", execute_action_expression(ent, "x = ") is False)
        scene.stop()
    finally:
        root.destroy()


def test_runtime_import():
    print("test_runtime_import")
    try:
        import tkunity.runtime as rt
        check("runtime 可导入", hasattr(rt, "Scene") and hasattr(rt, "execute_action_expression"))
    except Exception as exc:
        check("runtime 可导入", False, str(exc))


def test_three():
    print("test_three")
    from tkunity import three

    check("内置网格齐全",
          all(name in three.MESHES for name in ("cube", "sphere", "plane", "pyramid", "cylinder")))
    check("立方体 8 顶点 6 面",
          len(three.MESHES["cube"].vertices) == 8 and len(three.MESHES["cube"].faces) == 6)

    cam = three.Camera(yaw=35, pitch=20, distance=6, target=(0, 0.5, 0))
    view = three.View(cam, 400, 300)
    center = view.project((0, 0.5, 0))
    check("目标点投影居中", center is not None
          and abs(center[0] - 200) < 1 and abs(center[1] - 150) < 1, str(center))
    check("相机后方的点被裁剪", view.project((0, 0.5, 1000)) is None)

    p = Project(name="3D", scene_width=400, scene_height=300)
    cube = GameObject("方块", 0, 0, 60, 60)
    cube.set_component("Transform3D", x=0.0, y=0.5, z=0.0, scale=1.0)
    cube.set_component("Mesh3D", shape="cube", color="#89b4fa")
    p.add(cube)
    data = p.to_dict()
    check("has_3d 检测", three.has_3d(data))
    tf = three.transform3d_of(data["entities"][0])
    check("Transform3D 读取", tf["y"] == 0.5 and tf["scale"] == 1.0, str(tf))
    check("网格顶点数", len(three.entity_vertices(data["entities"][0])) == 8)
    eid = three.pick(data, cam, 400, 300, 200, 150)
    check("3D 拾取命中", eid == data["entities"][0]["id"], str(eid))
    check("空场景 has_3d 为假", not three.has_3d(Project(name="空").to_dict()))

    # 颜色工具
    check("颜色解析", three.hex_to_rgb("#ff8000") == (255, 128, 0))
    check("颜色变暗", three.rgb_to_hex(three.hex_to_rgb(three.shade("#ffffff", 0.5))) == "#7f7f7f")


def test_splash():
    print("test_splash")
    from tkunity import splash

    check("splash_enabled 默认开启", splash.splash_enabled([], {}))
    check("splash 支持 --no-splash", not splash.splash_enabled(["--no-splash"], {}))
    check("splash 支持环境变量", not splash.splash_enabled([], {"TKUNITY_NO_SPLASH": "1"}))

    root = tk_root()
    if root is None:
        print("  （无显示环境，跳过 splash 实际绘制）")
        return
    try:
        done = {"called": False}

        def on_done():
            done["called"] = True

        screen = splash.SplashScreen(root, duration_ms=200, on_done=on_done, version="test")
        screen._draw(0.5)
        screen.close()
        check("splash 可创建并关闭", done["called"])
    finally:
        root.destroy()


def test_editor_3d():
    print("test_editor_3d")
    root = tk_root()
    if root is None:
        print("  （无显示环境，跳过编辑器 3D 测试）")
        return
    try:
        from tkunity.editor import EditorApp
        app = EditorApp(root)
        app.set_mode("3d")
        check("模式切换", app.mode == "3d")
        app._place_part_3d("立方体")
        check("放置 3D 零件", len(app.project["entities"]) == 1)
        entity = app.project["entities"][0]
        check("带 Mesh3D", entity["components"].get("Mesh3D", {}).get("shape") == "cube")
        check("带 Transform3D", "Transform3D" in entity["components"])

        app.select(entity["id"])
        app._refresh_props()
        app._prop_vars[("Transform3D", "x")].set("2.5")
        app.apply_props()
        check("Inspector 改 3D 坐标", entity["components"]["Transform3D"]["x"] == 2.5,
              str(entity["components"]["Transform3D"]))

        app.duplicate_selection()
        check("3D 复制", len(app.project["entities"]) == 2)
        app.delete_selection()
        check("3D 删除", len(app.project["entities"]) == 1)
        app.undo()
        app.undo()
        check("3D 撤销", len(app.project["entities"]) == 1)

        app.set_mode("2d")
        app.redraw_all()
        app.set_mode("3d")
        check("切回 3D 正常", app.mode == "3d")
        root.update()
    finally:
        root.destroy()


def test_export_3d_warning():
    print("test_export_3d_warning")
    p = Project(name="3D 导出")
    cube = GameObject("方块", 0, 0, 60, 60)
    cube.set_component("Transform3D", x=0.0, y=0.5, z=0.0)
    cube.set_component("Mesh3D", shape="cube")
    p.add(cube)
    warnings = []
    outdir = os.path.join(tempfile.mkdtemp(), "android3d")
    files = export.build(p.to_dict(), outdir, warnings=warnings)
    check("3D 导出仍产出工程", len(files) >= 13, str(len(files)))
    check("3D 导出给出警告", any("3D" in w for w in warnings), str(warnings))


def main():
    print("== tkunity 冒烟测试 ==")
    test_pyu_roundtrip()
    test_migrate_old_project()
    test_validate_component()
    test_image_embed()
    test_hierarchy()
    test_prefab()
    test_export()
    test_script_compiler()
    test_three()
    test_splash()
    test_editor_3d()
    test_export_3d_warning()
    test_cli()
    test_runtime_engine()
    test_actions_and_scripts()
    test_runtime_import()
    print()
    if FAILED:
        print("失败项(%d): %s" % (len(FAILED), ", ".join(FAILED)))
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
