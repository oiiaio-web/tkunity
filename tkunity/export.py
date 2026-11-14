# -*- coding: utf-8 -*-
"""APK 导出器：把 .pyu 项目字典生成一个可直接构建的 Android Studio/Gradle 工程。

产物特点：
- 纯 Java + 系统自带 org.json / android.graphics，零第三方依赖；
- minSdk 26 / targetSdk 34，JDK 17，AGP 8.2.2，Gradle 8.5；
- 支持层级父子变换、旋转、缩放、透明度、刚体物理、AABB 碰撞与触发器、
  摄像机跟随/缩放、动画补间、生成器、计时器、点击动作；
- Script 组件会被编译成 JSON AST，由随工程一起生成的 ScriptVM.java 解释执行，
  APK 里脚本是真正生效的（桌面预览仍用完整 Python 执行）；
- 自定义 Python 表达式只用于桌面预览，APK 不支持（文档已注明）。
"""
from __future__ import annotations

import json
import os

from . import __version__
from .components import BUILTIN_ACTIONS
from .pyu import MAGIC
from .script import compile_project

__all__ = ["build", "DEFAULT_PACKAGE", "GAME_VIEW_JAVA", "SCRIPT_VM_JAVA"]

DEFAULT_PACKAGE = "com.oiiaio.tkunity"
APP_NAME = "TkUnityGame"


def build(project, outdir, package=DEFAULT_PACKAGE, app_name=None, warnings=None):
    """生成 Android 工程到 outdir，返回生成的文件路径列表。

    warnings: 可选的列表，脚本编译失败/语法不支持时会往里追加提示文本。
    """
    meta = project.get("meta", {})
    name = app_name or meta.get("name", APP_NAME)
    files = []
    programs, script_warnings = compile_project(project)
    if warnings is not None:
        warnings.extend(script_warnings)
        for entity in project.get("entities", []):
            if entity.get("components", {}).get("Mesh3D"):
                warnings.append("%s: 3D 网格（APK 导出只支持 2D 场景，该物体被跳过）"
                                % entity.get("name", "?"))
    pkg_path = package.replace(".", os.sep)
    paths = {
        "settings":      os.path.join(outdir, "settings.gradle"),
        "root_build":    os.path.join(outdir, "build.gradle"),
        "gradle_props":  os.path.join(outdir, "gradle.properties"),
        "app_build":     os.path.join(outdir, "app", "build.gradle"),
        "manifest":      os.path.join(outdir, "app", "src", "main", "AndroidManifest.xml"),
        "strings":       os.path.join(outdir, "app", "src", "main", "res", "values", "strings.xml"),
        "pyu":           os.path.join(outdir, "app", "src", "main", "assets", "game.pyu"),
        "activity":      os.path.join(outdir, "app", "src", "main", "java", pkg_path, "MainActivity.java"),
        "gameview":      os.path.join(outdir, "app", "src", "main", "java", pkg_path, "GameView.java"),
        "scriptvm":      os.path.join(outdir, "app", "src", "main", "java", pkg_path, "ScriptVM.java"),
        "bat":           os.path.join(outdir, "build_apk.bat"),
        "sh":            os.path.join(outdir, "build_apk.sh"),
        "readme":        os.path.join(outdir, "README_BUILD.md"),
        "local_props":   os.path.join(outdir, "local.properties.example"),
    }

    for path in paths.values():
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def write(key, content, encoding="utf-8"):
        with open(paths[key], "w", encoding=encoding, newline="\n") as fh:
            fh.write(content)
        files.append(paths[key])

    write("settings", _settings_gradle())
    write("root_build", _root_build_gradle())
    write("gradle_props", _gradle_properties())
    write("app_build", _app_build_gradle(package, name))
    write("manifest", _manifest(package))
    write("strings", _strings(name))
    write("pyu", _pyu_blob(project, programs))
    write("activity", _main_activity(package))
    write("gameview", _game_view(package))
    write("scriptvm", _script_vm(package))
    write("bat", _build_bat(), encoding="ascii")
    write("sh", _build_sh())
    write("readme", _build_readme(outdir, name, project, script_warnings))
    write("local_props", "# 复制为 local.properties 并填写你的 Android SDK 路径\n"
                         "# sdk.dir=C:\\\\Users\\\\you\\\\AppData\\\\Local\\\\Android\\\\Sdk\n"
                         "sdk.dir=/path/to/your/android/sdk\n")
    return files


# ---------------------------------------------------------------- 内容生成
def _pyu_blob(project, programs=None):
    data = project
    if programs:
        data = dict(project)
        data["programs"] = programs
    blob = json.dumps(data, ensure_ascii=False, indent=1,
                      separators=(",", ": ")).encode("utf-8")
    return (MAGIC + blob).decode("utf-8")


def _settings_gradle():
    return """pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    // PREFER_SETTINGS：优先用本工程 settings 里的仓库配置，
    // 同时保留 init.gradle 里配置的镜像，兼容国内镜像环境
    repositoriesMode.set(RepositoriesMode.PREFER_SETTINGS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "TkUnityGame"
include ':app'
"""


def _root_build_gradle():
    return """plugins {
    id 'com.android.application' version '8.2.2' apply false
}
"""


def _gradle_properties():
    return """org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
android.useAndroidX=false
android.enableJetifier=false
# 允许工程路径包含中文/空格等非 ASCII 字符
android.overridePathCheck=true
"""


def _app_build_gradle(package, name):
    return """plugins {
    id 'com.android.application'
}

android {
    namespace '%s'
    compileSdk 34

    defaultConfig {
        applicationId "%s"
        minSdk 26
        targetSdk 34
        versionCode 1
        versionName "%s"
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }

    buildTypes {
        release {
            minifyEnabled false
        }
    }
}

// tkunity 游戏：零第三方依赖，无需任何 dependencies 块
""" % (package, package, __version__)


def _manifest(package):
    return """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <application
        android:label="@string/app_name"
        android:allowBackup="true"
        android:hardwareAccelerated="true"
        android:theme="@android:style/Theme.Material.NoActionBar.Fullscreen">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:screenOrientation="landscape"
            android:configChanges="orientation|screenSize|keyboardHidden">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>

</manifest>
"""


def _strings(name):
    return """<resources>
    <string name="app_name">%s</string>
</resources>
""" % name


def _main_activity(package):
    return """package %s;

import android.app.Activity;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.WindowManager;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        GameView view = new GameView(this);
        setContentView(view);
        if (Build.VERSION.SDK_INT >= 19) {
            view.setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        }
    }
}
""" % package


def _build_readme(outdir, name, project=None, script_warnings=None):
    project = project or {}
    entities = len(project.get("entities", []))
    prefabs = len(project.get("prefabs", {}))
    scripts = 0
    for entity in project.get("entities", []):
        if entity.get("components", {}).get("Script"):
            scripts += 1
    warn_block = ""
    if script_warnings:
        warn_block = ("\n## 脚本编译警告（%d 条，这些钩子不会在 APK 中执行）\n%s\n"
                      % (len(script_warnings),
                         "\n".join("- " + w for w in script_warnings)))
    return """# %s - Android 构建说明

本目录由 tkunity %s 导出，是一个 **零第三方依赖** 的纯 Java Android 工程。
场景内物体 %d 个，预制体 %d 个，带脚本的物体 %d 个。

## 构建要求
- JDK 17
- Android SDK（compileSdk 34）
  - 设置环境变量 ANDROID_HOME，或把 local.properties.example 复制为 local.properties 并填写 sdk.dir
- 无需 Android Studio，命令行即可构建
- 工程路径可以包含中文/空格（已开启 android.overridePathCheck）

## 构建
Windows:
    build_apk.bat
Linux/macOS:
    ./build_apk.sh

脚本会自动下载 Gradle 8.5（若本机未安装 gradle）。

## 产物
    app/build/outputs/apk/debug/app-debug.apk

## 运行时支持
- 渲染：矩形 / 椭圆 / 图片（base64 内嵌）、文本对齐、透明度、旋转、缩放、层级排序
- 层级：父子变换（子物体跟随父物体位移与缩放）
- 物理：Rigidbody2D（dynamic / kinematic / static、重力、速度、阻尼、弹性）
- 碰撞：BoxCollider2D 实心碰撞推出 + 触发器
- 相机：Camera2D 跟随与缩放
- 动画：Animator（spin / pulse / fade / slide / float）
- 行为：Timer 定时动作、TapHandler 点击动作、Spawner 实例化预制体
- 动作：%s
- **脚本**：Script 组件的生命周期（on_start / on_update / on_tap / on_collision /
  on_destroy）由 ScriptVM.java 解释执行，语法子集与桌面预览一致

## 脚本子集（ScriptVM 支持）
数字 / 字符串 / True / False / None、算术（+ - * / // %% **）、比较、and / or / not、
赋值与增强赋值、if / elif / else、while、for i in range(...)、break / continue / pass。

可用函数：log / find / spawn / destroy / restart / abs / min / max / round / int /
float / str / len / math.sin / math.cos / math.tan / math.sqrt / math.atan2 /
math.hypot / math.fabs / math.pi / math.e。

可用变量：x / y / width / height / w / h / vx / vy / rotation / scale / dt / time /
other（碰撞对方的名字）/ name / tag。写入 x/y/vx/vy 等会直接作用于实体。

## 限制
- 桌面预览支持完整 Python；导出到 APK 时只支持上面的语法子集，
  用了子集之外的写法（导入、函数定义、列表、下标等）会在导出时给出警告并跳过该钩子。
%s""" % (name, __version__, entities, prefabs, scripts,
         " / ".join(BUILTIN_ACTIONS), warn_block)


def _build_bat():
    # 注意：这个文件必须保持纯 ASCII（英文提示）。
    # Windows CMD 默认按 GBK 解析批处理，UTF-8 中文会导致乱码，
    # 甚至把多字节字符拆进命令里（例如 `set` 变成 `et`），脚本直接跑不起来。
    return """@echo off
setlocal enabledelayedexpansion
set "GRADLE_VERSION=8.5"
set "DIR=%~dp0"
set "TOOL_DIR=%DIR%.gradle-tool"
set "GRADLE_HOME=%TOOL_DIR%\\gradle-%GRADLE_VERSION%"

set "GRADLE_CMD="
where gradle >nul 2>nul && set "GRADLE_CMD=gradle"
if not defined GRADLE_CMD (
  if not exist "%GRADLE_HOME%\\bin\\gradle.bat" (
    echo [tkunity] Downloading Gradle %GRADLE_VERSION% ...
    if not exist "%TOOL_DIR%" mkdir "%TOOL_DIR%"
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$u='https://services.gradle.org/distributions/gradle-%GRADLE_VERSION%-bin.zip';" ^
      "$z='%TOOL_DIR%\\gradle.zip';" ^
      "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;" ^
      "Invoke-WebRequest -Uri $u -OutFile $z;" ^
      "Expand-Archive -Path $z -DestinationPath '%TOOL_DIR%' -Force"
    if errorlevel 1 (
      echo [tkunity] Failed to download Gradle. Please download it manually:
      echo   https://services.gradle.org/distributions/gradle-%GRADLE_VERSION%-bin.zip
      exit /b 1
    )
  )
  set "GRADLE_CMD=%GRADLE_HOME%\\bin\\gradle.bat"
)

if not defined ANDROID_HOME (
  if not exist "%DIR%local.properties" (
    echo [tkunity] ANDROID_HOME is not set and local.properties is missing.
    echo   Create %DIR%local.properties with a line like:
    echo   sdk.dir=C:\\Users\\you\\AppData\\Local\\Android\\Sdk
    exit /b 1
  )
)

cd /d "%DIR%"
call "%GRADLE_CMD%" assembleDebug
if errorlevel 1 (
  echo [tkunity] Build FAILED
  exit /b 1
)
echo.
echo APK: %DIR%app\\build\\outputs\\apk\\debug\\app-debug.apk
"""


def _build_sh():
    return """#!/usr/bin/env bash
set -e
GRADLE_VERSION=8.5
DIR="$(cd "$(dirname "$0")" && pwd)"
TOOL_DIR="$DIR/.gradle-tool"
GRADLE_HOME="$TOOL_DIR/gradle-$GRADLE_VERSION"

if command -v gradle >/dev/null 2>&1; then
  GRADLE_CMD=gradle
else
  if [ ! -x "$GRADLE_HOME/bin/gradle" ]; then
    echo "[tkunity] downloading Gradle $GRADLE_VERSION ..."
    mkdir -p "$TOOL_DIR"
    (curl -fsSL -o "$TOOL_DIR/gradle.zip" \\
         "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip") \\
      || (wget -q -O "$TOOL_DIR/gradle.zip" \\
         "https://services.gradle.org/distributions/gradle-$GRADLE_VERSION-bin.zip")
    unzip -q -o "$TOOL_DIR/gradle.zip" -d "$TOOL_DIR"
  fi
  GRADLE_CMD="$GRADLE_HOME/bin/gradle"
fi

if [ -z "$ANDROID_HOME" ] && [ ! -f "$DIR/local.properties" ]; then
  echo "[tkunity] ANDROID_HOME not set and no local.properties found."
  echo "  Create $DIR/local.properties with: sdk.dir=/path/to/your/android/sdk"
  exit 1
fi

cd "$DIR"
"$GRADLE_CMD" assembleDebug
echo
echo "APK: $DIR/app/build/outputs/apk/debug/app-debug.apk"
"""


def _game_view(package):
    """生成 GameView.java 渲染器（含层级、物理、相机、动作）。"""
    return _GAME_VIEW_TEMPLATE.replace("@PACKAGE@", package)


GAME_VIEW_JAVA = _GAME_VIEW_TEMPLATE = r"""package @PACKAGE@;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.os.Handler;
import android.os.Looper;
import android.util.AttributeSet;
import android.util.Base64;
import android.util.Log;
import android.view.MotionEvent;
import android.view.View;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * tkunity 游戏渲染器：纯 Android 系统 API，零第三方依赖。
 * 读取 assets/game.pyu（.pyu 格式），支持层级、刚体物理、碰撞、相机与动作。
 */
public class GameView extends View {
    private static final String TAG = "tkunity";
    private static final int GRID = 40;
    private static final int TICK_MS = 16;
    private static final float ACTION_SPEED = 240f;
    private static final float JUMP_SPEED = 430f;

    private JSONObject project;
    private final List<Entity> entities = new ArrayList<>();
    private final Map<Integer, Entity> byId = new HashMap<>();
    private final Map<String, Bitmap> bitmaps = new HashMap<>();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

    private Entity dragging;
    private float dragDX;
    private float dragDY;
    private Entity camera;
    private int sceneW = 960;
    private int sceneH = 640;
    private int bgColor = Color.rgb(30, 30, 46);
    private float gravity = 980f;
    private float camX = 480f;
    private float camY = 320f;
    private float zoom = 1f;
    private long startTime;
    private long lastFrame;
    private float elapsed;
    private int nextId = 1;
    private boolean paused = false;
    private String scriptOther = null;
    private float lastDt = 0f;

    private final Runnable ticker = new Runnable() {
        @Override
        public void run() {
            frame();
        }
    };

    public GameView(Context context) {
        super(context);
        init();
    }

    public GameView(Context context, AttributeSet attrs) {
        super(context, attrs);
        init();
    }

    public GameView(Context context, AttributeSet attrs, int defStyle) {
        super(context, attrs, defStyle);
        init();
    }

    private void init() {
        loadProject();
        startTime = System.currentTimeMillis();
        lastFrame = startTime;
        startScripts();
        handler.post(ticker);
    }

    // ---------------------------------------------------------------- 载入
    private void loadProject() {
        try {
            InputStream in = getContext().getAssets().open("game.pyu");
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) != -1) {
                bos.write(buf, 0, n);
            }
            in.close();
            String text = new String(bos.toByteArray(), StandardCharsets.UTF_8);
            int idx = text.indexOf('{');
            if (idx < 0) {
                return;
            }
            project = new JSONObject(text.substring(idx));

            entities.clear();
            byId.clear();
            bitmaps.clear();

            JSONObject meta = project.optJSONObject("meta");
            if (meta != null) {
                sceneW = meta.optInt("scene_width", 960);
                sceneH = meta.optInt("scene_height", 640);
                bgColor = parseColor(meta.optString("background", "#1e1e2e"));
                gravity = (float) meta.optDouble("gravity", 980.0);
            }
            camX = sceneW / 2f;
            camY = sceneH / 2f;

            JSONArray arr = project.optJSONArray("entities");
            if (arr == null) {
                return;
            }
            for (int i = 0; i < arr.length(); i++) {
                JSONObject obj = arr.optJSONObject(i);
                if (obj == null) {
                    continue;
                }
                Entity entity = Entity.fromJson(obj, parseColor("#4C8BF5"), parseColor("#123456"));
                entities.add(entity);
                byId.put(entity.id, entity);
                if (entity.id >= nextId) {
                    nextId = entity.id + 1;
                }
            }
            for (Entity entity : entities) {
                if (entity.parentId != 0) {
                    entity.parent = byId.get(entity.parentId);
                }
            }
            camera = null;
            zoom = 1f;
            for (Entity entity : entities) {
                if (entity.hasCamera) {
                    camera = entity;
                    zoom = Math.max(0.1f, entity.zoom);
                    if (entity.follow != null && !entity.follow.isEmpty()) {
                        Entity target = findByName(entity.follow);
                        if (target != null) {
                            camX = target.centerX();
                            camY = target.centerY();
                        }
                    }
                    break;
                }
            }

            JSONObject programData = project.optJSONObject("programs");
            if (programData != null) {
                for (Entity entity : entities) {
                    entity.programs = programData.optJSONObject(String.valueOf(entity.id));
                }
            }
        } catch (Exception e) {
            Log.e(TAG, "load project failed", e);
        }
    }

    private Entity findByName(String name) {
        for (Entity entity : entities) {
            if (name.equals(entity.name)) {
                return entity;
            }
        }
        return null;
    }

    // ---------------------------------------------------------------- 主循环
    private void frame() {
        long now = System.currentTimeMillis();
        float dt = (now - lastFrame) / 1000f;
        lastFrame = now;
        if (dt < 0f) {
            dt = 0f;
        }
        if (dt > 0.1f) {
            dt = 0.1f;
        }
        lastDt = dt;
        if (!paused) {
            elapsed += dt;
            for (Entity entity : new ArrayList<>(entities)) {
                update(entity, dt);
                runHook(entity, "on_update", null);
            }
            collide();
        }
        updateCamera();
        invalidate();
        handler.postDelayed(ticker, TICK_MS);
    }

    private void updateCamera() {
        if (camera == null) {
            return;
        }
        zoom = Math.max(0.1f, camera.zoom);
        if (camera.follow == null || camera.follow.isEmpty()) {
            return;
        }
        Entity target = findByName(camera.follow);
        if (target == null) {
            return;
        }
        float k = 1f - Math.max(0f, Math.min(1f, camera.smooth));
        camX += (target.centerX() - camX) * k;
        camY += (target.centerY() - camY) * k;
    }

    private void update(Entity e, float dt) {
        if (!e.activeInHierarchy()) {
            return;
        }
        // 物理
        if (e.hasRigid && !"static".equals(e.bodyType)) {
            if ("dynamic".equals(e.bodyType)) {
                e.vy += gravity * e.gravityScale * dt;
                if (e.drag > 0f) {
                    float factor = Math.max(0f, 1f - e.drag * dt);
                    e.vx *= factor;
                    e.vy *= factor;
                }
            }
            if (e.vx != 0f || e.vy != 0f) {
                e.x += e.vx * dt;
                e.y += e.vy * dt;
                if (!e.hasCollider) {
                    e.clampToScene(sceneW, sceneH);
                }
            }
        } else if (e.vx != 0f || e.vy != 0f) {
            e.x += e.vx * dt;
            e.y += e.vy * dt;
            if (!e.hasCollider) {
                e.clampToScene(sceneW, sceneH);
            }
        }
        // 定时器
        if (e.hasTimer && !e.timerDone && e.autoStart) {
            e.timerElapsed += dt;
            if (e.timerElapsed * 1000f >= e.intervalMs) {
                e.timerElapsed = 0f;
                runAction(e, e.timerAction);
                if (!e.repeat) {
                    e.timerDone = true;
                }
            }
        }
        // 生成器
        if (e.hasSpawner && e.spawnPrefab != null && !e.spawnPrefab.isEmpty()) {
            e.spawnElapsed += dt;
            if (e.spawnElapsed * 1000f >= e.spawnIntervalMs) {
                e.spawnElapsed = 0f;
                int alive = 0;
                for (int id : e.spawned) {
                    Entity child = byId.get(id);
                    if (child != null && !child.dead) {
                        alive++;
                    }
                }
                if (e.spawnMaxAlive <= 0 || alive < e.spawnMaxAlive) {
                    Entity child = spawn(e.spawnPrefab, e.x + e.spawnOffsetX, e.y + e.spawnOffsetY);
                    if (child != null) {
                        e.spawned.add(child.id);
                    }
                }
            }
        }
    }

    private void collide() {
        List<Entity> list = new ArrayList<>();
        for (Entity e : entities) {
            if (e.hasCollider && e.activeInHierarchy() && !e.dead) {
                list.add(e);
            }
        }
        for (int i = 0; i < list.size(); i++) {
            for (int j = i + 1; j < list.size(); j++) {
                Entity a = list.get(i);
                Entity b = list.get(j);
                float[] ra = a.colliderRect();
                float[] rb = b.colliderRect();
                if (!overlap(ra, rb)) {
                    continue;
                }
                if (a.isTrigger || b.isTrigger) {
                    runHook(a, "on_collision", b.name);
                    runHook(b, "on_collision", a.name);
                    continue;
                }
                float[] pen = penetration(ra, rb);
                boolean aMoves = a.hasRigid && "dynamic".equals(a.bodyType);
                boolean bMoves = b.hasRigid && "dynamic".equals(b.bodyType);
                if (!aMoves && !bMoves) {
                    continue;
                }
                if (aMoves && !bMoves) {
                    a.x += pen[0];
                    a.y += pen[1];
                    a.bounceOn(pen[0], pen[1]);
                } else if (bMoves && !aMoves) {
                    b.x -= pen[0];
                    b.y -= pen[1];
                    b.bounceOn(-pen[0], -pen[1]);
                } else {
                    a.x += pen[0] / 2f;
                    a.y += pen[1] / 2f;
                    b.x -= pen[0] / 2f;
                    b.y -= pen[1] / 2f;
                    a.bounceOn(pen[0], pen[1]);
                    b.bounceOn(-pen[0], -pen[1]);
                }
            }
        }
        List<Entity> dead = new ArrayList<>();
        for (Entity e : entities) {
            if (e.dead) {
                dead.add(e);
            }
        }
        for (Entity e : dead) {
            runHook(e, "on_destroy", null);
            entities.remove(e);
            byId.remove(e.id);
        }
    }

    private static boolean overlap(float[] a, float[] b) {
        return a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
    }

    private static float[] penetration(float[] a, float[] b) {
        float dx1 = b[2] - a[0];
        float dx2 = a[2] - b[0];
        float dy1 = b[3] - a[1];
        float dy2 = a[3] - b[1];
        float dx = dx1 < dx2 ? dx1 : -dx2;
        float dy = dy1 < dy2 ? dy1 : -dy2;
        if (Math.abs(dx) <= Math.abs(dy)) {
            return new float[]{dx, 0f};
        }
        return new float[]{0f, dy};
    }

    // ---------------------------------------------------------------- 动作
    private void runAction(Entity e, String action) {
        if (action == null) {
            return;
        }
        action = action.trim();
        if (action.isEmpty() || "none".equals(action)) {
            return;
        }
        String low = action.toLowerCase();
        if (low.startsWith("spawn:")) {
            spawn(action.substring(6).trim(), e.x, e.y);
            return;
        }
        if ("move-left".equals(low)) {
            e.vx = -ACTION_SPEED;
            e.vy = 0f;
        } else if ("move-right".equals(low)) {
            e.vx = ACTION_SPEED;
            e.vy = 0f;
        } else if ("move-up".equals(low)) {
            e.vx = 0f;
            e.vy = -ACTION_SPEED;
        } else if ("move-down".equals(low)) {
            e.vx = 0f;
            e.vy = ACTION_SPEED;
        } else if ("jump".equals(low)) {
            e.vy = -JUMP_SPEED;
        } else if ("bounce".equals(low)) {
            if (Math.abs(e.vx) < 0.001f && Math.abs(e.vy) < 0.001f) {
                e.vx = ACTION_SPEED;
                e.vy = ACTION_SPEED;
            }
        } else if ("stop".equals(low)) {
            e.vx = 0f;
            e.vy = 0f;
        } else if ("destroy".equals(low)) {
            e.dead = true;
        } else if ("toggle".equals(low)) {
            e.active = !e.active;
        } else if ("restart".equals(low)) {
            restart();
        } else if (low.startsWith("print(")) {
            Log.i(TAG, action);
        }
    }

    private void restart() {
        loadProject();
        startTime = System.currentTimeMillis();
        lastFrame = startTime;
        elapsed = 0f;
    }

    // ---------------------------------------------------------------- 生成
    private Entity spawn(String prefabName, float x, float y) {
        try {
            if (project == null) {
                return null;
            }
            JSONObject prefabs = project.optJSONObject("prefabs");
            if (prefabs == null) {
                return null;
            }
            JSONObject prefab = prefabs.optJSONObject(prefabName);
            if (prefab == null) {
                Log.w(TAG, "prefab not found: " + prefabName);
                return null;
            }
            Entity entity = Entity.fromPrefab(prefab, parseColor("#4C8BF5"), parseColor("#123456"));
            entity.id = nextId++;
            entity.x = x;
            entity.y = y;
            entities.add(entity);
            byId.put(entity.id, entity);
            return entity;
        } catch (Exception e) {
            Log.e(TAG, "spawn failed: " + prefabName, e);
            return null;
        }
    }

    // ---------------------------------------------------------------- 脚本
    private void startScripts() {
        for (Entity entity : entities) {
            if (entity.activeInHierarchy()) {
                runHook(entity, "on_start", null);
            }
        }
    }

    private void runHook(Entity entity, String hook, String otherName) {
        if (entity == null || entity.programs == null) {
            return;
        }
        JSONObject program = entity.programs.optJSONObject(hook);
        if (program == null) {
            return;
        }
        scriptOther = otherName;
        ScriptVM.run(program, new EntityHost(entity));
        scriptOther = null;
    }

    private ScriptVM.Val callFunction(String fn, ScriptVM.Val[] args, Entity self) {
        if ("log".equals(fn)) {
            Log.i(TAG, args.length > 0 ? args[0].asString() : "");
            return ScriptVM.Val.none();
        }
        if ("find".equals(fn)) {
            Entity found = args.length > 0 ? findByName(args[0].asString()) : null;
            return found == null ? ScriptVM.Val.none() : ScriptVM.Val.str(found.name);
        }
        if ("spawn".equals(fn)) {
            String prefab = args.length > 0 ? args[0].asString() : "";
            float px = args.length > 1 ? (float) args[1].asNumber() : self.x;
            float py = args.length > 2 ? (float) args[2].asNumber() : self.y;
            spawn(prefab, px, py);
            return ScriptVM.Val.none();
        }
        if ("destroy".equals(fn)) {
            self.dead = true;
            return ScriptVM.Val.none();
        }
        if ("restart".equals(fn)) {
            restart();
            return ScriptVM.Val.none();
        }
        if ("abs".equals(fn)) {
            return ScriptVM.Val.num(Math.abs(args[0].asNumber()));
        }
        if ("min".equals(fn)) {
            return ScriptVM.Val.num(Math.min(args[0].asNumber(), args[1].asNumber()));
        }
        if ("max".equals(fn)) {
            return ScriptVM.Val.num(Math.max(args[0].asNumber(), args[1].asNumber()));
        }
        if ("round".equals(fn)) {
            return ScriptVM.Val.num(Math.round(args[0].asNumber()));
        }
        if ("int".equals(fn)) {
            return ScriptVM.Val.num((double) (long) args[0].asNumber());
        }
        if ("float".equals(fn)) {
            return ScriptVM.Val.num(args[0].asNumber());
        }
        if ("str".equals(fn)) {
            return ScriptVM.Val.str(args[0].asString());
        }
        if ("len".equals(fn)) {
            return ScriptVM.Val.num(args[0].asString().length());
        }
        if ("math.pi".equals(fn)) {
            return ScriptVM.Val.num(Math.PI);
        }
        if ("math.e".equals(fn)) {
            return ScriptVM.Val.num(Math.E);
        }
        if (fn.startsWith("math.")) {
            double a = args.length > 0 ? args[0].asNumber() : 0.0;
            double b = args.length > 1 ? args[1].asNumber() : 0.0;
            String name = fn.substring(5);
            if ("sin".equals(name)) {
                return ScriptVM.Val.num(Math.sin(a));
            }
            if ("cos".equals(name)) {
                return ScriptVM.Val.num(Math.cos(a));
            }
            if ("tan".equals(name)) {
                return ScriptVM.Val.num(Math.tan(a));
            }
            if ("sqrt".equals(name)) {
                return ScriptVM.Val.num(Math.sqrt(a));
            }
            if ("atan2".equals(name)) {
                return ScriptVM.Val.num(Math.atan2(a, b));
            }
            if ("hypot".equals(name)) {
                return ScriptVM.Val.num(Math.hypot(a, b));
            }
            if ("fabs".equals(name)) {
                return ScriptVM.Val.num(Math.abs(a));
            }
        }
        throw new ScriptVM.ScriptError("unknown function: " + fn);
    }

    /** 把脚本变量接到实体字段上，写回 x/y/vx/vy 等。 */
    private final class EntityHost implements ScriptVM.Host {
        private final Entity entity;

        EntityHost(Entity entity) {
            this.entity = entity;
        }

        @Override
        public ScriptVM.Val get(String name) {
            if ("x".equals(name)) {
                return ScriptVM.Val.num(entity.x);
            }
            if ("y".equals(name)) {
                return ScriptVM.Val.num(entity.y);
            }
            if ("width".equals(name) || "w".equals(name)) {
                return ScriptVM.Val.num(entity.width);
            }
            if ("height".equals(name) || "h".equals(name)) {
                return ScriptVM.Val.num(entity.height);
            }
            if ("vx".equals(name)) {
                return ScriptVM.Val.num(entity.vx);
            }
            if ("vy".equals(name)) {
                return ScriptVM.Val.num(entity.vy);
            }
            if ("rotation".equals(name)) {
                return ScriptVM.Val.num(entity.rotation);
            }
            if ("scale".equals(name)) {
                return ScriptVM.Val.num(entity.scale);
            }
            if ("dt".equals(name)) {
                return ScriptVM.Val.num(lastDt);
            }
            if ("time".equals(name)) {
                return ScriptVM.Val.num(elapsed);
            }
            if ("other".equals(name)) {
                return scriptOther == null ? ScriptVM.Val.none() : ScriptVM.Val.str(scriptOther);
            }
            if ("name".equals(name)) {
                return ScriptVM.Val.str(entity.name);
            }
            if ("tag".equals(name)) {
                return ScriptVM.Val.str(entity.tag);
            }
            return null;
        }

        @Override
        public void set(String name, ScriptVM.Val value) {
            if ("x".equals(name)) {
                entity.x = (float) value.asNumber();
            } else if ("y".equals(name)) {
                entity.y = (float) value.asNumber();
            } else if ("width".equals(name) || "w".equals(name)) {
                entity.width = (float) value.asNumber();
            } else if ("height".equals(name) || "h".equals(name)) {
                entity.height = (float) value.asNumber();
            } else if ("vx".equals(name)) {
                entity.vx = (float) value.asNumber();
            } else if ("vy".equals(name)) {
                entity.vy = (float) value.asNumber();
            } else if ("rotation".equals(name)) {
                entity.rotation = (float) value.asNumber();
            } else if ("scale".equals(name)) {
                entity.scale = (float) value.asNumber();
            }
        }

        @Override
        public ScriptVM.Val call(String fn, ScriptVM.Val[] args) {
            return callFunction(fn, args, entity);
        }

        @Override
        public void log(String message) {
            Log.i(TAG, message);
        }
    }

    // ---------------------------------------------------------------- 绘制
    @Override
    protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        canvas.drawColor(Color.rgb(20, 20, 26));
        canvas.save();
        canvas.translate(getWidth() / 2f - camX * zoom, getHeight() / 2f - camY * zoom);
        canvas.scale(zoom, zoom);

        paint.setStyle(Paint.Style.FILL);
        paint.setColor(bgColor);
        paint.setAlpha(255);
        canvas.drawRect(0, 0, sceneW, sceneH, paint);

        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(1);
        paint.setColor(Color.rgb(52, 52, 60));
        for (int gx = 0; gx <= sceneW; gx += GRID) {
            canvas.drawLine(gx, 0, gx, sceneH, paint);
        }
        for (int gy = 0; gy <= sceneH; gy += GRID) {
            canvas.drawLine(0, gy, sceneW, gy, paint);
        }

        List<Entity> sorted = new ArrayList<>(entities);
        Collections.sort(sorted, new Comparator<Entity>() {
            @Override
            public int compare(Entity a, Entity b) {
                int c = Integer.compare(a.layer, b.layer);
                return c != 0 ? c : Integer.compare(a.id, b.id);
            }
        });
        for (Entity entity : sorted) {
            if (!entity.activeInHierarchy() || entity.dead) {
                continue;
            }
            drawEntity(canvas, entity);
        }
        canvas.restore();
    }

    private void drawEntity(Canvas canvas, Entity e) {
        float[] wt = e.world();
        float wx = wt[0];
        float wy = wt[1];
        float ww = wt[2];
        float wh = wt[3];
        float rotation = wt[4] + e.animRotation(elapsed);
        float scale = e.animScale(elapsed);
        float opacity = e.opacity * e.animOpacity(elapsed);
        float cx = wx + ww / 2f;
        float cy = wy + wh / 2f;

        canvas.save();
        canvas.translate(cx, cy);
        canvas.rotate(rotation);
        canvas.scale(scale, scale);
        canvas.translate(-cx, -cy);

        int alpha = (int) (255f * Math.max(0f, Math.min(1f, opacity)));
        if ("image".equals(e.shape) && !e.image.isEmpty()) {
            Bitmap bmp = getBitmap(e.image);
            if (bmp != null) {
                paint.setAlpha(alpha);
                canvas.drawBitmap(bmp, null, new Rect(Math.round(wx), Math.round(wy),
                        Math.round(wx + ww), Math.round(wy + wh)), paint);
                paint.setAlpha(255);
            }
        } else if ("oval".equals(e.shape)) {
            paint.setStyle(Paint.Style.FILL);
            paint.setColor(e.fill);
            paint.setAlpha(alpha);
            canvas.drawOval(wx, wy, wx + ww, wy + wh, paint);
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(2);
            paint.setColor(e.outline);
            paint.setAlpha(Math.min(255, alpha + 40));
            canvas.drawOval(wx, wy, wx + ww, wy + wh, paint);
        } else {
            paint.setStyle(Paint.Style.FILL);
            paint.setColor(e.fill);
            paint.setAlpha(alpha);
            canvas.drawRect(wx, wy, wx + ww, wy + wh, paint);
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(2);
            paint.setColor(e.outline);
            paint.setAlpha(Math.min(255, alpha + 40));
            canvas.drawRect(wx, wy, wx + ww, wy + wh, paint);
        }
        paint.setAlpha(255);

        if (e.labelText != null && !e.labelText.isEmpty()) {
            paint.setStyle(Paint.Style.FILL);
            paint.setColor(e.labelColor);
            paint.setAlpha(alpha);
            paint.setTextSize(e.fontSize * zoom * getResources().getDisplayMetrics().density);
            paint.setTypeface(e.bold ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
            if ("left".equals(e.align)) {
                paint.setTextAlign(Paint.Align.LEFT);
            } else if ("right".equals(e.align)) {
                paint.setTextAlign(Paint.Align.RIGHT);
            } else {
                paint.setTextAlign(Paint.Align.CENTER);
            }
            float tx = wx + ww / 2f;
            if ("left".equals(e.align)) {
                tx = wx + 2f;
            } else if ("right".equals(e.align)) {
                tx = wx + ww - 2f;
            }
            Paint.FontMetrics fm = paint.getFontMetrics();
            float ty = cy - (fm.ascent + fm.descent) / 2f;
            canvas.drawText(e.labelText, tx, ty, paint);
            paint.setAlpha(255);
        }
        canvas.restore();
    }

    private Bitmap getBitmap(String assetName) {
        if (bitmaps.containsKey(assetName)) {
            return bitmaps.get(assetName);
        }
        try {
            JSONObject assets = project.optJSONObject("assets");
            if (assets == null) {
                return null;
            }
            String b64 = assets.optString(assetName, "");
            if (b64.isEmpty()) {
                return null;
            }
            byte[] data = Base64.decode(b64, Base64.DEFAULT);
            Bitmap bmp = BitmapFactory.decodeByteArray(data, 0, data.length);
            bitmaps.put(assetName, bmp);
            return bmp;
        } catch (Exception e) {
            Log.e(TAG, "decode image failed: " + assetName, e);
            return null;
        }
    }

    // ---------------------------------------------------------------- 触摸
    @Override
    public boolean onTouchEvent(MotionEvent event) {
        float x = (event.getX() - getWidth() / 2f) / zoom + camX;
        float y = (event.getY() - getHeight() / 2f) / zoom + camY;
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN: {
                Entity hit = hitTest(x, y);
                if (hit != null) {
                    dragging = hit;
                    dragDX = x - hit.x;
                    dragDY = y - hit.y;
                    runAction(hit, hit.tapAction);
                    runHook(hit, "on_tap", null);
                }
                return true;
            }
            case MotionEvent.ACTION_MOVE: {
                if (dragging != null) {
                    dragging.x = x - dragDX;
                    dragging.y = y - dragDY;
                    invalidate();
                }
                return true;
            }
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                dragging = null;
                return true;
            default:
                return super.onTouchEvent(event);
        }
    }

    private Entity hitTest(float x, float y) {
        List<Entity> sorted = new ArrayList<>(entities);
        Collections.sort(sorted, new Comparator<Entity>() {
            @Override
            public int compare(Entity a, Entity b) {
                int c = Integer.compare(b.layer, a.layer);
                return c != 0 ? c : Integer.compare(b.id, a.id);
            }
        });
        for (Entity e : sorted) {
            if (!e.activeInHierarchy() || e.dead) {
                continue;
            }
            float[] wt = e.world();
            if (x >= wt[0] && x <= wt[0] + wt[2] && y >= wt[1] && y <= wt[1] + wt[3]) {
                return e;
            }
        }
        return null;
    }

    // ---------------------------------------------------------------- 工具
    static int parseColor(String hex) {
        try {
            if (hex == null || hex.isEmpty()) {
                return Color.BLACK;
            }
            hex = hex.trim();
            if (hex.startsWith("#")) {
                hex = hex.substring(1);
            }
            if (hex.length() == 6) {
                return Color.rgb(Integer.parseInt(hex.substring(0, 2), 16),
                        Integer.parseInt(hex.substring(2, 4), 16),
                        Integer.parseInt(hex.substring(4, 6), 16));
            }
            if (hex.length() == 8) {
                return Color.argb(Integer.parseInt(hex.substring(0, 2), 16),
                        Integer.parseInt(hex.substring(2, 4), 16),
                        Integer.parseInt(hex.substring(4, 6), 16),
                        Integer.parseInt(hex.substring(6, 8), 16));
            }
        } catch (Exception ignored) {
            // fall through
        }
        return Color.BLACK;
    }

    // ---------------------------------------------------------------- 实体
    public static class Entity {
        int id;
        String name = "obj";
        String tag = "Untagged";
        boolean active = true;
        JSONObject programs;
        int parentId = 0;
        Entity parent;
        int layer;
        float x;
        float y;
        float width = 80f;
        float height = 60f;
        float rotation;
        float scale = 1f;

        String shape = "rect";
        int fill = Color.rgb(76, 139, 245);
        int outline = Color.rgb(18, 52, 86);
        String image = "";
        float opacity = 1f;

        String labelText = "";
        int fontSize = 18;
        int labelColor = Color.BLACK;
        boolean bold = false;
        String align = "center";

        boolean hasRigid = false;
        String bodyType = "static";
        float vx = 0f;
        float vy = 0f;
        float gravityScale = 1f;
        float drag = 0f;
        float bounce = 1f;

        boolean hasCollider = false;
        boolean isTrigger = false;
        float offsetX = 0f;
        float offsetY = 0f;
        float colliderW = 0f;
        float colliderH = 0f;

        boolean hasAnimator = false;
        String animEffect = "none";
        float animSpeed = 1f;
        float animAmplitude = 1f;
        boolean animAutoPlay = true;

        String tapAction = "none";
        boolean hasTimer = false;
        String timerAction = "none";
        float intervalMs = 1000f;
        boolean autoStart = true;
        boolean repeat = true;
        float timerElapsed = 0f;
        boolean timerDone = false;

        boolean hasSpawner = false;
        String spawnPrefab = "";
        float spawnIntervalMs = 1000f;
        int spawnMaxAlive = 0;
        float spawnOffsetX = 0f;
        float spawnOffsetY = 0f;
        float spawnElapsed = 0f;
        final List<Integer> spawned = new ArrayList<>();

        boolean hasCamera = false;
        String follow = "";
        float zoom = 1f;
        float smooth = 0.15f;

        boolean dead = false;

        static Entity fromJson(JSONObject o, int defaultFill, int defaultOutline) {
            Entity e = new Entity();
            e.id = o.optInt("id");
            e.name = o.optString("name", "obj");
            e.tag = o.optString("tag", "Untagged");
            e.active = o.optBoolean("active", true);
            e.parentId = o.optInt("parent", 0);
            e.readComponents(o.optJSONObject("components"), defaultFill, defaultOutline);
            return e;
        }

        static Entity fromPrefab(JSONObject prefab, int defaultFill, int defaultOutline) {
            Entity e = new Entity();
            e.name = prefab.optString("name", "obj");
            e.tag = prefab.optString("tag", "Untagged");
            e.readComponents(prefab.optJSONObject("components"), defaultFill, defaultOutline);
            return e;
        }

        void readComponents(JSONObject comps, int defaultFill, int defaultOutline) {
            if (comps == null) {
                return;
            }
            JSONObject t = comps.optJSONObject("Transform");
            if (t != null) {
                x = (float) t.optDouble("x", 0.0);
                y = (float) t.optDouble("y", 0.0);
                width = (float) t.optDouble("width", 80.0);
                height = (float) t.optDouble("height", 60.0);
                rotation = (float) t.optDouble("rotation", 0.0);
                scale = (float) t.optDouble("scale", 1.0);
                layer = t.optInt("layer", 0);
            }
            JSONObject s = comps.optJSONObject("Sprite");
            if (s != null) {
                shape = s.optString("shape", "rect");
                fill = parseColor(s.optString("fill", "#4C8BF5"));
                outline = parseColor(s.optString("outline", "#123456"));
                image = s.optString("image", "");
                opacity = (float) s.optDouble("opacity", 1.0);
            }
            JSONObject l = comps.optJSONObject("Label");
            if (l != null) {
                labelText = l.optString("text", "");
                fontSize = l.optInt("font_size", 18);
                labelColor = parseColor(l.optString("color", "#000000"));
                bold = l.optBoolean("bold", false);
                align = l.optString("align", "center");
            }
            JSONObject anim = comps.optJSONObject("Animator");
            if (anim != null) {
                hasAnimator = true;
                animEffect = anim.optString("effect", "none");
                animSpeed = (float) anim.optDouble("speed", 1.0);
                animAmplitude = (float) anim.optDouble("amplitude", 1.0);
                animAutoPlay = anim.optBoolean("auto_play", true);
            }
            JSONObject rb = comps.optJSONObject("Rigidbody2D");
            if (rb != null) {
                hasRigid = true;
                bodyType = rb.optString("body_type", "dynamic");
                vx = (float) rb.optDouble("velocity_x", 0.0);
                vy = (float) rb.optDouble("velocity_y", 0.0);
                gravityScale = (float) rb.optDouble("gravity_scale", 1.0);
                drag = (float) rb.optDouble("drag", 0.0);
                bounce = (float) rb.optDouble("bounce", 1.0);
            }
            JSONObject coll = comps.optJSONObject("BoxCollider2D");
            if (coll != null) {
                hasCollider = true;
                isTrigger = coll.optBoolean("is_trigger", false);
                offsetX = (float) coll.optDouble("offset_x", 0.0);
                offsetY = (float) coll.optDouble("offset_y", 0.0);
                colliderW = (float) coll.optDouble("width", 0.0);
                colliderH = (float) coll.optDouble("height", 0.0);
            }
            JSONObject tap = comps.optJSONObject("TapHandler");
            if (tap != null) {
                tapAction = tap.optString("action", "none");
            }
            JSONObject timer = comps.optJSONObject("Timer");
            if (timer != null) {
                hasTimer = true;
                timerAction = timer.optString("action", "none");
                intervalMs = (float) timer.optDouble("interval_ms", 1000.0);
                autoStart = timer.optBoolean("auto_start", true);
                repeat = timer.optBoolean("repeat", true);
            }
            JSONObject sp = comps.optJSONObject("Spawner");
            if (sp != null) {
                hasSpawner = true;
                spawnPrefab = sp.optString("prefab", "");
                spawnIntervalMs = (float) sp.optDouble("interval_ms", 1000.0);
                spawnMaxAlive = sp.optInt("max_alive", 0);
                spawnOffsetX = (float) sp.optDouble("offset_x", 0.0);
                spawnOffsetY = (float) sp.optDouble("offset_y", 0.0);
            }
            JSONObject cam = comps.optJSONObject("Camera2D");
            if (cam != null) {
                hasCamera = true;
                follow = cam.optString("follow", "");
                zoom = (float) cam.optDouble("zoom", 1.0);
                smooth = (float) cam.optDouble("smooth", 0.15);
            }
        }

        float[] world() {
            float wx = x;
            float wy = y;
            float ws = scale;
            Entity p = parent;
            int guard = 0;
            while (p != null && guard < 32) {
                wx = p.x + wx * p.scale;
                wy = p.y + wy * p.scale;
                ws *= p.scale;
                p = p.parent;
                guard++;
            }
            return new float[]{wx, wy, width * ws, height * ws, rotation, ws};
        }

        boolean activeInHierarchy() {
            Entity node = this;
            int guard = 0;
            while (node != null && guard < 32) {
                if (!node.active) {
                    return false;
                }
                node = node.parent;
                guard++;
            }
            return true;
        }

        float centerX() {
            float[] wt = world();
            return wt[0] + wt[2] / 2f;
        }

        float centerY() {
            float[] wt = world();
            return wt[1] + wt[3] / 2f;
        }

        void clampToScene(int sceneW, int sceneH) {
            float[] wt = world();
            float w = wt[2];
            float h = wt[3];
            if (x < 0f) {
                x = 0f;
                vx = Math.abs(vx) * bounce;
            } else if (x + w > sceneW) {
                x = sceneW - w;
                vx = -Math.abs(vx) * bounce;
            }
            if (y < 0f) {
                y = 0f;
                vy = Math.abs(vy) * bounce;
            } else if (y + h > sceneH) {
                y = sceneH - h;
                vy = -Math.abs(vy) * bounce;
            }
        }

        float[] colliderRect() {
            float[] wt = world();
            float w = colliderW > 0f ? colliderW * wt[5] : wt[2];
            float h = colliderH > 0f ? colliderH * wt[5] : wt[3];
            float left = wt[0] + offsetX * wt[5];
            float top = wt[1] + offsetY * wt[5];
            return new float[]{left, top, left + w, top + h};
        }

        void bounceOn(float dx, float dy) {
            if (Math.abs(dx) > Math.abs(dy)) {
                vx = -vx * bounce;
            } else {
                vy = -vy * bounce;
            }
        }

        float animRotation(float elapsed) {
            if (!hasAnimator || !animAutoPlay || !"spin".equals(animEffect)) {
                return 0f;
            }
            return (elapsed * animSpeed * 90f) % 360f;
        }

        float animScale(float elapsed) {
            if (!hasAnimator || !animAutoPlay || !"pulse".equals(animEffect)) {
                return 1f;
            }
            return 1f + 0.25f * animAmplitude * (float) Math.sin(elapsed * animSpeed * 3f);
        }

        float animOpacity(float elapsed) {
            if (!hasAnimator || !animAutoPlay || !"fade".equals(animEffect)) {
                return 1f;
            }
            float v = 0.5f + 0.5f * (float) Math.sin(elapsed * animSpeed * 2f);
            return Math.max(0f, Math.min(1f, v));
        }
    }
}
"""


def _script_vm(package):
    """生成 ScriptVM.java（脚本子集的解释器）。"""
    return SCRIPT_VM_JAVA.replace("@PACKAGE@", package)


SCRIPT_VM_JAVA = r"""package @PACKAGE@;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.HashMap;
import java.util.Map;

/**
 * tkunity 脚本虚拟机：解释执行由 tkunity.script 编译出的 JSON AST。
 * 只依赖 org.json，与桌面预览的 Python 语法子集语义保持一致。
 */
public final class ScriptVM {

    public static final int T_NUM = 0;
    public static final int T_STR = 1;
    public static final int T_BOOL = 2;
    public static final int T_NONE = 3;

    private static final int MAX_STEPS = 200000;

    public static final class ScriptError extends RuntimeException {
        public ScriptError(String message) {
            super(message);
        }
    }

    public static final class Val {
        public final int type;
        public final double num;
        public final String str;

        private Val(int type, double num, String str) {
            this.type = type;
            this.num = num;
            this.str = str;
        }

        public static Val num(double value) {
            return new Val(T_NUM, value, null);
        }

        public static Val str(String value) {
            return new Val(T_STR, 0.0, value == null ? "" : value);
        }

        public static Val bool(boolean value) {
            return new Val(T_BOOL, value ? 1.0 : 0.0, null);
        }

        public static Val none() {
            return new Val(T_NONE, 0.0, null);
        }

        public boolean isNone() {
            return type == T_NONE;
        }

        public boolean truth() {
            if (type == T_NONE) {
                return false;
            }
            if (type == T_BOOL || type == T_NUM) {
                return num != 0.0;
            }
            return str != null && str.length() > 0;
        }

        public double asNumber() {
            if (type == T_NUM || type == T_BOOL) {
                return num;
            }
            if (type == T_STR) {
                try {
                    return Double.parseDouble(str);
                } catch (NumberFormatException exc) {
                    throw new ScriptError("无法转成数字: " + str);
                }
            }
            throw new ScriptError("无法把 None 转成数字");
        }

        public String asString() {
            if (type == T_STR) {
                return str;
            }
            if (type == T_NONE) {
                return "None";
            }
            if (type == T_BOOL) {
                return num != 0.0 ? "True" : "False";
            }
            if (num == Math.floor(num) && !Double.isInfinite(num)) {
                return String.valueOf((long) num);
            }
            return String.valueOf(num);
        }
    }

    public interface Host {
        Val get(String name);

        void set(String name, Val value);

        Val call(String fn, Val[] args);

        void log(String message);
    }

    private final Host host;
    private final Map<String, Val> vars = new HashMap<String, Val>();
    private int steps = 0;
    private boolean breakFlag = false;
    private boolean continueFlag = false;

    private ScriptVM(Host host) {
        this.host = host;
    }

    public static boolean run(JSONObject program, Host host) {
        if (program == null) {
            return false;
        }
        try {
            new ScriptVM(host).execBlock(program.optJSONArray("stmts"));
            return true;
        } catch (ScriptError exc) {
            host.log("[script] " + exc.getMessage());
        } catch (RuntimeException exc) {
            host.log("[script] runtime error: " + exc);
        }
        return false;
    }

    private void tick() {
        steps++;
        if (steps > MAX_STEPS) {
            throw new ScriptError("too many steps (infinite loop?)");
        }
    }

    private void execBlock(JSONArray block) {
        if (block == null) {
            return;
        }
        for (int i = 0; i < block.length(); i++) {
            if (breakFlag || continueFlag) {
                return;
            }
            JSONObject stmt = block.optJSONObject(i);
            if (stmt != null) {
                exec(stmt);
            }
        }
    }

    private void exec(JSONObject stmt) {
        tick();
        String kind = stmt.optString("t");
        if ("assign".equals(kind)) {
            String name = stmt.optString("name");
            Val value = evalExpr(stmt.optJSONObject("e"));
            String op = stmt.optString("op", "=");
            if (!"=".equals(op)) {
                value = binop(op, lookup(name), value);
            }
            vars.put(name, value);
            host.set(name, value);
        } else if ("if".equals(kind)) {
            if (evalExpr(stmt.optJSONObject("c")).truth()) {
                execBlock(stmt.optJSONArray("then"));
            } else {
                execBlock(stmt.optJSONArray("else"));
            }
        } else if ("while".equals(kind)) {
            boolean broke = false;
            while (evalExpr(stmt.optJSONObject("c")).truth()) {
                tick();
                execBlock(stmt.optJSONArray("body"));
                if (breakFlag) {
                    breakFlag = false;
                    broke = true;
                    break;
                }
                continueFlag = false;
            }
            if (!broke) {
                execBlock(stmt.optJSONArray("else"));
            }
        } else if ("for".equals(kind)) {
            execFor(stmt);
        } else if ("expr".equals(kind)) {
            evalExpr(stmt.optJSONObject("e"));
        } else if ("pass".equals(kind)) {
            // 空语句
        } else if ("break".equals(kind)) {
            breakFlag = true;
        } else if ("continue".equals(kind)) {
            continueFlag = true;
        } else {
            throw new ScriptError("unknown statement: " + kind);
        }
    }

    private void execFor(JSONObject stmt) {
        JSONArray args = stmt.optJSONArray("args");
        int count = args == null ? 0 : args.length();
        double start = 0.0;
        double stop = 0.0;
        double stepSize = 1.0;
        if (count == 1) {
            stop = evalExpr(args.optJSONObject(0)).asNumber();
        } else if (count == 2) {
            start = evalExpr(args.optJSONObject(0)).asNumber();
            stop = evalExpr(args.optJSONObject(1)).asNumber();
        } else if (count == 3) {
            start = evalExpr(args.optJSONObject(0)).asNumber();
            stop = evalExpr(args.optJSONObject(1)).asNumber();
            stepSize = evalExpr(args.optJSONObject(2)).asNumber();
        } else {
            throw new ScriptError("range() argument count");
        }
        if (stepSize == 0.0) {
            throw new ScriptError("range() step must not be zero");
        }
        String varName = stmt.optString("var", "i");
        boolean broke = false;
        double value = start;
        while (stepSize > 0 ? value < stop : value > stop) {
            tick();
            vars.put(varName, Val.num(value));
            host.set(varName, Val.num(value));
            execBlock(stmt.optJSONArray("body"));
            if (breakFlag) {
                breakFlag = false;
                broke = true;
                break;
            }
            continueFlag = false;
            value += stepSize;
        }
        if (!broke) {
            execBlock(stmt.optJSONArray("else"));
        }
    }

    private Val evalExpr(JSONObject expr) {
        if (expr == null) {
            throw new ScriptError("empty expression");
        }
        tick();
        String kind = expr.optString("t");
        if ("num".equals(kind)) {
            return Val.num(expr.optDouble("v", 0.0));
        }
        if ("str".equals(kind)) {
            return Val.str(expr.optString("v", ""));
        }
        if ("const".equals(kind)) {
            return Val.bool(expr.optBoolean("v", false));
        }
        if ("none".equals(kind)) {
            return Val.none();
        }
        if ("name".equals(kind)) {
            return lookup(expr.optString("v"));
        }
        if ("bin".equals(kind)) {
            return binop(expr.optString("op"), evalExpr(expr.optJSONObject("a")),
                    evalExpr(expr.optJSONObject("b")));
        }
        if ("un".equals(kind)) {
            Val value = evalExpr(expr.optJSONObject("a"));
            if ("-".equals(expr.optString("op"))) {
                return Val.num(-value.asNumber());
            }
            return Val.bool(!value.truth());
        }
        if ("bool".equals(kind)) {
            Val left = evalExpr(expr.optJSONObject("a"));
            if ("and".equals(expr.optString("op"))) {
                return left.truth() ? evalExpr(expr.optJSONObject("b")) : left;
            }
            return left.truth() ? left : evalExpr(expr.optJSONObject("b"));
        }
        if ("cmp".equals(kind)) {
            return compare(expr.optString("op"), evalExpr(expr.optJSONObject("a")),
                    evalExpr(expr.optJSONObject("b")));
        }
        if ("call".equals(kind)) {
            return call(expr);
        }
        if ("ifexp".equals(kind)) {
            if (evalExpr(expr.optJSONObject("c")).truth()) {
                return evalExpr(expr.optJSONObject("a"));
            }
            return evalExpr(expr.optJSONObject("b"));
        }
        throw new ScriptError("unknown expression: " + kind);
    }

    private Val lookup(String name) {
        if (vars.containsKey(name)) {
            return vars.get(name);
        }
        Val value = host.get(name);
        if (value == null) {
            throw new ScriptError("unknown variable: " + name);
        }
        return value;
    }

    private Val call(JSONObject expr) {
        String fn = expr.optString("fn");
        JSONArray argNodes = expr.optJSONArray("args");
        int count = argNodes == null ? 0 : argNodes.length();
        Val[] args = new Val[count];
        for (int i = 0; i < count; i++) {
            args[i] = evalExpr(argNodes.optJSONObject(i));
        }
        return host.call(fn, args);
    }

    private Val binop(String op, Val a, Val b) {
        if ("+".equals(op) && (a.type == T_STR || b.type == T_STR)) {
            return Val.str(a.asString() + b.asString());
        }
        double left = a.asNumber();
        double right = b.asNumber();
        if ("+".equals(op)) {
            return Val.num(left + right);
        }
        if ("-".equals(op)) {
            return Val.num(left - right);
        }
        if ("*".equals(op)) {
            return Val.num(left * right);
        }
        if ("/".equals(op)) {
            if (right == 0.0) {
                throw new ScriptError("division by zero");
            }
            return Val.num(left / right);
        }
        if ("//".equals(op)) {
            if (right == 0.0) {
                throw new ScriptError("division by zero");
            }
            return Val.num(Math.floor(left / right));
        }
        if ("%".equals(op)) {
            if (right == 0.0) {
                throw new ScriptError("division by zero");
            }
            return Val.num(left - Math.floor(left / right) * right);
        }
        if ("**".equals(op)) {
            return Val.num(Math.pow(left, right));
        }
        throw new ScriptError("unknown operator: " + op);
    }

    private Val compare(String op, Val a, Val b) {
        if ("is".equals(op)) {
            if (a.isNone() || b.isNone()) {
                return Val.bool(a.isNone() && b.isNone());
            }
            return Val.bool(equalsVal(a, b));
        }
        if ("is not".equals(op)) {
            if (a.isNone() || b.isNone()) {
                return Val.bool(!(a.isNone() && b.isNone()));
            }
            return Val.bool(!equalsVal(a, b));
        }
        if ("==".equals(op)) {
            return Val.bool(equalsVal(a, b));
        }
        if ("!=".equals(op)) {
            return Val.bool(!equalsVal(a, b));
        }
        if (a.type == T_STR && b.type == T_STR) {
            int c = a.str.compareTo(b.str);
            if ("<".equals(op)) {
                return Val.bool(c < 0);
            }
            if ("<=".equals(op)) {
                return Val.bool(c <= 0);
            }
            if (">".equals(op)) {
                return Val.bool(c > 0);
            }
            if (">=".equals(op)) {
                return Val.bool(c >= 0);
            }
        }
        double left = a.asNumber();
        double right = b.asNumber();
        if ("<".equals(op)) {
            return Val.bool(left < right);
        }
        if ("<=".equals(op)) {
            return Val.bool(left <= right);
        }
        if (">".equals(op)) {
            return Val.bool(left > right);
        }
        if (">=".equals(op)) {
            return Val.bool(left >= right);
        }
        throw new ScriptError("unknown comparison: " + op);
    }

    private boolean equalsVal(Val a, Val b) {
        if (a.isNone() || b.isNone()) {
            return a.isNone() && b.isNone();
        }
        if (a.type == T_STR || b.type == T_STR) {
            return a.asString().equals(b.asString());
        }
        return a.asNumber() == b.asNumber();
    }
}
"""
