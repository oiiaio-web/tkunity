# -*- coding: utf-8 -*-
"""用 tkunity API 生成 3D 示例 examples/demo3d.pyu（无需打开编辑器）。

演示 3.5 之后的 3D 能力：Transform3D + Mesh3D + Camera3D，纯软件渲染。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tkunity import GameObject, Project, save


def build():
    p = Project("3D 展示", 960, 640, background="#12121a")

    ground = GameObject("地面", 0, 0, 960, 640)
    ground.set_component("Transform3D", x=0.0, y=-0.5, z=0.0, scale=6.0)
    ground.set_component("Mesh3D", shape="plane", color="#45475a")
    p.add(ground)

    cube = GameObject("中心方块", 0, 0, 60, 60)
    cube.set_component("Transform3D", x=0.0, y=0.5, z=0.0, ry=25.0)
    cube.set_component("Mesh3D", shape="cube", color="#89b4fa")
    cube.set_component("Animator", effect="spin", speed=1.0)
    p.add(cube)

    sphere = GameObject("金球", 0, 0, 60, 60)
    sphere.set_component("Transform3D", x=1.8, y=0.6, z=-0.4, scale=1.2)
    sphere.set_component("Mesh3D", shape="sphere", color="#f9e2af")
    p.add(sphere)

    pyramid = GameObject("粉棱锥", 0, 0, 60, 60)
    pyramid.set_component("Transform3D", x=-1.8, y=0.6, z=0.6, ry=-15.0)
    pyramid.set_component("Mesh3D", shape="pyramid", color="#f38ba8")
    p.add(pyramid)

    cylinder = GameObject("绿圆柱", 0, 0, 60, 60)
    cylinder.set_component("Transform3D", x=0.4, y=0.5, z=-2.2, scale=0.8)
    cylinder.set_component("Mesh3D", shape="cylinder", color="#a6e3a1")
    p.add(cylinder)

    camera = GameObject("3D 相机", 0, 0, 40, 40)
    camera.set_component("Camera3D", yaw=35.0, pitch=22.0, distance=6.5,
                         fov=50.0, target_x=0.0, target_y=0.6, target_z=0.0)
    p.add(camera)

    return p


def main():
    p = build()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo3d.pyu")
    save(p, out)
    print("[demo3d] 已生成: %s（物体 %d 个）" % (out, len(p.to_dict()["entities"])))
    return out


if __name__ == "__main__":
    main()
