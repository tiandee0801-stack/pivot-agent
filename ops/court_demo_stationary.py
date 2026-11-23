"""Pose and phase definitions for Pivot's two stationary court clips."""

from math import cos, pi, sin
import sys
from pathlib import Path

from court_demo_renderer import add, eased, render_demo, solve_leg


def athlete(pelvis, chest, head, feet, span, swings, flexions):
    joints = {"pelvis": pelvis, "chest": chest, "head": head}
    for index, side in enumerate(("L", "R")):
        direction = (-1, 1)[index]
        hip = add(pelvis, (0.0, direction * 0.115, 0.0))
        shoulder = add(chest, (0.0, direction * 0.205, 0.0))
        angle = swings[index]
        forearm = angle + flexions[index]
        elbow = add(shoulder, (0.265 * sin(angle), direction * 0.035, -0.265 * cos(angle)))
        wrist = add(elbow, (0.255 * sin(forearm), -direction * 0.017, -0.255 * cos(forearm)))
        x, lift, pitch = feet[index]
        ankle = (x, direction * span, 0.073 + lift)
        toe = (x + 0.16, direction * (span + 0.022), 0.034 + lift + pitch)
        for name, point in [
            ("hip", hip), ("knee", solve_leg(hip, ankle, thigh=0.42, calf=0.417)),
            ("ankle", ankle), ("toe", toe),
            ("shoulder", shoulder), ("elbow", elbow), ("wrist", wrist),
        ]:
            joints[side + name] = point
    contacts = tuple(side for side, foot in zip(("L", "R"), feet) if foot[1] <= 0.002)
    return joints, contacts


MARCH_STEPS = [
    (0.48, 1.18),
    (1.34, 2.00),
    (2.13, 2.75),
    (2.86, 3.45),
    (3.54, 4.08),
    (4.15, 4.62),
]


def march_pose(t):
    feet = [(0.008, 0.0, 0.0)] * 2
    active_arm = 0
    body_shift = 0
    bounce = 0
    for index, (start, end) in enumerate(MARCH_STEPS):
        if not start < t < end:
            continue
        side = index % 2
        direction = (1, -1)[side]
        u = (t - start) / (end - start)
        up = sin(pi * u)**1.55
        lift = (0.115 + index * 0.008) * up
        feet[side] = (0.008 + 0.11 * up, lift, 0.014 * sin(2 * pi * u) * up)
        active_arm = direction * up
        body_shift = direction * 0.033 * up
        bounce = 0.009 * up
        break
    return athlete(
        (-0.017, body_shift, 0.896 + bounce),
        (0.024, body_shift * 0.63, 1.382 + bounce),
        (0.049, body_shift * 0.52, 1.638 + bounce),
        feet, 0.13, (-active_arm * 0.355 - 0.045, active_arm * 0.355 - 0.045),
        (0.32 - active_arm * 0.15, 0.32 + active_arm * 0.15),
    )


SNAP_REPS = [(0.65, 0.97, 2.12, 2.77), (3.06, 3.35, 4.53, 5.15)]


def snap_pose(t):
    low = 0
    for start, landing, stand, end in SNAP_REPS:
        if start <= t < landing:
            low = eased((t - start) / (landing - start))
        elif landing <= t < stand:
            low = 1
        elif stand <= t < end:
            low = 1 - eased((t - stand) / (end - stand))
    reach = 0.14 + low * 0.55
    return athlete(
        (-0.022 - low * 0.158, 0, 0.9 - low * 0.23),
        (0.005 + low * 0.05, 0, 1.38 - low * 0.278),
        (0.034 + low * 0.092, 0, 1.637 - low * 0.302),
        [(0.02, 0.0, 0.0), (0.02, 0.0, 0.0)], 0.208,
        (reach - 0.15, reach - 0.15), (0.27 + 0.44 * low, 0.27 + 0.44 * low),
    )


def main():
    app_assets = Path(__file__).resolve().parents[1] / "web" / "assets" / "demos"
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else app_assets
    names = set(sys.argv[2:]) or {"march_in_place", "snap_down"}
    if "march_in_place" in names:
        render_demo(
            dest, "march_in_place", "原地踏步热身", "侧前方观察", 5.3, -62,
            [
                (0.0, "站稳准备", "双脚踩稳"),
                (0.48, "原地踏步", "交替抬脚，手臂自然摆动"),
                (2.86, "逐步加快", "双脚轮流支撑，身体留在原位"),
                (4.62, "回到站姿", "双脚踩稳，随时能停住"),
            ],
            march_pose, path_axis=None, poster_at=1.69,
        )
    if "snap_down" in names:
        render_demo(
            dest, "snap_down", "快速下沉定住", "侧前方观察", 5.55, -47,
            [
                (0.0, "站稳准备", "双脚保持原位"),
                (0.65, "快速下沉", "同时屈髋、屈膝"),
                (0.97, "停稳", "脚踩实后保持预备姿势"),
                (2.12, "起身复位", "稳稳站起，准备下一次"),
                (3.06, "快速下沉", "同时屈髋、屈膝"),
                (3.35, "停稳", "脚踩实后保持预备姿势"),
                (4.53, "起身复位", "控制好动作再加快"),
            ],
            snap_pose, path_axis=None, poster_at=1.46,
        )


if __name__ == "__main__":
    main()
