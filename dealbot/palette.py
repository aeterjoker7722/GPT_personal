"""키아트에서 포인트 컬러 추출 (테마가 게임마다 다른 색을 입도록)."""
from __future__ import annotations

import colorsys
import io

from PIL import Image

from .http import get

FALLBACK = {"accent": "#e8412c", "deep": "#1a1714", "ink": "#ffffff"}


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb)


def extract(url: str) -> dict:
    if not url:
        return dict(FALLBACK)
    try:
        img = Image.open(io.BytesIO(get(url, retries=1).content)).convert("RGB")
    except Exception:
        return dict(FALLBACK)
    img.thumbnail((96, 96))
    colors = img.quantize(colors=10, method=Image.Quantize.MEDIANCUT).convert("RGB").getcolors(96 * 96) or []
    total = sum(c for c, _ in colors) or 1
    best, best_score = None, -1.0
    for count, rgb in colors:
        h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
        if l < 0.18 or l > 0.85:  # 너무 어둡거나 밝은 색은 포인트로 부적합
            continue
        score = s * 0.7 + (count / total) * 0.6
        if score > best_score:
            best, best_score = (h, l, s), score
    if best is None:
        return dict(FALLBACK)
    h, l, s = best
    accent = colorsys.hls_to_rgb(h, min(max(l, 0.45), 0.6), max(s, 0.55))
    deep = colorsys.hls_to_rgb(h, 0.09, min(s, 0.45))
    lum = 0.2126 * accent[0] + 0.7152 * accent[1] + 0.0722 * accent[2]
    return {
        "accent": _hex([c * 255 for c in accent]),
        "deep": _hex([c * 255 for c in deep]),
        "ink": "#111111" if lum > 0.55 else "#ffffff",  # 포인트 색 위 글자색
    }
