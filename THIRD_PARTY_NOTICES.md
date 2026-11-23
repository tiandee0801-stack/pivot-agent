# Third-party references and local dependencies

The root [MIT license](LICENSE) applies to original Pivot code, documentation, and original project assets. Third-party components and media carry their own notices and terms. [Exercise demonstration credits](web/assets/demos/SOURCES.md)

- **Good-GYM** — https://github.com/yo-WASSUP/Good-GYM — MIT, copyright 2024 yo-WASSUP. Training UI hierarchy and interactions are adapted for Pivot; required license is retained in `licenses/Good-GYM-MIT.txt`. No original branding, screenshots or user videos are distributed as application assets.
- **MMPose / RTMPose** — https://github.com/open-mmlab/mmpose — pose-estimation model family referenced by the local inference pipeline. This package does not redistribute upstream checkpoint files or training datasets.
- **RTMLib / ONNX Runtime** — installed in the existing local Python environment and used for inference. Their distributions retain their own licenses. `video_engine` references local YOLOX and RTMPose ONNX weights; model/data terms are separate from software licensing.
- **FFmpeg / ffprobe** — existing local binaries handle video decoding, orientation and silent MP4 normalization; no binary is included in the source delivery.
- **Qwen3-4B / MLX** — existing local language-model environment performs structured intent extraction. Model files are not included in the source delivery.
- **cloudflared** — https://github.com/cloudflare/cloudflared — optional official binary in the local delivery tools directory; provides a temporary HTTPS tunnel. It is not embedded in the application source package.
- **QuickPose, OpenPose, EasyMocap** are retained references, not runtime dependencies of this release.

Private test videos, inferred landmark reports tied to those videos, runtime databases, pairing codes and session credentials are excluded from publishable source archives.

## Experience edition photography
Basketball court photo: Nikita Pishchugin / Unsplash, https://unsplash.com/photos/k75KSGiZWAE . Setting imagery under the [Unsplash License](https://unsplash.com/license).

Strength card photograph: yuhonas/free-exercise-db (Unlicense), https://github.com/yuhonas/free-exercise-db . Reused from existing project assets; license in web/assets/LICENSE-exercise-images.txt. Used as a training reference image, not a personal analysis result.
