"""정지 이미지, 모션(MP4/GIF), 릴스 렌더링.

모든 템플릿은 CSS 애니메이션으로 움직이고, 페이지의 window.__seek(t) 가
모든 애니메이션과 숫자 카운터를 t초 시점으로 맞춘다. 프레임마다 seek → 스크린샷 →
ffmpeg 로 인코딩하므로 실시간 녹화와 달리 프레임 드랍 없이 결정적으로 렌더링된다.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

from . import config
from .http import get

FPS = 30
STATIC_T = 6.0   # 정지 이미지는 모든 등장 애니메이션이 끝난 시점에서 찍는다


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg 가 필요합니다 (brew install ffmpeg / apt install ffmpeg)")
    return exe


@contextmanager
def browser_page(html_path: Path, width: int, height: int):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=config.CHROMIUM_PATH or None)
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle", timeout=90000)
        page.evaluate("document.fonts.ready")
        page.wait_for_function("window.__seek !== undefined")
        try:
            yield page
        finally:
            browser.close()


def seek(page, t: float) -> None:
    page.evaluate(f"window.__seek({t})")


def stills(page, out_dir: Path, selector: str = "section.slide", prefix: str = "slide") -> list[Path]:
    seek(page, STATIC_T)
    paths = []
    for i, el in enumerate(page.query_selector_all(selector), 1):
        path = out_dir / f"{prefix}_{i:02d}.png"
        el.screenshot(path=str(path))
        paths.append(path)
    return paths


def _encoder(out: Path, fps: int, extra_inputs: list[str] | None = None, vf: str | None = None):
    cmd = [_ffmpeg(), "-loglevel", "error", "-y"]
    cmd += extra_inputs or []
    cmd += ["-f", "image2pipe", "-framerate", str(fps), "-i", "-"]
    if vf:
        cmd += ["-filter_complex", vf]
    else:
        cmd += ["-pix_fmt", "yuv420p"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-movflags", "+faststart", str(out)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def clip(page, element, out: Path, duration: float, fps: int = FPS, transparent: bool = False,
         background: Path | None = None) -> Path:
    """element 를 duration 초 동안 프레임 단위로 캡처해 MP4 로 저장.

    background 가 있으면(트레일러) 그 위에 투명 캡처를 합성한다.
    """
    box = element.bounding_box()
    w, h = int(box["width"]), int(box["height"])
    if background is not None:
        vf = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
              f"setpts=PTS-STARTPTS,fps={fps}[bg];[bg][1:v]overlay=0:0:shortest=1,format=yuv420p")
        proc = _encoder(out, fps, ["-i", str(background)], vf)
    else:
        proc = _encoder(out, fps)
    for f in range(int(duration * fps)):
        seek(page, f / fps)
        proc.stdin.write(element.screenshot(type="png", omit_background=transparent or background is not None))
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg 인코딩 실패: {out}")
    return out


def to_gif(mp4: Path, width: int = 360, fps: int = 12) -> Path:
    """미리보기/문서용 GIF (인스타그램 업로드는 MP4 사용)."""
    gif = mp4.with_suffix(".gif")
    vf = (f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];"
          f"[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4")
    subprocess.run([_ffmpeg(), "-loglevel", "error", "-y", "-i", str(mp4), "-vf", vf, str(gif)], check=True)
    return gif


def concat(clips: list[Path], out: Path) -> Path:
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    subprocess.run([_ffmpeg(), "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    lst.unlink()
    return out


def _trailer_length(manifest_url: str) -> float:
    try:
        mpd = get(manifest_url, retries=1).text
    except Exception:
        return 0
    m = re.search(r'mediaPresentationDuration="PT(?:(\d+)M)?([\d.]+)S"', mpd)
    return int(m.group(1) or 0) * 60 + float(m.group(2)) if m else 0


def fetch_trailer(manifest_url: str, out: Path, start_sec: float | None = None, seconds: float = 9) -> Path | None:
    """스팀 트레일러 DASH(h264) 조각을 받아 소리 없는 MP4 로 저장.

    manifest: .../dash_h264.mpd → 조각: .../dash_h264/init-stream1.m4s, chunk-stream1-00001.m4s (3초 단위, 720p)
    시작 지점을 안 주면 앞부분 로고/암전을 건너뛰도록 전체 길이의 30% 지점부터 자른다.
    """
    if not manifest_url:
        return None
    if manifest_url.split("?")[0].endswith(".mp4"):  # PS 스토어 미리보기 영상은 MP4 한 파일
        subprocess.run([_ffmpeg(), "-loglevel", "error", "-y", "-ss", str(start_sec or 4), "-t", str(seconds),
                        "-i", manifest_url, "-an", "-vf", "setpts=PTS-STARTPTS", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "20", str(out)], check=True)
        return out
    if start_sec is None:
        length = _trailer_length(manifest_url)
        start_sec = max(6.0, min(length * 0.3, length - seconds - 3)) if length else 12.0
    base = manifest_url.split("?")[0].rsplit("/", 1)[0] + "/dash_h264"
    first = int(start_sec // 3) + 1
    raw = out.with_suffix(".raw.mp4")
    try:
        data = get(f"{base}/init-stream1.m4s").content
        for n in range(first, first + int(seconds // 3) + 1):
            data += get(f"{base}/chunk-stream1-{n:05d}.m4s").content
    except Exception as e:
        print(f"[trailer] 다운로드 실패: {e}")
        return None
    raw.write_bytes(data)
    subprocess.run([_ffmpeg(), "-loglevel", "error", "-y", "-i", str(raw), "-t", str(seconds), "-an",
                    "-vf", "setpts=PTS-STARTPTS", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    str(out)], check=True)
    raw.unlink()
    return out
