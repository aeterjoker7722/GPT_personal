"""슬라이드 구성 → 테마별 HTML → 정지 이미지 / 모션 MP4·GIF / 릴스, 캡션 생성."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config, motion, palette
from .models import Deal, FreeGame

KST = timezone(timedelta(hours=9))
STORE_NAMES = {"steam": "Steam", "gog": "GOG", "epic": "Epic", "directg": "다이렉트게임즈", "stove": "STOVE",
               "playstation": "PlayStation", "nintendo": "Nintendo", "xbox": "Xbox"}
STORE_SHORT = {"directg": "다이렉트G", "playstation": "PS", "nintendo": "Switch"}
TEMPLATES = Path(__file__).parent / "templates"

# 테마 이름 → 설명. 템플릿은 templates/<theme>.html.j2
THEMES = {
    "editorial": "에디토리얼 매거진: 종이 질감, 명조 헤드라인, 표처럼 정리된 가격",
    "receipt": "영수증: 감열지 영수증과 '역대최저' 고무도장, 할인액을 계산서처럼",
    "ticker": "증권 시세: 게임을 종목처럼, 가격 차트와 매수 의견(판정)",
    "poster": "포스터: 키아트 풀블리드, 게임마다 키아트에서 뽑은 포인트 컬러",
}


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(KST)


def _dday(iso: str) -> str:
    """종료 시각까지 남은 시간: 24시간 이상이면 D-n, 미만이면 nH."""
    left = (_parse_iso(iso) - datetime.now(KST)).total_seconds()
    hours = max(0, int(left // 3600))
    return f"D-{hours // 24}" if hours >= 24 else f"{hours}H"


def chart(history: list, w: float, h: float, pad: float = 6) -> dict | None:
    """가격 이력 → SVG path. 점이 2개 미만이면 None."""
    if not history or len(history) < 2:
        return None
    prices = [p for _, p in history]
    lo, hi = min(prices), max(prices)
    span = (hi - lo) or 1
    n = len(prices) - 1

    def xy(i, p):
        return round(pad + (w - 2 * pad) * i / n, 1), round(pad + (h - 2 * pad) * (1 - (p - lo) / span), 1)

    pts = [xy(i, p) for i, p in enumerate(prices)]
    # 가격은 계단형(가격이 바뀌는 날 수직 이동)으로 그려야 실제 시세처럼 보인다
    d = f"M{pts[0][0]},{pts[0][1]}"
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        d += f" H{x1}" if y0 == y1 else f" H{x1} V{y1}"
    low_i = len(prices) - 1 - prices[::-1].index(lo)
    return {
        "path": d,
        "area": d + f" V{h} H{pts[0][0]} Z",
        "low": pts[low_i], "last": pts[-1], "min": lo, "max": hi,
        "start": history[0][0], "end": history[-1][0], "w": w, "h": h,
    }


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    env.filters.update({
        "won": lambda v: f"{int(v):,}",
        "store_name": lambda s: STORE_NAMES.get(s, s),
        "compact": lambda n: f"{n / 10000:.1f}만" if n >= 10000 else f"{n:,}",
        "kdate": lambda s: _parse_iso(s).strftime("%-m/%-d"),
        "kdatetime": lambda s: _parse_iso(s).strftime("%-m/%-d %H:%M"),
        "short_url": lambda u: urlparse(u).netloc.replace("www.", ""),
        "pad2": lambda n: f"{int(n):02d}",
        "ord": ord,
        "dday": _dday,
        "store_short": lambda s: STORE_SHORT.get(s, STORE_NAMES.get(s, s)),
        "short_won": lambda v: (f"{v / 10000:.1f}".rstrip("0").rstrip(".") + "만") if v >= 10000 else f"{int(v) // 1000}천" if v >= 1000 else f"{int(v)}",
    })
    env.globals["chart"] = chart
    return env


def week_info(now: datetime | None = None) -> dict:
    now = (now or datetime.now(KST)).astimezone(KST)
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    return {
        "range": f"{monday:%Y.%m.%d} — {sunday:%m.%d}",
        "issue": f"{monday.month}월 {(monday.day - 1) // 7 + 1}주차",
        "no": monday.isocalendar().week,
        "year": monday.year,
    }


def decorate(deals: list[Deal]) -> None:
    """테마에 필요한 부가 정보: 키아트 포인트 컬러."""
    for d in deals:
        if not d.palette:
            d.palette = palette.extract(d.art_tall or d.image)


def build_slides(picks: list[Deal], more: list[Deal], free: list[FreeGame], stores: list[str]) -> list[dict]:
    hero_n = config.HERO_SLIDES
    every = picks + more
    slides = [{
        "kind": "cover", "deals": picks[:5], "stores": stores,
        "deal_count": len(every), "free_count": sum(not g.upcoming for g in free),
        "max_pct": max((d.discount for d in every), default=0),
        "avg_pct": round(sum(d.discount for d in every) / len(every)) if every else 0,
        "savings": sum(d.regular - d.price for d in picks[:5]),
    }]
    slides += [{"kind": "hero", "deal": d, "rank": i + 1} for i, d in enumerate(picks[:hero_n])]
    rest = picks[hero_n:] + more
    for i in range(0, len(rest), config.LIST_SLIDE_ITEMS):
        slides.append({"kind": "list", "deals": rest[i:i + config.LIST_SLIDE_ITEMS], "offset": hero_n + i})
    if free:
        slides.append({"kind": "free", "games": sorted(free, key=lambda g: g.upcoming)[:2]})
    slides.append({"kind": "cta"})
    return slides[:20]  # 인스타그램 캐러셀 최대 20장


def render_html(slides: list[dict], theme: str, *, sample: bool = False, affiliate: bool = False) -> str:
    return _env().get_template(f"{theme}.html.j2").render(
        slides=slides, total=len(slides), week=week_info(), brand=config.BRAND,
        handle=config.ACCOUNT_HANDLE, affiliate=affiliate, sample=sample,
        min_review=config.MIN_REVIEW_PCT, min_discount=config.MIN_DISCOUNT,
    )


MOTION_KINDS = {"cover": {"cover", "story", "story_free"},
                "key": {"cover", "hero", "story", "story_free", "free"}}


def render_theme(slides: list[dict], theme: str, out_dir: Path, *, name: str | None = None,
                 motion_slides: str = "", sample: bool = False, affiliate: bool = False) -> dict:
    """테마 하나를 렌더링. motion_slides: "" (정지만) / "cover" / "key" (표지+메인카드) / "all"."""
    out = out_dir / (name or theme)
    out.mkdir(parents=True, exist_ok=True)
    html_path = out / "carousel.html"
    html_path.write_text(render_html(slides, theme, sample=sample, affiliate=affiliate), encoding="utf-8")
    result = {"html": html_path, "png": [], "mp4": []}
    with motion.browser_page(html_path, 1080, 1350) as page:
        result["png"] = motion.stills(page, out)
        if motion_slides:
            for i, (el, s) in enumerate(zip(page.query_selector_all("section.slide"), slides), 1):
                if motion_slides in MOTION_KINDS and s["kind"] not in MOTION_KINDS[motion_slides]:
                    continue
                mp4 = motion.clip(page, el, out / f"slide_{i:02d}.mp4", duration=float(s.get("duration", 4.0)))
                result["mp4"].append(mp4)
    return result


REEL_TITLES = {"weekly": ("이번 주", "할인"), "ending": ("곧 끝나는", "할인"), "console": ("주말 콘솔", "세일")}


def render_reel(picks: list[Deal], out_dir: Path, *, count: int = 3, sample: bool = False,
                source: str = "weekly") -> Path:
    """9:16 릴스: 인트로 → 게임별 트레일러 위 가격 오버레이 → 아웃트로."""
    out = out_dir / ("reel" if source == "weekly" else f"reel-{source}")
    out.mkdir(parents=True, exist_ok=True)
    games = picks[:count]
    trailers = {}
    for i, d in enumerate(games):
        clip_path = motion.fetch_trailer(d.trailer, out / f"trailer_{i + 1}.mp4") if d.trailer else None
        trailers[d.key] = clip_path
    scenes = [{"kind": "intro", "duration": 2.4, "deals": games, "lines": REEL_TITLES.get(source, REEL_TITLES["weekly"])}]
    scenes += [{"kind": "game", "deal": d, "rank": i + 1, "duration": 3.8, "video": bool(trailers[d.key])}
               for i, d in enumerate(games)]
    scenes += [{"kind": "outro", "duration": 2.6}]
    html_path = out / "reel.html"
    html_path.write_text(_env().get_template("reel.html.j2").render(
        scenes=scenes, total=len(scenes), week=week_info(), brand=config.BRAND,
        handle=config.ACCOUNT_HANDLE, sample=sample), encoding="utf-8")
    parts = []
    with motion.browser_page(html_path, 1080, 1920) as page:
        for i, (el, sc) in enumerate(zip(page.query_selector_all("section.scene"), scenes), 1):
            bg = trailers.get(sc["deal"].key) if sc["kind"] == "game" else None
            parts.append(motion.clip(page, el, out / f"part_{i:02d}.mp4", sc["duration"], background=bg))
    reel = motion.concat(parts, out / "reel.mp4")
    for p in parts:
        p.unlink()
    for t in trailers.values():
        if t:
            t.unlink()
    return reel


HASHTAGS = "#스팀할인 #스팀세일 #게임할인 #에픽무료게임 #GOG #다이렉트게임즈 #스토브 #PC게임 #게임추천 #역대최저가"


def caption(picks: list[Deal], free: list[FreeGame], affiliate: bool = False) -> str:
    w = week_info()
    lines = [f"{w['issue']} 게임 할인 정리 ({w['range']})", ""]
    marks = {"best": "[역대최저]", "near": "[최저근접]", "wait": "[대기]", "unknown": ""}
    for i, d in enumerate(picks, 1):
        ko = f" · 한국어 {d.korean}" if d.korean else ""
        lines.append(f"{i:02d} {d.title} ({STORE_NAMES[d.store]}) -{d.discount}% ₩{d.price:,}{ko} {marks[d.verdict]}".rstrip())
    now_free = [g for g in free if not g.upcoming]
    if now_free:
        lines += ["", "에픽 무료: " + ", ".join(g.title for g in now_free)]
    lines += [
        "", "판정은 역대 최저가 기록 기준입니다.",
        "기다리는 게임을 댓글로 남겨 주세요. 할인하면 알려드릴게요.",
        "저장해 두고 세일 끝나기 전에 확인하세요.",
        "", "가격은 게시 시점 기준이며 바뀔 수 있습니다.",
    ]
    if affiliate:
        lines.insert(0, "[광고] 이 게시물에는 제휴 링크가 포함되어 있습니다.")
    lines += ["", HASHTAGS]
    return "\n".join(lines)
