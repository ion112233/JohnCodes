"""Turn a list of scenes into a silent H.264 mp4 by piping raw frames to ffmpeg."""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import Config
from .scenes import Scene


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("ffmpeg not found on PATH. Install it (e.g. `brew install ffmpeg`).")
    return exe


def render_video(cfg: Config, scenes: list[Scene], out_path: Path) -> float:
    fps = cfg.fps
    starts: list[float] = []
    acc = 0.0
    for sc in scenes:
        starts.append(acc)
        acc += sc.duration
    total = acc
    n_frames = int(round(total * fps))

    cmd = [
        _ffmpeg(), "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{cfg.width}x{cfg.height}", "-r", str(fps),
        "-i", "-",
        "-an",
        "-c:v", "libx264", "-preset", cfg.x264_preset, "-crf", str(cfg.crf),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert proc.stdin is not None

    from PIL import Image as _Img

    fade = cfg.fade
    xfade = max(0.0, cfg.xfade)
    black = _Img.new("RGB", (cfg.width, cfg.height), (0, 0, 0))
    t0 = time.time()
    si = 0
    prev_final: "_Img.Image | None" = None   # frozen last frame of scene si-1
    try:
        for f in range(n_frames):
            gt = f / fps
            while si + 1 < len(scenes) and gt >= starts[si + 1]:
                # crossing into the next scene: freeze the outgoing scene's
                # final frame so we can dissolve out of it
                pf = scenes[si].render(max(0.0, scenes[si].duration - 1e-3))
                prev_final = pf.convert("RGB") if pf.mode != "RGB" else pf
                si += 1
            local_t = gt - starts[si]
            frame = scenes[si].render(local_t)
            if frame.mode != "RGB":
                frame = frame.convert("RGB")

            # crossfade dissolve over the first `xfade` seconds of every scene
            if si > 0 and prev_final is not None and xfade > 0 and local_t < xfade:
                frame = _Img.blend(prev_final, frame, local_t / xfade)

            # global fade from / to black at the very start and end
            a = 1.0
            if fade > 0 and gt < fade:
                a = gt / fade
            elif fade > 0 and gt > total - fade:
                a = max(0.0, (total - gt) / fade)
            if a < 0.999:
                frame = _Img.blend(black, frame, a)
            proc.stdin.write(frame.tobytes())
            if f % fps == 0 or f == n_frames - 1:
                pct = 100 * (f + 1) / n_frames
                sys.stdout.write(f"\r  frames {f + 1}/{n_frames} ({pct:4.0f}%)  "
                                 f"{time.time() - t0:5.1f}s")
                sys.stdout.flush()
    finally:
        proc.stdin.close()
        proc.wait()
    sys.stdout.write("\n")
    if proc.returncode != 0:
        raise SystemExit(f"ffmpeg exited with code {proc.returncode}")
    return total


def mux(cfg: Config, video: Path, audio: Path, out_path: Path) -> None:
    cmd = [
        _ffmpeg(), "-y",
        "-i", str(video), "-i", str(audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
