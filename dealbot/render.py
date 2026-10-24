"""카드뉴스 슬라이드 구성 → HTML → PNG(1080x1350) 렌더링, 캡션 생성."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config
from .models import Deal, FreeGame

KST = timezone(timedelta(hours=9))
STORE_NAMES = {"steam": "Steam", "gog": "GOG", "epic": "Epic", "directg": "다이렉트게임즈", "stove": "STOVE"}
VERDICT_LABELS = {"best": "지금 사세요 · 역대 최저가", "near": "최저가 근접", "wait": "더 기다려 보세요", "unknown": "가격 추적 중"}


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(KST)


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                      autoescape=select_autoescape(["html", "j2"]))
    env.filters.update({
        "won": lambda v: f"{int(v):,}",
        "store_name": lambda s: STORE_NAMES.get(s, s),
        "verdict_label": lambda v: VERDICT_LABELS.get(v, v),
        "compact": lambda n: f"{n / 10000:.1f}만" if n >= 10000 else f"{n:,}",
        "kdate": lambda s: _parse_iso(s).strftime("%-m/%-d"),
        "kdatetime": lambda s: _parse_iso(s).strftime("%-m/%-d %H:%M"),
        "short_url": lambda u: urlparse(u).netloc.replace("www.", ""),
    })
    return env


def week_range(now: datetime | None = None) -> tuple[str, str]:
    now = (now or datetime.now(KST)).astimezone(KST)
    monday = now - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6)
    week_no = (monday.day - 1) // 7 + 1
    return f"{monday:%Y.%m.%d} – {sunday:%m.%d}", f"{monday.month}월 {week_no}주차"


def build_slides(picks: list[Deal], more: list[Deal], free: list[FreeGame], stores: list[str]) -> list[dict]:
    rng, issue = week_range()
    hero_n = config.HERO_SLIDES
    slides = [{
        "kind": "cover", "issue": issue, "range": rng,
        "title_1": "이번 주", "title_2": "게임 할인",
        "deal_count": len(picks) + len(more), "free_count": sum(not g.upcoming for g in free),
        "max_pct": max((d.discount for d in picks + more), default=0), "stores": stores,
    }]
    slides += [{"kind": "hero", "deal": d, "rank": i + 1} for i, d in enumerate(picks[:hero_n])]
    rest = picks[hero_n:] + more
    for i in range(0, len(rest), config.LIST_SLIDE_ITEMS):
        slides.append({"kind": "list", "title": "이것도", "subtitle": "놓치지 마세요",
                       "deals": rest[i:i + config.LIST_SLIDE_ITEMS]})
    if free:
        slides.append({"kind": "free", "games": sorted(free, key=lambda g: g.upcoming)})
    slides.append({"kind": "cta"})
    return slides[:20]  # 인스타그램 캐러셀 최대 20장


def render_html(slides: list[dict], affiliate: bool = False) -> str:
    return _env().get_template("carousel.html.j2").render(
        slides=slides, handle=config.ACCOUNT_HANDLE, affiliate=affiliate,
        min_review=config.MIN_REVIEW_PCT, min_discount=config.MIN_DISCOUNT,
    )


def render_png(html_path: Path, out_dir: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=config.CHROMIUM_PATH or None)
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle", timeout=60000)
        page.evaluate("document.fonts.ready")
        for i, el in enumerate(page.query_selector_all("section.slide"), 1):
            path = out_dir / f"slide_{i:02d}.png"
            el.screenshot(path=str(path))
            paths.append(path)
        browser.close()
    return paths


HASHTAGS = "#스팀할인 #스팀세일 #게임할인 #에픽무료게임 #GOG #다이렉트게임즈 #스토브 #PC게임 #게임추천 #역대최저가"


def caption(picks: list[Deal], free: list[FreeGame], affiliate: bool = False) -> str:
    rng, issue = week_range()
    lines = [f"🎮 {issue} 게임 할인 정리 ({rng})", ""]
    marks = {"best": "🟢", "near": "🟡", "wait": "🔴", "unknown": "⚪"}
    for i, d in enumerate(picks, 1):
        ko = f" · 한국어 {d.korean}" if d.korean else ""
        lines.append(f"{i}. {marks[d.verdict]} {d.title} ({STORE_NAMES[d.store]}) -{d.discount}% ₩{d.price:,}{ko}")
    now_free = [g for g in free if not g.upcoming]
    if now_free:
        lines += ["", "🎁 에픽 무료: " + ", ".join(g.title for g in now_free)]
    lines += [
        "", "🟢 역대 최저가 · 🟡 최저가 근접 · 🔴 더 기다리기",
        "💬 기다리는 게임을 댓글로 남겨 주세요. 할인하면 알려드릴게요.",
        "📌 저장해 두고 세일 끝나기 전에 확인하세요.",
        "", "가격은 게시 시점 기준이며 바뀔 수 있습니다.",
    ]
    if affiliate:
        lines.insert(0, "[광고] 이 게시물에는 제휴 링크가 포함되어 있습니다.")
    lines += ["", HASHTAGS]
    return "\n".join(lines)
