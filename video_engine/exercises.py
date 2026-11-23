"""Exercise geometry adapted from Good-GYM/data/exercises.json (MIT)."""
import math
from .counter import CurlCounter
EXERCISES = {
 'squat': dict(name='深蹲', en='Squat', indices=(11,13,15), extended=160, flexed=110, invert=False, view='侧面拍摄，髋、膝和脚踝完整入镜', group='下肢'),
 # A 2D elbow projection need not reach an anatomical 180 degrees. These
 # hysteresis thresholds observe cycles, never certify push-up form or depth.
 'pushup': dict(name='俯卧撑', en='Push-up', indices=(5,7,9), extended=145, flexed=110, invert=False, view='从侧面拍摄，肩、肘、手腕和髋部清晰可见', group='胸部'),
 'bicep_curl': dict(name='哑铃弯举', en='Bicep Curl', indices=(5,7,9), extended=150, flexed=70, invert=False, view='侧前方拍摄，肩、肘和手腕完整入镜', group='手臂'),
 'lateral_raise': dict(name='侧平举', en='Lateral Raise', indices=(11,5,7), extended=150, flexed=100, invert=True, view='正面拍摄，上半身和双臂完整入镜', group='肩部'),
 'overhead_press': dict(name='肩上推举', en='Overhead Press', indices=(11,5,7), extended=80, flexed=30, invert=True, view='侧前方拍摄，髋、肩、肘清晰可见，举过头顶时手臂仍在画面内', group='肩部'),
}
def public_exercises():
 return [dict(id=k, name=v['name'], english=v['en'], guidance=v['view'], group=v['group']) for k,v in EXERCISES.items()]
def measure(points,side,exercise,min_score=.5):
 if side not in ('left','right'):raise ValueError('invalid side')
 cfg=EXERCISES[exercise]; offset=0 if side=='left' else 1
 try:
  selected=[[float(v) for v in points[i+offset][:3]] for i in cfg['indices']]
  if any(len(p)<3 or not all(math.isfinite(v) for v in p) or p[2]<min_score for p in selected): return None
  if exercise=='pushup':
   # Elbow flexion alone also occurs in a curl. Require a visible,
   # approximately horizontal torso before treating it as a push-up cycle.
   shoulder=selected[0]
   hip=[float(v) for v in points[11+offset][:3]]
   if len(hip)<3 or not all(math.isfinite(v) for v in hip) or hip[2]<min_score:return None
   dx,dy=hip[0]-shoulder[0],hip[1]-shoulder[1]
   length=math.hypot(dx,dy)
   if length<.03 or abs(dy)/length>.65:return None
 except (IndexError,TypeError,ValueError,OverflowError):return None
 a,b,c=selected; u=(a[0]-b[0],a[1]-b[1]);v=(c[0]-b[0],c[1]-b[1]); lu=math.hypot(*u);lv=math.hypot(*v)
 if min(lu,lv)<.015:return None
 return math.degrees(math.acos(max(-1,min(1,(u[0]*v[0]+u[1]*v[1])/(lu*lv)))))
def make_counter(exercise):
 c=EXERCISES[exercise]
 return CurlCounter(extended=c['extended'],flexed=c['flexed'])
def counter_angle(angle,exercise):
 return None if angle is None else 180-angle if EXERCISES[exercise]['invert'] else angle
