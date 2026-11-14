# tkunity

> 纯标准库、零第三方依赖（不需要 pygame / numpy）的 **Unity 风格 2D + 3D 游戏编辑器 + 运行时**，
> 把你在编辑器里拼出来的 `.pyu` 游戏一键导出成 **Android APK 工程**。

- **许可证**：Apache License 2.0
- **作者**：oiiaio-web <3926580760@qq.com>
- **版本**：2026.11.4
- **Python**：>= 3.8（已在 3.8 / 3.14 / 3.15 / 3.16 上测试）
- **依赖**：**零**。只使用标准库 `tkinter / json / base64 / argparse / math`。Linux 上若缺少 tk 图形环境，请安装系统包 `python3-tk`（这不是 pip 依赖）。

---

## 版本号规则

版本号形如 **`YYYY.M.N`**，三段都是「日历 + 计数」，**不是** 语义化的 主.次.补丁：

```
2026 . 11 . 4
 │      │    └── 该月的第几个发布版本（这里是 11 月的第 4 个版本）
 │      └─────── 月份（11 月）
 └────────────── 年份（2026 年）
```

- `2026.11.1` = 2026 年 11 月的**第 1 个**版本
- `2026.11.2` = 2026 年 11 月的第 2 个版本
- `2026.11.3` = 2026 年 11 月的第 3 个版本
- `2026.11.4` = 2026 年 11 月的**第 4 个**版本（本版）
- `2026.12.1` = 2026 年 12 月的第 1 个版本

所以第三段只是「当月第几发」，不代表兼容性等级；同一个 `YYYY.M` 下的相邻版本都保证 `.pyu` 文件向后兼容（旧文件能直接打开，读入时自动补齐新字段）。

**预发布**沿用 PEP 440 的 `devN` 后缀，例如 `2026.11.2.dev0` 表示「2026 年 11 月第 2 版之前的开发快照 0」。
按 PEP 440 排序 `2026.11.2.dev0 < 2026.11.2`，因此 `pip install tkunity` 默认只会装正式版，预发布需要 `pip install --pre tkunity` 或精确指定版本。

---

## 一、这一版「更像 Unity」的地方

| Unity 概念 | tkunity 对应实现 |
|---|---|
| GameObject + Component | 实体 + 可增删组件（组件表驱动，Inspector 自动生成） |
| Transform 父子层级 | 实体 `parent` 字段，子物体跟随父物体的位移与缩放 |
| Prefab | 预制体库：存 / 实例化 / 生成器批量刷怪 |
| Rigidbody2D | 刚体：重力、速度、阻尼、弹性、dynamic / kinematic / static |
| BoxCollider2D | AABB 碰撞推出 + 触发器（`on_collision` 回调） |
| MonoBehaviour | Script 组件：`on_start / on_update / on_tap / on_collision / on_destroy` |
| Camera | Camera2D 跟随缩放；Camera3D 轨道相机 |
| Animator | Animator：spin / pulse / fade / slide / float 补间 |
| **3D 场景** | **Mesh3D + Transform3D：立方体 / 球体 / 平面 / 棱锥 / 圆柱，软件渲染视口** |
| Scene View | 3D 视口：环绕、平移、缩放、点选、拖动 |
| Tag | 每个物体的 `tag` 标签，可按标签筛选 |
| Play / Pause / Step | 预览窗口的暂停·继续、单步、重启（3D 预览支持自动环绕） |
| Hierarchy / Inspector / Console | 编辑器左树 / 右属性面板 / 底部控制台 |
| Undo / Redo | Ctrl+Z / Ctrl+Y（60 步快照） |
| Splash | 启动开屏动画（旋转立方体 + 进度条，可跳过） |

---

## 二、安装

```bash
pip install tkunity        # 从 PyPI
# 或从源码目录
pip install -e .
tkunity --version          # 查看版本
tkunity -h / -help / --help   # 三种写法功能一样
```

不需要 pygame、不需要 Kivy、不需要任何 pip 第三方包（3D 视口也是纯 tkinter 软件渲染）。

启动编辑器时会先播一段约 1.5 秒的开屏动画；不想看可以：

```bash
tkunity --no-splash          # 本次跳过
set TKUNITY_NO_SPLASH=1      # Windows 环境变量，长期跳过
```

---

## 三、命令行

```bash
tkunity                          # 打开图形编辑器
tkunity edit examples/demo.pyu   # 打开编辑器并载入项目
tkunity new 游戏.pyu --width 960 --height 640
tkunity run 游戏.pyu             # 直接运行（桌面预览）
tkunity validate 游戏.pyu        # 校验组件 / 父子环 / 预制体引用
tkunity build 游戏.pyu -o out    # 导出 Android 工程
tkunity info                     # 环境与组件信息
```

---

## 四、编辑器

```
┌──────────────────── 工具栏：文件 / 撤销重做 / 预览 / 导出 ─────────────────────┐
│ 层级(父子树) │         场景画布（缩放 / 网格吸附）        │  Inspector        │
│ ＋空物体     │                                           │  名称 / 标签 / 激活 │
│ 零件库       │                                           │  父物体            │
│ 预制体       │                                           │  各组件字段        │
├──────────────┴───────────────────────────────────────────┴───────────────────┤
│ 控制台（运行日志 / 脚本输出）                                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

**常用操作**

| 操作 | 方式 |
|---|---|
| 放置零件 | 左侧零件库单击 → 画布单击；或双击零件放到画布中心 |
| 选中 / 拖动 / 缩放 | 画布单击物体、拖拽移动、右下角绿点缩放 |
| 精确改数值 | 右侧 Inspector 改字段 → 点「应用」 |
| 添加 / 移除组件 | Inspector 底部下拉「添加组件」；组件标题栏「移除」 |
| 建立父子 | 先选中子物体，在 Inspector「父物体」下拉里选父级 |
| 存预制体 | Inspector「存为预制体」 |
| 实例化预制体 | 左下预制体列表双击 |
| 复制 / 删除 | Ctrl+D / Delete |
| 微调位置 | 方向键（一次一格） |
| 撤销 / 重做 | Ctrl+Z / Ctrl+Y |
| 切换 2D / 3D | 顶部「2D 场景 / 3D 场景」按钮，或 Ctrl+1 / Ctrl+2 |
| 试玩 | 工具栏「预览」→ 暂停 / 继续、单步、重启 |

### 3D 场景

顶部切到 **3D 场景** 后，中间变成软件渲染的 3D 视口（不依赖任何 3D 库）：

| 操作 | 方式 |
|---|---|
| 环绕视角 | 左键在空白处拖动 |
| 平移视角 | Shift + 左键拖动 |
| 缩放 | 滚轮 |
| 选中物体 | 左键点物体（会同步层级树与 Inspector） |
| 移动物体 | 左键拖动已选中的物体（沿地面 XZ 平面） |
| 聚焦 | 双击物体 |
| 放置 3D 零件 | 零件库双击「立方体 / 球体 / 平面 / 棱锥 / 圆柱」 |

3D 物体用 **Transform3D**（位置 / 三轴旋转 / 缩放）与 **Mesh3D**（网格类型 / 颜色 / 透明度 / 线框）描述，
全部走组件表，所以 Inspector 里改数值同样是「改完点应用」。

场景里可以放一个 **Camera3D** 组件来定义预览时的初始机位（yaw / pitch / distance / fov / 注视点）。

---

## 五、组件参考

| 组件 | 字段 |
|---|---|
| **Transform** | x, y, width, height, rotation, scale, layer（绘制层级） |
| **Sprite** | shape(rect/oval/image), fill, outline, image, opacity |
| **Label** | text, font_size, color, bold, align(center/left/right) |
| **Animator** | effect(spin/pulse/fade/slide/float), speed, amplitude, auto_play |
| **Rigidbody2D** | body_type, velocity_x, velocity_y, gravity_scale, drag, bounce, fixed_rotation |
| **BoxCollider2D** | is_trigger, offset_x, offset_y, width, height（0 = 跟随 Transform） |
| **TapHandler** | action |
| **Timer** | interval_ms, action, auto_start, repeat |
| **Script** | name, on_start, on_update, on_tap, on_collision, on_destroy |
| **Spawner** | prefab, interval_ms, max_alive, offset_x, offset_y |
| **Camera2D** | follow（物体名）, zoom, smooth |
| **Transform3D** | x, y, z, rx, ry, rz, scale |
| **Mesh3D** | shape(cube/sphere/plane/pyramid/cylinder), color, outline, opacity, wireframe |
| **Camera3D** | yaw, pitch, distance, fov, target_x, target_y, target_z |

---

## 六、内置动作

可用于 `TapHandler.action`、`Timer.action`：

```
none                    什么都不做
move-left / move-right / move-up / move-down   设置速度 240 px/s
jump                    向上初速度 430 px/s
bounce                  首次触发时给一个对角速度
stop                    速度归零
destroy                 销毁自己
toggle                  切换自身激活状态
restart                 重开场景
spawn:<预制体名>         在自己位置实例化预制体
print('文字')            打印到控制台 / logcat
```

桌面预览额外支持 Python 表达式，例如 `x += 10`、`width = 200`、`log('hp=%d' % hp)`。

> 导出 APK 时只保留上表的内置动作；Script 组件会走下面的「脚本子集」编译执行。

---

## 七、脚本

`Script` 组件在桌面预览里用完整 Python 执行；导出 APK 时没有 Python 解释器，
tkunity 会把脚本编译成一份 JSON AST，由随工程生成的 **`ScriptVM.java`** 解释执行，
因此 **脚本在 APK 里是真正生效的**。

两边共享同一套语义，只有写法子集不同（桌面预览宽容，APK 严格）：

| 可用名字 | 含义 | APK 可用 |
|---|---|---|
| `x`, `y`, `width`, `height`, `w`, `h` | 位置与尺寸，执行后自动写回 | ✅ |
| `vx`, `vy` | 速度（px/s），写回刚体 | ✅ |
| `rotation`, `scale` | 旋转与缩放 | ✅ |
| `dt`, `time` | 帧间隔（秒）、运行时长（秒） | ✅ |
| `log(msg)` | 输出到控制台 / logcat | ✅ |
| `find(name)` | 按名字找实体（找不到返回 None） | ✅ |
| `spawn(prefab, x, y)` | 实例化预制体 | ✅ |
| `destroy()` / `restart()` | 销毁自己 / 重开场景 | ✅ |
| `other` | 碰撞对象的名字（字符串） | ✅ |
| `name`, `tag` | 自己的名字与标签 | ✅ |
| `math.*` | sin/cos/tan/sqrt/atan2/hypot/fabs/pi/e | ✅ |
| `self`, `scene` | 实体字典 / 运行时对象 | ❌ 仅桌面 |

**APK 支持的语法子集**：数字、字符串、`True/False/None`、`+ - * / // % **`、
比较、`and/or/not`、赋值与增强赋值、`if/elif/else`、`while`、`for i in range(...)`、
`break/continue/pass`、以及白名单函数 `log/find/spawn/destroy/restart/abs/min/max/
round/int/float/str/len` 与 `math.*`。

**桌面预览还额外支持**：完整 Python 语法、`self` / `scene` 对象、`scene.axis()` 读键盘。

例：左右巡逻（两边都能跑）

```python
# on_update
vx = 160 if x < 500 else -160
```

例：碰到就打印（两边都能跑）

```python
# on_collision
log('hit ' + other)
```

> 若脚本用了子集之外的写法（导入、函数定义、列表、下标、任意属性访问等），
> 导出时 `tkunity build` 会打印「脚本编译警告」并跳过该钩子，`tkunity validate` 也会报出来；
> APK 工程里的 `README_BUILD.md` 同样会列出这些警告。

---

## 八、Python API

```python
from tkunity import Project, GameObject, save

p = Project("弹球", 960, 640, background="#1e1e2e", gravity=980)

ground = GameObject("地面", 0, 560, 960, 40, tag="Ground")
ground.add_sprite("rect", fill="#45475a").add_collider()
p.add(ground)

ball = GameObject("球", 460, 100, 60, 60, tag="Player")
ball.add_sprite("oval", fill="#f38ba8")
ball.add_rigidbody(velocity_x=160, bounce=0.9)
ball.add_collider()
ball.add_animator("spin", speed=0.6)
ball.add_script(on_update="if x < 0 or x + w > 960: vx = -vx")
p.add(ball)

p.save_prefab(ball, "ball")      # 存成预制体
p.instantiate("ball", 200, 80)   # 再实例化一个
save(p, "demo.pyu")
```

### 项目 / 物体 API

| 方法 | 说明 |
|---|---|
| `Project(name, w, h, background, gravity)` | 新建项目（一个 `.pyu` = 一个场景） |
| `Project.add(obj, parent=...)` | 加入物体，可指定父物体 |
| `Project.find(name)` / `Project.tag(tag)` | 按名字 / 标签查找 |
| `Project.save_prefab(obj, name)` / `instantiate(name, x, y)` | 预制体 |
| `Project.set_scene(...)` / `set_physics(gravity=..., time_scale=...)` | 场景与物理设置 |
| `Project.embed_image(path)` | 内嵌 PNG/GIF |
| `Project.world_rect(obj)` | 世界坐标包围盒 |
| `Project.save(path)` / `tkunity.save(p, path)` | 保存 |
| `GameObject.add_sprite / add_label / add_animator / add_rigidbody / add_collider / add_tap / add_timer / add_script / add_spawner / add_camera` | 加组件（链式） |
| `GameObject.set_parent(parent)` / `move(dx,dy)` / `set_position / set_size / set_rotation` | 变换 |

---

## 九、导出 Android

```bash
tkunity build examples/demo.pyu -o ./out
cd out/android_*
# 设置 ANDROID_HOME 或在目录里放 local.properties
build_apk.bat        # Windows
./build_apk.sh       # Linux / macOS
# 产物 app/build/outputs/apk/debug/app-debug.apk
```

导出的 Java 渲染器（`GameView.java` + `ScriptVM.java`）零第三方依赖，支持层级、
旋转缩放、刚体物理、碰撞触发器、摄像机、动画、全部内置动作，以及脚本子集。

导出的工程还做了两处兼容处理：

- `build_apk.bat` 是**纯 ASCII**（英文提示）—— Windows CMD 默认按 GBK 解析批处理，
  UTF-8 中文会乱码甚至把命令截断（`set` 变成 `et`），所以这个文件不写中文；
- `gradle.properties` 里写了 `android.overridePathCheck=true`，`settings.gradle` 用
  `PREFER_SETTINGS`，因此工程放在**中文/空格路径**下也能构建，也能配合国内镜像的 `init.gradle`。

---

## 十、限制

- 2D 简化模型：父物体的旋转不参与子物体位置计算（位移与缩放参与）；
- `tkinter` Canvas 不能真正旋转图片，图片精灵的旋转在桌面预览中表现为轴对齐，APK 中完整支持；
- 脚本在 APK 中受语法子集限制（见第七节），超出子集的写法会告警并跳过；
- **3D 场景目前只在桌面端**（编辑器 + 预览）：软件渲染没有光照贴图、阴影、纹理，
  APK 导出只支持 2D，遇到 Mesh3D 物体时会跳过并在 `tkunity build` / `validate` 里给出警告；
- 一个 `.pyu` 对应一个场景，暂不支持多场景切换。
