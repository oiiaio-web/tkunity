# -*- coding: utf-8 -*-
"""用 tkunity API 生成示例游戏 examples/demo.pyu（无需打开编辑器）。

演示这一版的 Unity 化能力：父子层级、刚体物理、碰撞体、预制体、生成器、
摄像机跟随、动画补间、生命周期脚本。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tkunity import GameObject, Project, save


def build():
    p = Project("弹球竞技场", 960, 640, background="#1e1e2e", gravity=1400)

    # ---- 场地（静态碰撞体）----
    ground = GameObject("地面", 0, 600, 960, 40, tag="Ground")
    ground.add_sprite("rect", fill="#313244", outline="#45475a")
    ground.add_collider()
    p.add(ground)

    left = GameObject("左墙", -20, 0, 20, 640, tag="Ground")
    left.add_sprite("rect", fill="#313244", outline="#45475a")
    left.add_collider()
    p.add(left)

    right = GameObject("右墙", 960, 0, 20, 640, tag="Ground")
    right.add_sprite("rect", fill="#313244", outline="#45475a")
    right.add_collider()
    p.add(right)

    # ---- 弹球（动态刚体 + 碰撞 + 自转动画 + 脚本）----
    ball = GameObject("球", 460, 60, 56, 56, tag="Player")
    ball.add_sprite("oval", fill="#f38ba8", outline="#f9e2af")
    ball.add_rigidbody(velocity_x=180, velocity_y=-120, bounce=0.92, drag=0.02)
    ball.add_collider()
    ball.add_animator("spin", speed=1.2)
    ball.add_script(
        name="BallBehaviour",
        on_start="log('ball spawned')",
        on_update="if y > 560: vy = -abs(vy) - 40",
        on_collision="log('hit ' + other)",
    )
    p.add(ball)

    # ---- 玩家方块（运动学刚体不吃重力，脚本左右巡逻）----
    player = GameObject("玩家", 60, 480, 80, 80, tag="Player")
    player.add_sprite("rect", fill="#89b4fa", outline="#74c7ec")
    player.add_rigidbody(body_type="kinematic", gravity_scale=0.0)
    player.add_script(
        name="PlayerPatrol",
        on_update="vx = 160 if x < 500 else -160",
    )
    p.add(player)

    # ---- 金币预制体（生成器刷出来的东西）----
    coin = GameObject("金币", 0, 0, 28, 28, tag="Pickup")
    coin.add_sprite("oval", fill="#f9e2af", outline="#b8860b")
    coin.add_rigidbody(gravity_scale=0.5, bounce=0.4)
    coin.add_collider()
    coin.add_animator("pulse", speed=2.0, amplitude=0.8)
    p.add(coin)
    p.save_prefab(coin, "coin")
    p.remove(coin)

    # ---- 生成器：每 1.2 秒从顶部刷一枚金币，最多 6 枚 ----
    spawner = GameObject("金币生成器", 460, 40, 40, 40)
    spawner.add_spawner("coin", interval_ms=1200, max_alive=6, offset_x=-14, offset_y=-14)
    p.add(spawner)

    # ---- 得分触发区（只做演示：有东西进来就打印）----
    zone = GameObject("得分区", 0, 560, 960, 90)
    zone.add_collider(is_trigger=True)
    zone.add_script(on_collision="log('enter zone: ' + other)")
    p.add(zone)

    # ---- 主相机：跟随球 ----
    camera = GameObject("主相机", 480, 320, 20, 20)
    camera.add_camera(follow="球", zoom=1.05, smooth=0.12)
    p.add(camera)

    # ---- UI 文本 ----
    title = GameObject("标题", 330, 12, 300, 40)
    title.add_label("tkunity 弹球竞技场", font_size=26, color="#f9e2af", bold=True)
    p.add(title)

    hint = GameObject("提示", 300, 600, 360, 30)
    hint.add_label("方向键移动玩家 / 点球试试", font_size=14, color="#a6adc8")
    hint.add_tap("bounce")
    p.add(hint)

    return p


def main():
    p = build()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.pyu")
    save(p, out)
    print("[demo] 已生成: %s（物体 %d 个，预制体 %d 个）"
          % (out, len(p.to_dict()["entities"]), len(p.prefabs)))
    return out


if __name__ == "__main__":
    main()
