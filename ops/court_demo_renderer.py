"""Render Pivot court demonstrations using original joint trajectories."""
import math
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

WIDTH, HEIGHT = 960, 540
SCALE = 153
FLOOR = 386
FPS = 24
CJK = os.environ.get("PIVOT_DEMO_CJK_FONT", "/System/Library/Fonts/STHeiti Medium.ttc")
LATIN = os.environ.get("PIVOT_DEMO_LATIN_FONT", "/System/Library/Fonts/Avenir Next.ttc")
MUTED = "#a0abc7"
TEXT = "#f3f5ff"
BLUE = "#b4b0ff"
COURT_LINE = "#2d3d54"


@lru_cache
def font(size, latin=False):
    return ImageFont.truetype(LATIN if latin else CJK, size)


def add(point, offset):
    return tuple(a + b for a, b in zip(point, offset))


def middle(a, b, mix=0.5):
    return tuple(x * (1 - mix) + y * mix for x, y in zip(a, b))


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def eased(value):
    value = clamp(value)
    return value * value * (3 - 2 * value)


def solve_leg(hip, ankle, forward=(1, 0, 0), thigh=0.44, calf=0.43):
    """Find a forward-bending knee between a fixed hip and foot."""
    delta = tuple(a - h for h, a in zip(hip, ankle))
    distance = math.sqrt(sum(value * value for value in delta))
    line = tuple(value / max(distance, 0.001) for value in delta)
    used_distance = min(thigh + calf - 0.002, distance)
    along = (thigh * thigh - calf * calf + used_distance * used_distance) / (2 * used_distance)
    perpendicular = math.sqrt(max(0, thigh * thigh - along * along))
    dot = sum(a * b for a, b in zip(line, forward))
    bend = tuple(a - dot * b for a, b in zip(forward, line))
    norm = math.sqrt(sum(value * value for value in bend)) or 1
    knee = tuple(h + along * k + perpendicular * b / norm for h, k, b in zip(hip, line, bend))
    return knee


def project(point, yaw):
    x, y, z = point
    angle = math.radians(yaw)
    px = x * math.cos(angle) - y * math.sin(angle)
    depth = x * math.sin(angle) + y * math.cos(angle)
    return (WIDTH / 2 + SCALE * px, FLOOR - SCALE * (0.98 * z + 0.26 * depth), depth)


def capsule(draw, a, b, r1, r2, color, highlight=None):
    ax, ay = a[:2]
    bx, by = b[:2]
    length = math.hypot(bx - ax, by - ay) or 1
    nx, ny = (by - ay) / length, (ax - bx) / length
    draw.polygon([(ax+nx*r1,ay+ny*r1),(bx+nx*r2,by+ny*r2),(bx-nx*r2,by-ny*r2),(ax-nx*r1,ay-ny*r1)], fill=color)
    draw.ellipse((ax-r1, ay-r1, ax+r1, ay+r1), fill=color)
    draw.ellipse((bx-r2, by-r2, bx+r2, by+r2), fill=color)
    if highlight:
        draw.line([(ax+nx*r1*.42,ay+ny*r1*.42), (bx+nx*r2*.42,by+ny*r2*.42)],fill=highlight,width=max(1,round(r2*.23)))


def limbs(draw, joints, yaw):
    points = {key:project(value,yaw) for key,value in joints.items()}
    parts = []

    def chain(a, b, r1, r2, color, highlight=None, shift=0):
        p, q = points[a], points[b]
        parts.append(((p[2]+q[2])/2+shift, lambda:capsule(draw,p,q,r1,r2,color,highlight)))

    for side in ("L","R"):
        def key(name):
            return side+name

        hip, knee, ankle, toe = (key(name) for name in ("hip","knee","ankle","toe"))
        shoulder, elbow, wrist = (key(name) for name in ("shoulder","elbow","wrist"))
        chain(hip, knee, 11.7, 7.9, "#7576aa", "#9594bf")
        chain(knee, ankle, 7.6, 5.2, "#a8b4cb", "#c0cce3")
        chain(ankle, toe, 5.1, 4.1, "#dde6ff", "#f6faff")
        chain(shoulder, elbow, 9.2, 5.5, "#aebad0", "#d1dcf0")
        chain(elbow, wrist, 5.8, 4.1, "#adb9cf", "#d4dff0")
        wx, wy, depth = points[wrist]
        parts.append((depth-0.012, lambda x=wx,y=wy:draw.ellipse((x-5,y-5,x+5,y+5),fill="#c3cde0")))

    pelvis, chest, head = (points[name] for name in ("pelvis","chest","head"))
    sx, sy = chest[:2]
    hx, hy = pelvis[:2]
    left_dx = abs(points["Lshoulder"][0]-points["Rshoulder"][0])/2
    shoulder_half = 15+left_dx
    hip_half = 12 + abs(points["Lhip"][0]-points["Rhip"][0])/2

    def body():
        draw.rounded_rectangle((hx-hip_half,hy-11,hx+hip_half,hy+13),radius=7,fill="#6e6d9f")
        draw.polygon([(sx-shoulder_half,sy+3),(sx-shoulder_half+5,sy-10),(sx+shoulder_half-5,sy-10),(sx+shoulder_half,sy+3),
                      (hx+hip_half-3,hy+6),(hx-hip_half+2,hy+6)], fill="#9a92ef")
        stripe_x = sx-shoulder_half*.38
        draw.line([(stripe_x,sy-7),(hx-hip_half*.44,hy+2)],fill="#bcb6ff",width=2)
        draw.line([(hx-hip_half+3,hy+5),(hx+hip_half-4,hy+5)],fill="#e1dfff",width=2)

    parts.append(((pelvis[2]+chest[2])/2, body))

    def draw_head():
        x, y = head[:2]
        capsule(draw,(sx,sy),(x,y+12),7,6,"#a6b2c9")
        draw.ellipse((x-11,y-14,x+11,y+14),fill="#bdc9df")
        draw.pieslice((x-11.5,y-14.5,x+11.5,y+12),188,352,fill="#3b4a61")
        facing = math.cos(math.radians(yaw))
        nx = x + 11*facing
        draw.ellipse((nx-3,y+1,nx+3,y+6), fill="#bdc9df")
        eye = x + 6*facing
        draw.ellipse((eye-1.4,y-1.0,eye+1.4,y+1.8),fill="#343f56")

    parts.append((head[2]-.07, draw_head))
    for _, draw_part in sorted(parts,key=lambda part:part[0],reverse=True):
        draw_part()


def line3(draw, values, yaw, color=COURT_LINE, width=2):
    draw.line([project(point,yaw)[:2] for point in values],fill=color,width=width)


@lru_cache
def backdrop(yaw, path_axis):
    result = Image.new("RGB",(WIDTH,HEIGHT))
    draw = ImageDraw.Draw(result)
    for row in range(HEIGHT):
        u = row / HEIGHT
        draw.line((0,row,WIDTH,row),fill=(round(15+5*u),round(21+9*u),round(36+13*u)))
    draw.rounded_rectangle((34,87,926,434),radius=24,fill="#171f33",outline="#303b54",width=2)

    court = Image.new("RGBA",(WIDTH,HEIGHT))
    grid = ImageDraw.Draw(court)
    for along in range(-7,8):
        color = "#3d4b62" if along==0 else ("#273348" if along%2==0 else "#232f43")
        line3(grid,[(along,-8,0),(along,8,0)],yaw,color,2 if along==0 else 1)
        line3(grid,[(-8,along,0),(8,along,0)],yaw,color,2 if along==0 else 1)
    arc = [(0.67*math.cos(i*.10),0.67*math.sin(i*.10),0) for i in range(64)]
    line3(grid,arc,yaw,"#394861",2)
    mask = Image.new("L",(WIDTH,HEIGHT))
    ImageDraw.Draw(mask).rounded_rectangle((36,89,924,432),radius=22,fill=255)
    mask = Image.eval(mask,lambda x:round(x*.94))
    alpha = court.getchannel("A")
    mask = Image.composite(mask,Image.new("L",(WIDTH,HEIGHT)),alpha)
    result.paste(court.convert("RGB"),(0,0),mask)
    draw = ImageDraw.Draw(result)
    if path_axis:
        def ground(along):
            return (along,0.51,0) if path_axis=="x" else (-.33,along,0)
        for start in range(-20,20,2):
            line3(draw,[ground(start/10),ground((start+1)/10)],yaw,"#515a94",2)
        cx,cy,_ = project(ground(2.05),yaw)
        draw.line((cx-8,cy-4,cx,cy,cx-8,cy+4),fill="#7779b5",width=2)
        if path_axis=="y":
            cx,cy,_ = project(ground(-2.05),yaw)
            draw.line((cx+8,cy-4,cx,cy,cx+8,cy+4),fill="#7779b5",width=2)
    return result


def frame(title, view_label, duration, yaw, phases, pose, path_axis, time):
    img = backdrop(yaw,path_axis).copy()
    draw = ImageDraw.Draw(img)
    draw.text((35,25),title,font=font(36),fill=TEXT)
    draw.text((925,42),view_label,font=font(18),fill=MUTED,anchor="rm")

    joints, contacts = pose(time)
    center_x, center_y, _ = project((*joints["pelvis"][:2],0),yaw)
    shape = Image.new("RGBA",img.size)
    shadow = ImageDraw.Draw(shape)
    shadow.ellipse((center_x-35,center_y-8,center_x+35,center_y+10),fill=(4,8,20,154))
    img.paste(shape,(0,0),shape.getchannel("A").filter(ImageFilter.GaussianBlur(4)))
    for side in contacts:
        foot = joints[side+"toe"]
        ankle = joints[side+"ankle"]
        x,y,_ = project((*middle(foot,ankle)[:2],0),yaw)
        draw.ellipse((x-13,y-3,x+13,y+3),fill="#69669d")
        draw.ellipse((x-7,y-2,x+7,y+2),fill="#c3bcff")
    limbs(draw,joints,yaw)

    stage = max(index for index, phase in enumerate(phases) if phase[0] <= time+1e-4)
    label, cue = phases[stage][1:]
    draw.text((36,460),label,font=font(22),fill=BLUE,anchor="lm")
    offset = int(draw.textlength(label,font=font(22))) + 54
    draw.text((offset,460),cue,font=font(22),fill=TEXT,anchor="lm")
    draw.rounded_rectangle((35,501,925,506),radius=3,fill="#353f58")
    width = int(890 * clamp(time/duration))
    if width > 2:
        draw.rounded_rectangle((35,501,35+width,506),radius=3,fill=BLUE)
    return img


def render_demo(dest, clip_id, title, view_label, duration, yaw, phases, pose, *, path_axis="x", poster_at=0.6):
    dest=Path(dest)
    ffmpeg = shutil.which(os.environ.get("PIVOT_DEMO_FFMPEG","ffmpeg"))
    if not ffmpeg:
        raise RuntimeError("Place ffmpeg on PATH or set PIVOT_DEMO_FFMPEG to its executable.")
    dest.mkdir(parents=True,exist_ok=True)
    poster = frame(title, view_label, duration, yaw, phases, pose, path_axis, poster_at)
    contact_dir = os.environ.get("PIVOT_DEMO_CONTACTS")
    if contact_dir:
        previews = Path(contact_dir)
        previews.mkdir(parents=True, exist_ok=True)
        sheet = Image.new("RGB", (WIDTH, HEIGHT), "#13192a")
        sample_times = [phase[0] + min(.30, ((phases[index+1][0] if index+1<len(phases) else duration)-phase[0])*.5)
                        for index, phase in enumerate(phases)]
        for index, time in enumerate(sample_times[:4]):
            sample = frame(title, view_label, duration, yaw, phases, pose, path_axis, time)
            tile = sample.resize((WIDTH//2, HEIGHT//2), Image.Resampling.LANCZOS)
            sheet.paste(tile, ((index%2)*WIDTH//2, (index//2)*HEIGHT//2))
        sheet.save(previews/(clip_id+"-contact.jpg"), quality=93)

    with tempfile.TemporaryDirectory(prefix="pivot-court-video-") as temporary:
        scratch=Path(temporary)
        video=scratch/(clip_id+".mp4")
        cmd=[ffmpeg,"-nostdin","-loglevel","error","-y","-f","rawvideo","-pixel_format","rgb24","-video_size",f"{WIDTH}x{HEIGHT}",
             "-framerate",str(FPS),"-i","-","-an","-c:v","libx264","-preset","fast","-crf","20","-pix_fmt","yuv420p",
             "-movflags","+faststart",str(video)]
        with subprocess.Popen(cmd, stdin=subprocess.PIPE) as encoder:
            for i in range(round(duration*FPS)):
                time=i/FPS
                encoder.stdin.write(frame(title,view_label,duration,yaw,phases,pose,path_axis,time).tobytes())
            encoder.stdin.close()
            if encoder.wait()!=0:
                raise RuntimeError(f"Encoding failed for {clip_id}")
        picture=scratch/(clip_id+".jpg")
        poster.save(picture,quality=90,optimize=True)
        for file in (video,picture):
            target=dest/file.name
            candidate=target.with_suffix(target.suffix+".tmp")
            shutil.copyfile(file,candidate)
            os.replace(candidate,target)
    print(clip_id, f"{duration:.1f}s", (dest/(clip_id+".mp4")).stat().st_size, flush=True)
