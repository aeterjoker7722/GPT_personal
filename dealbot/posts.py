"""게시물 포맷(요일별 시리즈)과 주간 편성표.

포맷마다 고르는 기준, 표지 문구, 캡션, 해시태그가 다르다. 렌더링은 poster 템플릿 하나로 한다.
편성표와 운영 방법은 docs/weekly_plan.md 참고.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import curate
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
    heroes: int = 3      # 메인 카드 장수


POSTS = {
    "weekly": PostType("weekly", "WEEKLY TOP", "이번 주\n할인 TOP {n}",
                       "이번 주 놓치면 아까운 할인 {n}개, 평가 좋은 것만 골랐습니다.",
                       "#스팀할인 #게임할인 #스팀세일 #PC게임추천", heroes=5),
    "lowest": PostType("lowest", "ALL-TIME LOW", "역대 최저가\n갱신 {n}",
                       "지금이 역대 최저가입니다. 기다리던 게임 있으면 지금 사세요.",
                       "#역대최저가 #스팀할인 #게임할인 #스팀세일"),
    "ending": PostType("ending", "ENDING SOON", "곧 끝나는\n할인 {n}",
                       "이번 주말에 끝나는 할인입니다. 장바구니에 담아 둔 게임 확인하세요.",
                       "#스팀할인 #마감임박 #게임할인 #주말게임"),
    "under5k": PostType("under5k", "UNDER ₩5,000", "5천 원 이하\n명작 {n}",
                        "커피 한 잔 값으로 사는 명작 {n}개.",
                        "#스팀할인 #갓겜추천 #가성비게임 #인디게임"),
    "korean": PostType("korean", "KOREAN SUPPORTED", "한국어로 즐기는\n할인 {n}",
                       "한국어 자막·음성 지원되는 할인 게임만 모았습니다.",
                       "#한글패치필요없음 #스팀할인 #한국어지원 #게임추천"),
    "aaa": PostType("aaa", "AAA DEALS", "정가 5만 원 넘는\n대작 할인 {n}",
                    "원래 5만 원 넘던 대작들이 할인 중입니다.",
                    "#스팀할인 #대작게임 #AAA게임 #게임할인"),
    "console": PostType("console", "CONSOLE SALE", "주말 콘솔\n세일 {n}",
                        "주말에 할 콘솔 게임, 할인 중인 인기작 {n}개입니다. 같은 게임의 PC 가격도 같이 적었습니다.",
                        "#PS5할인 #플스할인 #PS스토어 #콘솔게임"),
    "free": PostType("free", "FREE THIS WEEK", "이번 주\n무료 게임",
                     "이번 주 무료 게임입니다. 받아 두면 계속 내 게임입니다.",
                     "#에픽무료게임 #무료게임 #에픽게임즈 #PC게임", heroes=0),
    "story": PostType("story", "TODAY'S DEAL", "오늘의 할인", "", "", heroes=1),
    "guide": PostType("guide", "HOW TO READ", "이 계정\n보는 법",
                      "할인율보다 중요한 건 '지금이 제일 싼가'입니다. 판정 기준과 요일별 편성표를 정리했습니다.",
                      "#스팀할인 #게임할인 #역대최저가", heroes=0),
}

# 수요일/토요일 큐레이션은 주차마다 돌아가며 쓴다
SERIES_ROTATION = ["under5k", "korean", "aaa"]

# 요일(월=0)별 편성. (시각, 포맷). 시각은 업로드 권장 시각(KST)
WEEKLY_PLAN = {
    0: [("12:00", "weekly"), ("20:00", "reel")],
    1: [("19:00", "lowest")],
    2: [("19:00", "series")],
    3: [("23:00", "story:upcoming-free")],
    4: [("00:05", "free"), ("18:00", "ending"), ("20:00", "reel:ending")],
    5: [("12:00", "console")],
    6: [("20:00", "story")],
}


def series_for(day: datetime) -> str:
    week = day.isocalendar().week
    idx = (week * 2 + (1 if day.weekday() == 5 else 0)) % len(SERIES_ROTATION)
    return SERIES_ROTATION[idx]


def jobs_for(day: datetime | None = None) -> list[tuple[str, str]]:
    day = (day or datetime.now(KST)).astimezone(KST)
    out = []
    for at, kind in WEEKLY_PLAN[day.weekday()]:
        out.append((at, series_for(day) if kind == "series" else kind))
    return out


def ending_soon(deals: list[Deal], hours: int = 80) -> list[Deal]:
    now = datetime.now(timezone.utc)
    soon = []
    for d in deals:
        if d.ends_at:
            end = datetime.fromisoformat(d.ends_at.replace("Z", "+00:00"))
            if now < end <= now + timedelta(hours=hours):
                soon.append(d)
    return soon


def select(kind: str, deals: list[Deal], n: int = 9) -> list[Deal]:
    """포맷별 선정. 결과가 적으면 그만큼만 쓴다(억지로 채우지 않음)."""
    if kind == "weekly":
        return curate.pick(deals, n)
    if kind == "lowest":
        return curate.pick([d for d in deals if d.verdict == "best"], n)
    if kind == "ending":
        return curate.pick(ending_soon(deals), n)
    if kind == "aaa":
        return curate.pick([d for d in deals if d.regular >= 50000], n)
    if kind in ("under5k", "korean"):
        return curate.series(deals, kind, n)
    if kind == "console":
        return curate.pick_console(deals, n)
    if kind == "story":
        return curate.pick(deals, 1)
    if kind == "guide":
        return curate.pick(deals, 5)
    return []


LIST_ROWS = 5


def trim(kind: str, picks: list[Deal]) -> list[Deal]:
    """목록 슬라이드 마지막 장에 1~2개만 남으면 그만큼 덜어 낸다 (거의 빈 장 방지)."""
    heroes = POSTS[kind].heroes
    rest = len(picks) - heroes
    if rest > LIST_ROWS and rest % LIST_ROWS in (1, 2):
        return picks[:heroes + rest // LIST_ROWS * LIST_ROWS]
    return picks


def build(kind: str, picks: list[Deal], free: list[FreeGame], stores: list[str]) -> list[dict]:
    """포맷 → 슬라이드 목록 (poster 템플릿의 kind 별 블록과 짝)."""
    pt = POSTS[kind]
    post = {"key": kind, "kicker": pt.kicker, "headline": pt.headline.format(n=len(picks)),
            "series_label": pt.kicker}
    if kind == "story":
        return [{"kind": "story", "deal": d, "post": post} for d in picks[:1]]
    if kind == "guide":
        return [{"kind": "cover", "post": post, "deals": picks[:5], "deal_count": len(picks),
                 "stat": "3", "stat_label": "판정 기준"},
                {"kind": "legend", "post": post, "deals": picks[:3]},
                {"kind": "cta", "post": post}]
    if kind == "free":
        games = sorted(free, key=lambda g: g.upcoming)
        slides = [{"kind": "cover", "post": post, "deals": [], "free_games": games,
                   "deal_count": sum(not g.upcoming for g in games), "stat": "₩0", "stat_label": "이번 주 무료"}]
        slides += [{"kind": "free", "game": g, "post": post} for g in games[:3]]
        slides.append({"kind": "cta", "post": post})
        return slides
    every = picks
    stat, stat_label = f"{max((d.discount for d in every), default=0)}%", "최대 할인"
    if kind == "ending" and every:
        first_end = min(datetime.fromisoformat(d.ends_at.replace("Z", "+00:00")) for d in every)
        hours = max(0, int((first_end - datetime.now(timezone.utc)).total_seconds() // 3600))
        stat, stat_label = (f"D-{hours // 24}" if hours >= 24 else f"{hours}H"), "가장 빠른 마감"
    elif kind == "lowest":
        stat, stat_label = f"{len(every)}", "역대 최저가"
    elif kind == "console":
        stat, stat_label = f"₩{sum(d.regular - d.price for d in every[:5]) // 10000}만", "TOP 5 할인액 합계"
    elif kind in ("weekly", "aaa"):
        stat, stat_label = f"₩{sum(d.regular - d.price for d in every[:5]) // 10000}만", "TOP 5 할인액 합계"
    slides = [{"kind": "cover", "post": post, "deals": every[:5], "deal_count": len(every),
               "stat": stat, "stat_label": stat_label, "stores": stores}]
    slides += [{"kind": "hero", "deal": d, "rank": i + 1, "post": post} for i, d in enumerate(every[:pt.heroes])]
    rest = every[pt.heroes:]
    for i in range(0, len(rest), LIST_ROWS):
        slides.append({"kind": "list", "deals": rest[i:i + LIST_ROWS], "offset": pt.heroes + i, "post": post})
    if kind == "weekly" and free:
        slides += [{"kind": "free", "game": g, "post": post} for g in [g for g in free if not g.upcoming][:1]]
    slides.append({"kind": "cta", "post": post})
    return slides[:20]


def caption(kind: str, picks: list[Deal], free: list[FreeGame], affiliate: bool = False) -> str:
    pt = POSTS[kind]
    lines = []
    if affiliate:
        lines.append("[광고] 이 게시물에는 제휴 링크가 포함되어 있습니다.")
    lines += [pt.hook.format(n=len(picks)), ""]
    marks = {"best": " · 역대 최저가", "near": " · 최저가 근접", "wait": "", "unknown": ""}
    if kind == "free":
        for g in free:
            when = "다음 주 무료 예정" if g.upcoming else f"~{_kst(g.ends_at)}까지"
            lines.append(f"{g.title} (정가 ₩{g.regular:,}) {when}")
    else:
        for i, d in enumerate(picks, 1):
            extra = f" · ~{_kst(d.ends_at)} 종료" if kind == "ending" and d.ends_at else ""
            ko = f" · 한국어 {d.korean}" if d.korean and d.korean != "미지원" else ""
            if d.pc_compare:
                diff = d.pc_compare["diff"]
                ko += f" · PC보다 ₩{-diff:,} 쌈" if diff < 0 else (f" · PC({STORE_NAMES[d.pc_compare['store']]})가 ₩{diff:,} 더 쌈" if diff > 0 else " · PC와 같은 가격")
            lines.append(f"{i}. {d.title} ({STORE_NAMES[d.store]}) -{d.discount}% ₩{d.price:,}{ko}{marks[d.verdict]}{extra}")
    lines += [
        "",
        "기다리는 게임을 댓글로 남겨 주세요. 할인하면 알려드릴게요.",
        "월 TOP · 화 최저가 · 수 큐레이션 · 금 0시 무료게임 · 금 마감임박 · 토 콘솔",
        "가격은 게시 시점 기준이며 바뀔 수 있습니다.",
        "",
        pt.hashtags,
    ]
    return "\n".join(lines)


def _kst(iso: str) -> str:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST).strftime("%-m/%-d %H:%M")


def story_caption(d: Deal) -> str:
    return f"{d.title} -{d.discount}% ₩{d.price:,}\n{d.url}"

