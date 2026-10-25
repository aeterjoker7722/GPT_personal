"""주 단위 운영 상태 (data/ 아래 JSON, GitHub Actions 가 커밋해서 다음 실행에 이어 쓴다).

- week_state.json: 이번 주에 이미 소개한 게임. 요일별 게시물이 같은 게임을 반복하지 않게 한다.
- ledger.json: "매주 주간 리포트 1위만 샀다면" 누적 기록 (일요일 결산에 사용).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from . import config
from .models import Deal

KST = timezone(timedelta(hours=9))
WEEK_FILE = config.DATA_DIR / "week_state.json"
LEDGER_FILE = config.DATA_DIR / "ledger.json"


def week_id(now: datetime | None = None) -> str:
    iso = (now or datetime.now(KST)).astimezone(KST).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def used_keys() -> set[str]:
    st = _load(WEEK_FILE, {})
    return set(st.get("used", [])) if st.get("week") == week_id() else set()


def mark_used(kind: str, deals: list[Deal]) -> None:
    st = _load(WEEK_FILE, {})
    if st.get("week") != week_id():
        st = {"week": week_id(), "used": [], "posts": {}}
    for d in deals:
        if d.key not in st["used"]:
            st["used"].append(d.key)
    st["posts"][kind] = [d.title for d in deals]
    _save(WEEK_FILE, st)


def ledger() -> list[dict]:
    return _load(LEDGER_FILE, [])


def add_to_ledger(d: Deal) -> list[dict]:
    """주간 리포트 1위를 장부에 기록 (같은 주에 다시 돌려도 한 번만)."""
    rows = [r for r in ledger() if r["week"] != week_id()]
    rows.append({"week": week_id(), "title": d.title, "store": d.store, "price": d.price, "regular": d.regular,
                 "image": d.art_tall or d.image})
    _save(LEDGER_FILE, rows)
    return rows


def ledger_summary(rows: list[dict]) -> dict:
    spent = sum(r["price"] for r in rows)
    regular = sum(r["regular"] for r in rows)
    return {"count": len(rows), "spent": spent, "regular": regular, "saved": regular - spent,
            "since": rows[0]["week"] if rows else week_id()}
