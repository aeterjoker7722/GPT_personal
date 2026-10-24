"""가격 이력 저장과 '지금 사도 되나' 판정.

판정 근거 우선순위
1. IsThereAnyDeal 역대 최저가 (ITAD_API_KEY 설정 시, 스팀 한정, KR 지역 기준)
2. 이 도구가 직접 쌓은 로컬 가격 기록 (매일 돌릴수록 정확해짐)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import config
from .http import post
from .models import Deal

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    store TEXT, store_id TEXT, title TEXT, price INTEGER, regular INTEGER, discount INTEGER,
    seen_at TEXT, PRIMARY KEY (store, store_id, seen_at)
);
"""


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.executescript(SCHEMA)
    return con


def record(con: sqlite3.Connection, deals: list[Deal]) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    con.executemany(
        "INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?)",
        [(d.store, d.store_id, d.title, d.price, d.regular, d.discount, today) for d in deals],
    )
    con.commit()


def local_low(con: sqlite3.Connection, deal: Deal) -> tuple[int | None, int]:
    """(기록된 최저가, 기록 일수)."""
    row = con.execute(
        "SELECT MIN(price), COUNT(DISTINCT seen_at) FROM prices WHERE store=? AND store_id=?",
        (deal.store, deal.store_id),
    ).fetchone()
    return row[0], row[1] or 0


def itad_lows(steam_appids: list[str]) -> dict[str, int]:
    """스팀 appid -> ITAD 역대 최저가(원, KR). 키가 없거나 실패하면 빈 dict."""
    if not config.ITAD_API_KEY or not steam_appids:
        return {}
    base = "https://api.isthereanydeal.com"
    key = {"key": config.ITAD_API_KEY}
    try:
        ids = post(f"{base}/lookup/id/shop/61/v1", params=key,
                   json=[f"app/{a}" for a in steam_appids]).json()  # 61 = Steam
        appid_by_itad = {v: k.split("/")[1] for k, v in ids.items() if v}
        lows = post(f"{base}/games/historylow/v1", params={**key, "country": "KR"},
                    json=list(appid_by_itad)).json()
    except Exception as e:
        print(f"[itad] 조회 실패: {e}")
        return {}
    out = {}
    for item in lows:
        low = (item.get("low") or {}).get("price") or {}
        if low.get("currency") == "KRW" and item.get("id") in appid_by_itad:
            out[appid_by_itad[item["id"]]] = int(low["amount"])
    return out


def judge(deal: Deal, low: int | None, source: str, days: int = 0) -> None:
    if low is None:
        deal.verdict, deal.verdict_note = "unknown", "가격 기록 수집 중"
        return
    deal.history_low = low
    if deal.price <= low:
        deal.verdict = "best"
        deal.verdict_note = "역대 최저가" if source == "itad" else f"추적 {days}일 중 최저가"
    elif deal.price <= low * config.NEAR_LOW_RATIO or deal.price - low <= config.NEAR_LOW_WON:
        deal.verdict = "near"
        deal.verdict_note = f"최저가 대비 +{deal.price - low:,}원"
    else:
        deal.verdict = "wait"
        deal.verdict_note = f"{low:,}원까지 내려간 적 있음"


def apply_verdicts(con: sqlite3.Connection, deals: list[Deal]) -> None:
    itad = itad_lows([d.store_id for d in deals if d.store == "steam"])
    for d in deals:
        if d.store == "steam" and d.store_id in itad:
            judge(d, itad[d.store_id], "itad")
            continue
        low, days = local_low(con, d)
        # 기록이 1일뿐이면 오늘 가격이 곧 최저라 의미가 없으므로 판정 보류
        judge(d, low if days >= 7 else None, "local", days)

