"""Foot-plant trajectories for the three Pivot directional court drills."""
import math
import argparse
from dataclasses import dataclass
from pathlib import Path

from court_demo_renderer import clamp, eased, render_demo, solve_leg


@dataclass(frozen=True)
class Step:
    begin: float
    end: float
    target: float
    lift: float


def foot(time, initial, steps):
    plant=initial
    for step in steps:
        if time<step.begin:
            return plant,0,True
        if time<step.end:
            fraction=(time-step.begin)/(step.end-step.begin)
            along=plant+(step.target-plant)*eased(fraction)
            return along,step.lift*math.sin(math.pi*fraction),False
        plant=step.target
    return plant,0,True


def lerp_curve(time, elements):
    for (a,x),(b,y) in zip(elements,elements[1:]):
        if time <= b:
            return x + (y-x)*eased((time-a)/(b-a))
    return elements[-1][1]


def straight_pose(time, tracks, lean_track, hip_track):
    feet={side:foot(time,*tracks[side]) for side in ("L","R")}
    motion=(feet["L"][0]+feet["R"][0])/2
    lean=lerp_curve(time,lean_track)
    ready=lerp_curve(time,hip_track)
    lift=feet["L"][1]+feet["R"][1]
    body=ready + .15*lift
    pelvis=(motion+.17*lean,0,body)
    chest=(pelvis[0]+lean,0,body+.44-.25*lean*lean)
    head=(chest[0]+.06*lean,0,chest[2]+.23)
    joints={"pelvis":pelvis,"chest":chest,"head":head}
    stride=clamp((feet["L"][0]-feet["R"][0])/.52,-1,1)
    arm_energy=min(1,abs(stride)*1.15)
    for side,sign in (("L",-1),("R",1)):
        x,z,_=feet[side]
        hip=(pelvis[0],sign*.10,pelvis[2])
        ankle=(x,sign*.105,.065+z)
        knee=solve_leg(hip,ankle)
        toe=(x+.145,sign*.106,.033+z*.76)
        shoulder=(chest[0],sign*.195,chest[2]-.027)
        swing=stride*sign
        elbow=(shoulder[0]-.095+.17*swing,sign*.23,shoulder[2]-.247-.023*swing)
        wrist=(elbow[0]+.16+.072*arm_energy+.020*swing,sign*.22,elbow[2]+.037+.110*arm_energy)
        joints.update({side+n:p for n,p in {"hip":hip,"knee":knee,"ankle":ankle,"toe":toe,
                                            "shoulder":shoulder,"elbow":elbow,"wrist":wrist}.items()})
    return joints,tuple(side for side,motion in feet.items() if motion[2])


def acceleration(time):
    tracks={
      "L":(-2.24,[Step(.94,1.44,-1.64,.17),Step(1.77,2.15,-.63,.21),Step(2.43,2.78,.59,.24),
                  Step(3.05,3.43,1.59,.18),Step(3.88,4.31,2.26,.08)]),
      "R":(-2.08,[Step(1.36,1.85,-1.15,.20),Step(2.08,2.45,-.04,.23),Step(2.72,3.11,1.16,.23),
                  Step(3.36,3.85,1.97,.14),Step(4.22,4.73,2.37,.07)]),
    }
    lean=[(0,.02),(.92,.18),(1.52,.24),(2.54,.26),(3.30,.22),(3.92,.12),(4.65,.015)]
    hip=[(0,.865),(.91,.79),(1.43,.745),(2.55,.725),(3.52,.745),(4.22,.797),(4.74,.864)]
    return straight_pose(time,tracks,lean,hip)


def braking(time):
    tracks={
      "L":(-2.18,[Step(.67,1.05,-1.59,.17),Step(1.36,1.71,-.55,.20),Step(2.00,2.32,.48,.18),
                  Step(2.56,2.94,1.25,.14),Step(3.33,3.79,1.75,.09),Step(4.28,4.66,2.025,.048)]),
      "R":(-1.98,[Step(.97,1.43,-1.08,.20),Step(1.63,2.05,-.04,.2),Step(2.26,2.64,.91,.16),
                  Step(2.89,3.36,1.53,.11),Step(3.73,4.19,1.84,.063)]),
    }
    lean=[(0,.085),(.66,.21),(1.78,.215),(2.34,.15),(3.16,.095),(3.92,.115),(4.68,.06)]
    hip=[(0,.85),(.68,.77),(1.7,.77),(2.30,.75),(2.95,.706),(3.89,.747),(4.67,.812)]
    return straight_pose(time,tracks,lean,hip)


def lateral(time):
    tracks={
      "L":(-.54,[Step(1.34,1.76,-.01,.079),Step(2.08,2.43,.53,.088),Step(2.85,3.24,.88,.068),
                Step(4.31,4.76,.32,.083),Step(5.10,5.54,-.25,.09),Step(5.88,6.33,-.62,.072)]),
      "R":(-.08,[Step(.86,1.32,.44,.084),Step(1.72,2.10,1.00,.089),Step(2.39,2.83,1.33,.074),
                 Step(4.72,5.11,.78,.084),Step(5.52,5.95,.22,.085),Step(6.30,6.77,-.16,.063)]),
    }
    feet={side:foot(time,*tracks[side]) for side in ("L","R")}
    mid=(feet["L"][0]+feet["R"][0])/2
    forward=.035+.014*math.sin(time*3)
    depth=lerp_curve(time,[(0,.825),(.77,.717),(2.53,.729),(3.30,.705),(4.24,.726),(5.12,.737),(6.73,.701)])
    depth+=(feet["L"][1]+feet["R"][1])*.14
    drift=lerp_curve(time,[(0,0),(.91,.047),(2.74,.035),(3.25,0),(4.28,-.041),(6.22,-.035),(6.78,0)])
    pelvis=(forward,mid+drift,depth)
    chest=(forward+.13,mid+drift+.01,depth+.435)
    head=(chest[0]+.025,chest[1],chest[2]+.23)
    joints={"pelvis":pelvis,"chest":chest,"head":head}
    for side,sign in (("L",-1),("R",1)):
        along,z,_=feet[side]
        hip=(pelvis[0],pelvis[1]+sign*.11,pelvis[2])
        ankle=(-.018,along,.063+z)
        toe=(.13,along+sign*.026,.034+.77*z)
        knee=solve_leg(hip,ankle)
        shoulder=(chest[0],chest[1]+sign*.206,chest[2]-.035)
        elbow=(shoulder[0]+.031,shoulder[1]+sign*.20,shoulder[2]-.18)
        wrist=(elbow[0]+.21,elbow[1]+sign*.027,elbow[2]+.07)
        joints.update({side+n:p for n,p in {"hip":hip,"knee":knee,"ankle":ankle,"toe":toe,
                                            "shoulder":shoulder,"elbow":elbow,"wrist":wrist}.items()})
    return joints,tuple(side for side,data in feet.items() if data[2])


MOVES=[
 ("short_acceleration","短距离启动","侧前方视角",5.8,-20,
   [(0,"准备","站稳，确认前方和减速空间已清空"),
    (.94,"启动","沿直线迈出第一步"),
    (1.50,"提速","步幅逐渐拉开，摆臂随步伐加快"),
    (3.37,"放缓","留出跑出空间，几步逐渐放慢")],
   acceleration,{"poster_at":2.55}),
 ("linear_braking","直线减速停稳","侧前方视角",6.0,-19,
   [(0,"前移","在清空的直线区域沿同一方向移动"),
    (.67,"可控速度","用可控制的速度前进"),
    (2.28,"多步减速","逐渐缩短步幅，连续几步过渡"),
    (4.67,"停稳","两脚踩稳，身体保持平衡")],
   braking,{"poster_at":2.92}),
 ("lateral_shuffle_stop","侧移后制动","正前方视角",7.8,-89,
   [(0,"预备","身体朝前，两脚保持间距"),
    (.86,"侧向滑步","向一侧滑步，保持胸口朝前"),
    (2.39,"减小步幅","用更短的滑步停稳"),
    (4.30,"换侧","停稳后换向，再用短步停稳")],
   lateral,{"path_axis":"y","poster_at":2.67}),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("clips", nargs="*", help="Optional movement IDs.")
    args = parser.parse_args()
    unknown = set(args.clips) - {clip[0] for clip in MOVES}
    if unknown:
        parser.error("Unknown movement IDs: " + ", ".join(sorted(unknown)))
    for clip_id, title, view, duration, yaw, phases, pose, options in MOVES:
        if not args.clips or clip_id in args.clips:
            render_demo(args.destination, clip_id, title, view, duration, yaw, phases, pose, **options)


if __name__=="__main__":
    main()
