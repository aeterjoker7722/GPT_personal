"""스팀 세일·페스티벌 일정과 진행 중인 기획전.

- 일정: Steamworks 공식 문서 'Upcoming Steam Events' 페이지의 날짜를 읽는다(계절 세일, 넥스트 페스트, 테마 페스티벌).
  문서 형식이 바뀌면 못 읽을 수 있어서, data/steam_events_manual.csv 로 보충/수정할 수 있다.
  CSV 헤더: name,start,end   (날짜는 YYYY-MM-DD)
- 기획전: 스팀 메인(featuredcategories)의 스포트라이트(프랜차이즈 할인, 퍼블리셔 할인, 주말 특가 등).
"""
from __future__ import annotations

import csv
import html
import re
from datetime import date, timedelta

from .. import config
from ..http import get

EVENTS_URL = "https://partner.steamgames.com/doc/marketing/upcoming_events"
FEATURED_URL = "https://store.steampowered.com/api/featuredcategories"
MANUAL_CSV = config.DATA_DIR / "steam_events_manual.csv"
SEASON_KR = {"Winter": "겨울 할인", "Spring": "봄 할인", "Summer": "여름 할인", "Autumn": "가을 할인"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _d(month: str, day: str, year: str | int) -> date:
    return date(int(year), MONTHS[month[:3].lower()], int(day))


def _page_text() -> str:
    page = get(EVENTS_URL, headers={"User-Agent": "Mozilla/5.0"}).text
    m = re.search(r'class="documentation_bbcode"(.*)', page, re.S)
    text = re.sub(r"<br\s*/?>", "\n", m.group(1) if m else page)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def parse_calendar(text: str) -> list[dict]:
    events = []
    for season, year, m1, d1, y1, m2, d2, y2 in re.findall(
            r"(Winter|Spring|Summer|Autumn) Sale (\d{4}) \| (\w+) (\d+), (\d{4}) - (\w+) (\d+), (\d{4})", text):
        events.append({"name": f"스팀 {SEASON_KR[season]}", "kind": "season",
                       "start": _d(m1, d1, y1), "end": _d(m2, d2, y2)})
    # "Next Fest | October 19 - October 26, 2026" 또는 "Next Fest | June 14 - 21, 2027"
    for m1, d1, m2, d2, y in re.findall(r"Next Fest \| (\w+) (\d+) - (?:(\w+) )?(\d+), (\d{4})", text):
        events.append({"name": "스팀 넥스트 페스트 (체험판 축제)", "kind": "nextfest",
                       "start": _d(m1, d1, y), "end": _d(m2 or m1, d2, y)})
    # 테마 페스티벌 표: "2026 Fests ... Oct 26 Nov 2 Steam Scream V Registration details ..."
    for block_year, block in re.findall(r"(\d{4}) Fests?(.*?)(?=\d{4} Fests?|$)", text, re.S):
        for m1, d1, m2, d2, name in re.findall(
                r"\b([A-Z][a-z]{2}) (\d{1,2}) ([A-Z][a-z]{2}) (\d{1,2}) (.{3,60}?) Registration", block):
            if m1.lower() in MONTHS and m2.lower() in MONTHS:
                start = _d(m1, d1, block_year)
                end = _d(m2, d2, int(block_year) + (1 if MONTHS[m2.lower()] < MONTHS[m1.lower()] else 0))
                name = re.sub(r"^Steam\s+", "", name.strip())
                events.append({"name": f"스팀 {name}", "kind": "fest", "start": start, "end": end})
    return events


def _manual() -> list[dict]:
    if not MANUAL_CSV.exists():
        return []
    with MANUAL_CSV.open(encoding="utf-8-sig") as f:
        return [{"name": r["name"], "kind": "manual", "start": date.fromisoformat(r["start"]),
                 "end": date.fromisoformat(r["end"])} for r in csv.DictReader(f)]


def calendar(today: date | None = None, ahead_days: int = 45) -> list[dict]:
    """진행 중이거나 ahead_days 안에 시작하는 일정 (시작일 순)."""
    today = today or date.today()
    try:
        events = parse_calendar(_page_text())
    except Exception as e:
        print(f"[steam-events] 일정 조회 실패: {e}")
        events = []
    events += _manual()
    seen, out = set(), []
    for e in sorted(events, key=lambda e: e["start"]):
        if e["end"] < today or e["start"] > today + timedelta(days=ahead_days) or e["name"] in seen:
            continue
        seen.add(e["name"])
        e["status"] = "진행 중" if e["start"] <= today else f"D-{(e['start'] - today).days}"
        out.append(e)
    return out


def _sale_title(url: str) -> str:
    """기획전 페이지 제목 (예: 'Don't Starve 프랜차이즈 할인'). 실패하면 빈 문자열."""
    try:
        page = get(url, params={"l": "koreana", "cc": "kr"}, retries=1).text
    except Exception:
        return ""
    m = re.search(r"<title>(.*?)</title>", page, re.S)
    title = html.unescape(re.sub(r"\s+", " ", m.group(1)).strip()) if m else ""
    return re.sub(r"\s*(on Steam|- Steam|Steam의|\| Steam).*$", "", title)


def spotlights() -> list[dict]:
    """스팀 메인에 걸린 기획전 (프랜차이즈·퍼블리셔 할인). 개별 게임 '주말 특가'는 제외."""
    data = get(FEATURED_URL, params={"cc": "kr", "l": "koreana"}).json()
    out = []
    for v in data.values():
        if not isinstance(v, dict) or v.get("id") != "cat_spotlight":
            continue
        for it in v.get("items", []):
            url = it.get("url", "")
            if "/sale/" not in url:
                continue
            out.append({"label": it.get("name", ""), "title": _sale_title(url) or it.get("name", ""),
                        "image": it.get("header_image", ""), "url": url})
    return out
