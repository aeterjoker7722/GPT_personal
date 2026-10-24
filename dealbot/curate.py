"""선별, 점수화, 스토어 간 가격 비교, 시리즈 묶음."""
from __future__ import annotations

import math
import re
import unicodedata

from . import config
from .models import Deal

VERDICT_BONUS = {"best": 25, "near": 10, "unknown": 0, "wait": -20}
KOREAN_BONUS = {"음성": 12, "자막": 8, "미지원": -10}


def normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKC", title).lower()
    t = re.sub(r"[™®©:'’\-–—!?.,]", " ", t)
    t = re.sub(r"\b(the|edition|standard|digital|pc)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def compare_stores(deals: list[Deal]) -> None:
    """같은 게임이 다른 스토어에서 더 싸면 cheaper_elsewhere 를 채운다 (제목 정규화 일치)."""
    by_title: dict[str, list[Deal]] = {}
    for d in deals:
        by_title.setdefault(normalize_title(d.title), []).append(d)
    for group in by_title.values():
        if len(group) < 2:
            continue
        cheapest = min(group, key=lambda d: d.price)
        for d in group:
            if d is not cheapest and cheapest.price < d.price:
                d.cheaper_elsewhere = {"store": cheapest.store, "price": cheapest.price, "url": cheapest.url}
        # 한국어 지원, 평가 정보는 아는 쪽 값을 공유 (다이렉트게임즈는 평가가 없음)
        known = next((d.korean for d in group if d.korean), None)
        rated = next((d for d in group if d.review_pct is not None), None)
        for d in group:
            d.korean = d.korean or known
            if rated and d.review_pct is None:
                d.review_pct, d.review_count = rated.review_pct, rated.review_count


def score(d: Deal) -> float:
    s = d.discount * 0.6
    if d.review_pct is not None:
        s += (d.review_pct - 70) * 0.8
    if d.review_count:
        s += min(math.log10(d.review_count) * 6, 30)
    s += VERDICT_BONUS.get(d.verdict, 0)
    s += KOREAN_BONUS.get(d.korean or "", 0)
    if d.regular >= 30000:  # 원래 비싼 게임이 할인할 때 반응이 큼
        s += 8
    return round(s, 1)


def passes(d: Deal) -> bool:
    if d.discount < config.MIN_DISCOUNT:
        return False
    if d.store in ("steam", "gog"):
        if d.review_pct is None or d.review_pct < config.MIN_REVIEW_PCT:
            return False
        if d.store == "steam" and (d.review_count or 0) < config.MIN_REVIEW_COUNT:
            return False
    return True


def pick(deals: list[Deal], n: int) -> list[Deal]:
    for d in deals:
        d.score = score(d)
    good = sorted((d for d in deals if passes(d)), key=lambda d: d.score, reverse=True)
    # 같은 게임이 여러 스토어에 있으면 가장 싼 하나만 노출
    out, seen = [], set()
    for d in good:
        t = normalize_title(d.title)
        if t in seen or d.cheaper_elsewhere:
            continue
        seen.add(t)
        out.append(d)
        if len(out) >= n:
            break
    return out


SERIES = {
    "top": ("이번 주 할인 TOP", lambda d: True),
    "under5k": ("5천 원 이하 명작", lambda d: d.price <= 5000),
    "korean": ("한국어 지원 할인작", lambda d: d.korean in ("음성", "자막")),
    "best": ("역대 최저가 갱신", lambda d: d.verdict == "best"),
}


def series(deals: list[Deal], key: str, n: int) -> list[Deal]:
    _, cond = SERIES[key]
    return pick([d for d in deals if cond(d)], n)
