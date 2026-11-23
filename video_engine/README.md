# Pivot local curl observation

This bounded CLI reuses the local Life Fitness implementation (`sites/life-fitness/engine/vision.py` and `counter.py`). Its elbow-angle approach references [Good-GYM](https://github.com/yo-WASSUP/Good-GYM), and inference uses existing local RTMLib / YOLOX-nano / RTMPose-s ONNX weights. No model is downloaded and no remote inference is called. OpenPose, EasyMocap and the QuickPose SDK are not loaded by this module.

```sh
/path/to/Good-GYM-master/.venv/bin/python video_engine/vision.py --input /absolute/normalized.mp4 --output /absolute/result.json --side left
```

Only a single-person, fixed-camera bicep-curl video is supported. `left` and `right` refer to the person's own body. Input must have rotation applied physically (zero rotation metadata), contain one video stream, be 0.3–45 seconds, at most 60 MiB and at most 4096 pixels on either side / 9 million pixels. Analysis samples at most 360 frames at 8 fps. A subprocess wall timeout must additionally be enforced by the calling server; the CLI itself checks a 180-second processing limit between frames.

The result retains `count`, `quality`, `side`, `duration`, `validRatio`, `summary`, `frames`, `events`, `width`, `height`, `mode` and `limitations`. Each frame has normalized COCO17 points, an aspect-correct calculated elbow angle, cumulative provisional count and visibility flag. When `quality` is `insufficient`, the final `count` is null; clients must never present a frame's provisional count as the rejected total. A usable static recording legitimately has count 0.

Additional fields are `qualityReasons`, `modelVersion`, `ruleVersion`, `cycleDurationSeconds` and `cycleIntervalCount`. The cycle duration field is the median interval between consecutive completed cycles in continuously observed footage. Occlusion, timestamp gaps, overly fast cycles and intervals above 12 seconds break the sequence. Fewer than two consecutive completed cycles, or an insufficient video, returns null. It is an observed rhythm measurement, not a prescription or a form-quality grade.

`result.progress.json` records running / done / error and an actual analysis progress value. CLI exits 0 for completed analysis (including truthful refusal) and nonzero for processing failure. Dependencies are the existing Good-GYM Python environment plus local FFprobe. `PIVOT_VISION_REPOS` can override the reference root; `PIVOT_FFPROBE` can override FFprobe.

Run behavior tests with:

```sh
python3 -m unittest discover -s tests -p test_video_counter.py -v
```

Tests cover complete/partial/occluded/static cycles, ordered timestamps, cadence continuity, quality gates and metadata resource limits. They do not establish model accuracy. Existing private videos were used only for local smoke tests; no private media or pose-frame outputs are included here. No accuracy rate, training effect or clinical effectiveness is claimed.
