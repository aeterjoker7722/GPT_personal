"""게시물 포맷(요일별 시리즈)과 주간 편성표.

원칙(보수적 운영)
- 스토어에서 바로 확인되는 사실만 쓴다. '역대 최저가' 같은 판정은 기본으로 보여 주지 않는다(config.SHOW_VERDICT).
- 이번 주 할인을 요일별 주제로 나눠 소개하고, 같은 주에 같은 게임을 반복하지 않는다(state.used_keys).
- 조건이 안 맞는 포맷은 억지로 만들지 않는다(콘솔 세일 → 대체 포맷, 에픽이 전부 한국 미제공 → 스토리만).

디자인은 poster 하나로 통일하되, 포맷마다 레이아웃(PostType.layout)을 달리해 요일별로 다른 맛을 낸다.
편성표와 운영 방법은 docs/weekly_plan.md 참고.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from . import config, curate, state
from .models import Deal, FreeGame

KST = timezone(timedelta(hours=9))
STORE_NAMES = {"steam": "Steam", "gog": "GOG", "epic": "Epic", "directg": "다이렉트게임즈", "stove": "STOVE",
               "playstation": "PlayStation", "nintendo": "Nintendo", "xbox": "Xbox"}


@dataclass
class PostType:
    key: str
    kicker: str          # 표지 상단 영문 (압축 서체)
    headline: str        # 표지 한글 헤드라인 ({n} = 개수), 줄바꿈은 \n
    hook: str            # 캡션 첫 줄 (피드에서 잘리기 전에 보이는 부분)
    hashtags: str        # 포맷별 3~5개
    heroes: int = 3      # 메인 카드 장수 (poster/cinema 레이아웃)
    layout: str = "poster"   # poster / cinema / grid / duo / report / recap


POSTS = {
    "report": PostType("report", "WEEKLY REPORT", "이번 주\n스팀 리포트",
                       "이번 주 스팀: 진행 중인 세일·페스티벌과 할인 TOP {n}를 정리했습니다.",
                       "#스팀할인 #스팀세일 #게임할인 #PC게임추천", heroes=5, layout="report"),
    "aaa": PostType("aaa", "AAA DEALS", "정가 5만 원 넘는\n대작 할인 {n}",
                    "원래 5만 원 넘던 대작들이 할인 중입니다.",
                    "#스팀할인 #대작게임 #AAA게임 #게임할인", heroes=4, layout="cinema"),
    "indie": PostType("indie", "INDIE PICKS", "금주의\n인디 {n}",
                      "평가 좋은 인디 게임 {n}개, 할인 중일 때 담아 두세요.",
                      "#인디게임 #스팀할인 #인디게임추천 #게임추천", heroes=0, layout="grid"),
    "under5k": PostType("under5k", "UNDER ₩5,000", "5천 원 이하\n할인 {n}",
                        "커피 한 잔 값으로 사는 게임 {n}개.",
                        "#스팀할인 #가성비게임 #게임추천 #스팀세일", heroes=0, layout="duo"),
    "korean": PostType("korean", "KOREAN SUPPORTED", "한국어로 즐기는\n할인 {n}",
                       "한국어 자막·음성 지원되는 할인 게임만 모았습니다.",
                       "#한국어지원 #스팀할인 #게임추천 #스팀세일", heroes=0, layout="duo"),
    "ending": PostType("ending", "ENDING SOON", "곧 끝나는\n할인 {n}",
                       "이번 주말에 끝나는 할인입니다. 장바구니에 담아 둔 게임 확인하세요.",
                       "#스팀할인 #마감임박 #게임할인 #주말게임"),
    "console": PostType("console", "CONSOLE SALE", "주말 콘솔\n세일 {n}",
                        "주말에 할 콘솔 게임, 할인 중인 인기작 {n}개입니다. 같은 게임의 PC 가격도 같이 적었습니다.",
                        "#PS5할인 #플스할인 #PS스토어 #콘솔게임"),
    "free": PostType("free", "FREE THIS WEEK", "이번 주\n무료 게임",
                     "이번 주 에픽 무료 게임입니다. 받아 두면 계속 내 게임입니다.",
                     "#에픽무료게임 #무료게임 #에픽게임즈 #PC게임", heroes=0),
    "recap": PostType("recap", "WEEKLY RECAP", "이번 주\n결산",
                      "이 계정의 주간 1위만 매주 샀다면, 지금까지 얼마를 아꼈을까요?",
                      "#스팀할인 #게임할인 #스팀세일", heroes=0, layout="recap"),
    "story": PostType("story", "TODAY'S DEAL", "오늘의 할인", "", "", heroes=1),
    "guide": PostType("guide", "HOW TO READ", "이 계정\n보는 법",
                      "카드 읽는 법과 요일별 편성표를 정리했습니다.",
                      "#스팀할인 #게임할인 #게임추천", heroes=0),
    # 편성표에서는 뺐지만 명령으로는 만들 수 있다 (판정 데이터가 확실할 때만 쓸 것)
    "lowest": PostType("lowest", "ALL-TIME LOW", "역대 최저가\n갱신 {n}",
                       "지금이 역대 최저가입니다.", "#역대최저가 #스팀할인 #게임할인"),
    "weekly": PostType("weekly", "WEEKLY TOP", "이번 주\n할인 TOP {n}",
                       "이번 주 놓치면 아까운 할인 {n}개, 평가 좋은 것만 골랐습니다.",
                       "#스팀할인 #게임할인 #스팀세일 #PC게임추천", heroes=5),
}

# 목요일은 주차마다 교대하고, 토요일 콘솔 세일이 조건 미달이면 목요일에 안 쓴 쪽으로 대체한다
THURSDAY_ROTATION = ["under5k", "korean"]

# 요일(월=0)별 편성. (시각, 포맷). 시각은 업로드 권장 시각(KST)
STORY_AT = "09:00"  # 매일 스토리 (목요일 23:00 에픽 예고 스토리는 별도)

WEEKLY_PLAN = {
    0: [("12:00", "report"), ("20:00", "reel")],
    1: [("19:00", "aaa")],
    2: [("19:00", "indie")],
    3: [("19:00", "thursday"), ("23:00", "story:upcoming-free")],
    4: [("00:05", "free"), ("18:00", "ending"), ("20:00", "reel:ending")],
    5: [("12:00", "console")],
    6: [("20:00", "recap")],
}

# 콘솔 세일을 올리는 조건: PS 인기 150위 안에서 40% 이상 할인 게임이 5개 이상
CONSOLE_MIN_GAMES, CONSOLE_MIN_DISCOUNT, CONSOLE_MAX_RANK = 5, 40, 150


def thursday_kind(day: datetime) -> str:
    return THURSDAY_ROTATION[day.isocalendar().week % 2]


def jobs_for(day: datetime | None = None) -> list[tuple[str, str]]:
    day = (day or datetime.now(KST)).astimezone(KST)
    return [(at, thursday_kind(day) if kind == "thursday" else kind) for at, kind in WEEKLY_PLAN[day.weekday()]]


def console_ready(deals: list[Deal]) -> bool:
    hot = [d for d in deals if d.store in curate.CONSOLE_STORES and d.discount >= CONSOLE_MIN_DISCOUNT
           and (d.popularity or 999) <= CONSOLE_MAX_RANK]
    return len(hot) >= CONSOLE_MIN_GAMES


def console_fallback(day: datetime | None = None) -> str:
    day = (day or datetime.now(KST)).astimezone(KST)
    used = thursday_kind(day)
    return next(k for k in THURSDAY_ROTATION if k != used)


def ending_soon(deals: list[Deal], hours: int = 80) -> list[Deal]:
    now = datetime.now(timezone.utc)
    soon = []
    for d in deals:
        if d.ends_at:
            end = datetime.fromisoformat(d.ends_at.replace("Z", "+00:00"))
            if now < end <= now + timedelta(hours=hours):
                soon.append(d)
    return soon


def select(kind: str, deals: list[Deal], n: int = 9, exclude: set[str] | None = None) -> list[Deal]:
    """포맷별 선정. exclude(이번 주 이미 소개한 게임)는 빼고 고른다. 결과가 적으면 그만큼만 쓴다."""
    pool = [d for d in deals if not state.is_used(d, exclude or set())]
    if kind in ("report", "weekly"):
        return curate.pick(deals, n)  # 주간 대표 게시물은 중복 제외 없이 최고만
    if kind == "lowest":
        return curate.pick([d for d in pool if d.verdict == "best"], n)
    if kind == "ending":
        return curate.pick(ending_soon(deals), n)  # 마감 알림은 앞서 소개한 게임이어도 다시 알린다
    if kind == "aaa":
        return curate.pick([d for d in pool if d.regular >= 50000], min(n, 7))
    if kind == "indie":
        return curate.pick([d for d in pool if d.indie and (d.review_pct or 0) >= 85], 8)
    if kind in ("under5k", "korean"):
        return curate.series(pool, kind, 8)
    if kind == "console":
        return curate.pick_console(deals, n)
    if kind == "story":  # 9:16 이라 세로 키아트가 있는 게임만 (가로 이미지를 늘리면 깨져 보임)
        tall = [d for d in deals if d.art_tall]
        return curate.pick([d for d in tall if not state.is_used(d, exclude or set())], 1) or curate.pick(tall, 1)
    if kind in ("guide", "recap"):
        return curate.pick(deals, 5)  # 표지 그림용
    return []


LIST_ROWS = 5


def trim(kind: str, picks: list[Deal]) -> list[Deal]:
    """마지막 장에 1~2개만 남으면 그만큼 덜어 낸다 (거의 빈 장 방지)."""
    layout = POSTS[kind].layout
    if layout == "grid":
        return picks[:len(picks) // 4 * 4] if len(picks) >= 4 else picks
    if layout == "duo":
        return picks[:len(picks) // 2 * 2] if len(picks) >= 2 else picks
    if layout == "cinema":
        return picks
    heroes = POSTS[kind].heroes
    rest = len(picks) - heroes
    if rest > LIST_ROWS and rest % LIST_ROWS in (1, 2):
        return picks[:heroes + rest // LIST_ROWS * LIST_ROWS]
    return picks


def _won_man(v: int) -> str:
    return "₩" + f"{v / 10000:.1f}".rstrip("0").rstrip(".") + "만" if v >= 10000 else f"₩{v:,}"


def build(kind: str, picks: list[Deal], free: list[FreeGame], stores: list[str], ctx: dict | None = None) -> list[dict]:
    """포맷 → 슬라이드 목록 (poster 템플릿의 kind 별 블록과 짝). ctx: 일정·기획전·장부 등 부가 정보."""
    ctx = ctx or {}
    pt = POSTS[kind]
    post = {"key": kind, "kicker": pt.kicker, "headline": pt.headline.format(n=len(picks)), "layout": pt.layout}
    if kind == "story":
        return [{"kind": "story", "deal": d, "post": post} for d in picks[:1]]
    if kind == "guide":
        return [{"kind": "cover", "post": post, "deals": picks[:5], "stat": "1분", "stat_label": "읽는 데 걸리는 시간"},
                {"kind": "legend", "post": post, "deals": picks[:3]},
                {"kind": "cta", "post": post}]
    if kind == "free":
        games = sorted(free, key=lambda g: (g.upcoming, g.kr_blocked))
        open_now = [g for g in games if not g.upcoming and not g.kr_blocked]
        slides = [{"kind": "cover", "post": post, "deals": [], "free_games": games,
                   "stat": f"{len(open_now)}개" if open_now else "없음", "stat_label": "한국에서 받을 수 있는 무료 게임"}]
        slides += [{"kind": "free", "game": g, "post": post} for g in games[:3]]
        slides.append({"kind": "cta", "post": post})
        return slides
    if kind == "recap":
        ledger = ctx.get("ledger") or {}
        return [{"kind": "cover", "post": post, "deals": picks[:5], "stat": _won_man(ledger.get("saved", 0)),
                 "stat_label": "주간 1위만 샀다면 누적 절약액"},
                {"kind": "recap_ledger", "post": post, "ledger": ledger, "rows": ctx.get("ledger_rows", [])},
                {"kind": "recap_next", "post": post, "events": ctx.get("events", []),
                 "week_count": ctx.get("week_count", 0), "spotlights": ctx.get("spotlights", [])},
                {"kind": "cta", "post": post}]

    every = picks
    stat, stat_label = f"{max((d.discount for d in every), default=0)}%", "최대 할인"
    if kind == "ending" and every:
        first_end = min(datetime.fromisoformat(d.ends_at.replace("Z", "+00:00")) for d in every)
        hours = max(0, int((first_end - datetime.now(timezone.utc)).total_seconds() // 3600))
        stat, stat_label = (f"D-{hours // 24}" if hours >= 24 else f"{hours}H"), "가장 빠른 마감"
    elif kind in ("report", "weekly", "aaa", "console"):
        stat, stat_label = _won_man(sum(d.regular - d.price for d in every[:5])), "TOP 5 할인액 합계"
    elif kind == "under5k":
        stat, stat_label = f"₩{min((d.price for d in every), default=0):,}", "가장 싼 게임"
    slides = [{"kind": "cover", "post": post, "deals": every[:5], "stat": stat, "stat_label": stat_label,
               "stores": stores}]

    if pt.layout == "report":
        slides.append({"kind": "report_stats", "post": post, "stats": ctx.get("stats", {}), "deals": every[:3]})
        if ctx.get("events") or ctx.get("spotlights"):
            slides.append({"kind": "report_events", "post": post, "events": ctx.get("events", [])[:5],
                           "spotlights": ctx.get("spotlights", [])[:3]})
    if pt.layout == "cinema":
        slides += [{"kind": "cinema", "deal": d, "rank": i + 1, "post": post} for i, d in enumerate(every)]
    elif pt.layout == "grid":
        slides += [{"kind": "grid", "deals": every[i:i + 4], "offset": i, "post": post} for i in range(0, len(every), 4)]
    elif pt.layout == "duo":
        slides += [{"kind": "duo", "deals": every[i:i + 2], "offset": i, "post": post} for i in range(0, len(every), 2)]
    else:
        slides += [{"kind": "hero", "deal": d, "rank": i + 1, "post": post} for i, d in enumerate(every[:pt.heroes])]
        rest = every[pt.heroes:]
        for i in range(0, len(rest), LIST_ROWS):
            slides.append({"kind": "list", "deals": rest[i:i + LIST_ROWS], "offset": pt.heroes + i, "post": post})
    if kind in ("report", "weekly") and free:
        slides += [{"kind": "free", "game": g, "post": post}
                   for g in [g for g in free if not g.upcoming and not g.kr_blocked][:1]]
    slides.append({"kind": "cta", "post": post})
    return slides[:20]


SCHEDULE_LINE = "월 리포트 · 화 대작 · 수 인디 · 목 5천원/한국어 · 금 0시 무료게임 · 금 마감임박 · 토 콘솔 · 일 결산"


def caption(kind: str, picks: list[Deal], free: list[FreeGame], affiliate: bool = False, ctx: dict | None = None) -> str:
    ctx = ctx or {}
    pt = POSTS[kind]
    lines = []
    if affiliate:
        lines.append("[광고] 이 게시물에는 제휴 링크가 포함되어 있습니다.")
    lines += [pt.hook.format(n=len(picks)), ""]
    if kind == "free":
        for g in free:
            when = "다음 주 무료 예정" if g.upcoming else f"~{_kst(g.ends_at)}까지"
            blocked = " · 한국 계정 미제공" if g.kr_blocked else ""
            lines.append(f"{g.title} (정가 ₩{g.regular:,}) {when}{blocked}")
        if any(g.kr_blocked for g in free):
            lines += ["", "한국 계정 미제공: 에픽이 한국을 제공 국가에서 뺀 게임입니다. 한국 계정으로는 받을 수 없습니다."]
    elif kind == "recap":
        led = ctx.get("ledger") or {}
        lines.append(f"{led.get('count', 0)}주 동안 주간 1위 {led.get('count', 0)}개를 샀다면: "
                     f"정가 ₩{led.get('regular', 0):,} → 실제 ₩{led.get('spent', 0):,} (₩{led.get('saved', 0):,} 절약)")
        for e in ctx.get("events", [])[:4]:
            lines.append(f"- {e['name']} {e['start']:%-m/%-d}~{e['end']:%-m/%-d} ({e['status']})")
    else:
        if kind == "report":
            for e in ctx.get("events", [])[:3]:
                lines.append(f"[{e['status']}] {e['name']} {e['start']:%-m/%-d}~{e['end']:%-m/%-d}")
            for s in ctx.get("spotlights", [])[:3]:
                lines.append(f"[기획전] {s['title']}")
            if ctx.get("events") or ctx.get("spotlights"):
                lines.append("")
        for i, d in enumerate(picks, 1):
            extra = f" · ~{_kst(d.ends_at)} 종료" if kind == "ending" and d.ends_at else ""
            ko = f" · 한국어 {d.korean}" if d.korean and d.korean != "미지원" else ""
            cheaper = next((o for o in d.offers if o["price"] < d.price), None)
            if cheaper:
                ko += f" · {cheaper['platform'] or STORE_NAMES[cheaper['store']]} ₩{cheaper['price']:,}"
            verdict = " · 역대 최저가(ITAD)" if config.SHOW_VERDICT and d.verdict == "best" else ""
            lines.append(f"{i}. {d.title} ({STORE_NAMES[d.store]}) -{d.discount}% ₩{d.price:,}{ko}{verdict}{extra}")
    lines += ["", "기다리는 게임을 댓글로 남겨 주세요. 할인하면 알려드릴게요.", SCHEDULE_LINE,
              "가격은 게시 시점 기준이며 바뀔 수 있습니다.", "", pt.hashtags]
    return "\n".join(lines)


def _kst(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST).strftime("%-m/%-d %H:%M")


def story_caption(d: Deal) -> str:
    return f"{d.title} -{d.discount}% ₩{d.price:,}\n{d.url}"


def report_stats(deals: list[Deal], picks: list[Deal], free: list[FreeGame]) -> dict:
    """월요일 리포트의 숫자 카드."""
    good = [d for d in deals if curate.passes(d)]
    return {
        "good_count": len(good),
        "avg_pct": round(sum(d.discount for d in good) / len(good)) if good else 0,
        "max_pct": max((d.discount for d in good), default=0),
        "korean_count": sum(1 for d in good if d.korean in ("음성", "자막", "지원")),
        "free_count": sum(1 for g in free if not g.upcoming and not g.kr_blocked),
        "ending_count": len(ending_soon(good, hours=24 * 7)),
    }


def next_week_events(events: list[dict], today: date | None = None) -> list[dict]:
    today = today or datetime.now(KST).date()
    return [e for e in events if e["start"] <= today + timedelta(days=8)]
