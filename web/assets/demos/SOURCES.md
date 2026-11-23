# 动作示范素材来源

每个动作包含同名 MP4 视频与从视频提取的 JPG 封面。

## DVIDS 实拍

各素材由 DVIDS 标注为美国政府公共领域影像，使用条件见 [DVIDS Copyright Information](https://www.dvidshub.net/about/copyright)。已截取动作示范段落、去掉音轨并转换为 H.264。需要时裁剪黑边或选取一个拍摄角度。

> The appearance of U.S. Department of War (DoW) visual information does not imply or constitute DoW endorsement.

| 本地素材编号 | 动作与来源 | 署名 | 原片截取 |
|---|---|---|---|
| `squat` | [Body Weight Squat](https://www.dvidshub.net/video/517502/body-weight-squat) | U.S. Marine Corps / Cpl. Amber Jennings，DVIDS 署名 Joshua Pena | 00:18–00:29 |
| `barbell_back_squat` | [Barbell Back Squat](https://www.dvidshub.net/video/517475/barbell-back-squat) | U.S. Marine Corps / Cpl. Amber Jennings，DVIDS 署名 Joshua Pena | 00:24–00:36 |
| `pushup` | [Push Up Demonstration](https://www.dvidshub.net/video/283728/push-up-demonstration) | U.S. Navy / Andrea Perez | 00:46.7–00:58.7 |
| `bicep_curl` | [Dumbbell Curl](https://www.dvidshub.net/video/636923/dumbbell-curl) | U.S. Marine Corps / Matthew Holfinger | 00:00–00:10 |
| `side_plank` | [Side Plank](https://www.dvidshub.net/video/640254/side-plank) | U.S. Marine Corps / Matthew Holfinger | 00:00–00:09.5 |
| `plank` | [Forearm Plank](https://www.dvidshub.net/video/825280/forearm-plank) | U.S. Air Force / Randall Moose | 01:43–01:52 |
| `lateral_lunge` | [Lateral Lunge](https://www.dvidshub.net/video/677362/lateral-lunge) | U.S. Marine Corps / Matthew Holfinger | 00:04–00:16 |
| `reverse_lunge` | [Stationary Reverse Lunge](https://www.dvidshub.net/video/551833/stationary-reverse-lunge) | U.S. Marine Corps / Matthew Holfinger | 00:11–00:24.5 |
| `dumbbell_rdl` | [Dumbbell Romanian Deadlift](https://www.dvidshub.net/video/548459/dumbbell-romanian-deadlift) | U.S. Marine Corps / Matthew Holfinger | 00:19–00:30 |
| `dumbbell_row` | [Dumbbell Bent Over Rows](https://www.dvidshub.net/video/636921/dumbbell-bent-over-rows) | U.S. Marine Corps / Matthew Holfinger | 00:00.3–00:12.3，选取斜侧视角 |

## CrossFitOS 3D 动画

CrossFitOS 在每个来源页以 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 发布视频和图片。人体模型署名归 [Z-Anatomy](https://www.z-anatomy.com/)（CC BY-SA 4.0），基于 [BodyParts3D](https://lifesciencedb.jp/bp3d/)（CC BY 4.0）。Pivot 保留原片单次动作的完整片段，转换为无声 H.264，并从原片提取封面。下列本地 MP4 和 JPG 继续使用 CC BY-SA 4.0。

| 本地素材编号 | 动作与来源 | 署名 |
|---|---|---|
| `band_row` | [Band Row](https://crossfitos.com/exercises/band-row) | CrossFitOS / Z-Anatomy / BodyParts3D |
| `band_rdl` | [Banded Romanian Deadlift](https://crossfitos.com/exercises/banded-romanian-deadlift) | CrossFitOS / Z-Anatomy / BodyParts3D |
| `dead_bug` | [Dead Bug](https://crossfitos.com/exercises/dead-bug) | CrossFitOS / Z-Anatomy / BodyParts3D |

## Pivot 换场自制球场动作动画

动画根据现有动作库说明制作。人物、球场和动作轨迹为自制，使用同名 MP4 和封面图，采用项目 [MIT 许可](../../../LICENSE)。内容为动作示意，待体能教练审核。

可用 `ops/court_demo_moving.py` 和 `ops/court_demo_stationary.py` 重新生成，两者共用 `ops/court_demo_renderer.py`，需要 Pillow、FFmpeg 和可显示中文的字体。

| 素材编号 | 动作 | 演示阶段 |
|---|---|---|
| `short_acceleration` | 短距离启动 | 站稳、起步、逐步提速、留出缓冲空间 |
| `linear_braking` | 直线减速停稳 | 向前移动、数步减速、站稳 |
| `lateral_shuffle_stop` | 侧移后制动 | 胸口朝前、侧向滑步、缩小步幅并停稳、另一侧 |
| `march_in_place` | 原地踏步热身 | 交替抬脚摆臂、由慢到快、回到稳定站姿 |
| `snap_down` | 快速下沉定住 | 从站姿快速屈髋屈膝、双脚踩稳并保持 |
