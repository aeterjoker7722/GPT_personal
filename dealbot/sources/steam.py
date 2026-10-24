"""Steam 할인 수집.

- 목록: 스토어 검색(specials=1, 인기순) JSON. 리뷰 점수는 영어 평가 기준 툴팁에서 파싱.
- 상세: appdetails(cc=kr, l=koreana) 로 한국어 이름, 한국어 지원, 헤더 이미지 보강.
"""
from __future__ import annotations

import html
import re
import time

from bs4 import BeautifulSoup

from .. import config
from ..http import get
from ..models import Deal

SEARCH_URL = "https://store.steampowered.com/search/results/"
APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
REVIEW_RE = re.compile(r"(\d+)% of the ([\d,]+) user reviews")


def _parse_search_html(markup: str) -> list[Deal]:
    soup = BeautifulSoup(markup, "html.parser")
    deals = []
    for row in soup.select("a.search_result_row"):
        appid = row.get("data-ds-appid", "")
        block = row.select_one(".discount_block")
        if not appid or "," in appid or block is None:  # 번들(appid 여러 개)은 제외
            continue
        pct = int(block.get("data-discount") or 0)
        if pct <= 0:
            continue
        final = int(block.get("data-price-final") or 0) // 100
        orig_el = block.select_one(".discount_original_price")
        regular = int(re.sub(r"[^\d]", "", orig_el.text)) if orig_el else 0
        title = row.select_one(".title").text.strip()
        review_pct = review_count = None
        review_desc = ""
        rv = row.select_one(".search_review_summary")
        if rv is not None:
            tip = html.unescape(rv.get("data-tooltip-html", ""))
            review_desc = tip.split("<br>")[0]
            m = REVIEW_RE.search(tip)
            if m:
                review_pct, review_count = int(m.group(1)), int(m.group(2).replace(",", ""))
        img = row.select_one(".search_capsule img")
        deals.append(Deal(
            store="steam", store_id=appid, title=title,
            url=f"https://store.steampowered.com/app/{appid}/",
            price=final, regular=regular, discount=pct,
            image=img["src"] if img else "",
            review_pct=review_pct, review_count=review_count, review_desc=review_desc,
        ))
    return deals


def fetch_specials(pages: int = config.STEAM_PAGES) -> list[Deal]:
    deals: list[Deal] = []
    for page in range(pages):
        r = get(SEARCH_URL, params={
            "specials": 1, "cc": "kr", "l": "english", "infinite": 1,
            "count": 100, "start": page * 100, "filter": "topsellers",
        })
        data = r.json()
        batch = _parse_search_html(data.get("results_html", ""))
        if not batch:
            break
        deals.extend(batch)
        time.sleep(1)
    # 같은 appid 중복 제거 (인기순 첫 등장 유지)
    seen, unique = set(), []
    for d in deals:
        if d.store_id not in seen:
            seen.add(d.store_id)
            unique.append(d)
    return unique


def korean_support(supported_languages: str) -> str:
    """appdetails(l=koreana) 의 supported_languages 에서 한국어 지원 수준 판정."""
    if not supported_languages:
        return "미지원"
    m = re.search(r"한국어(<strong>\*</strong>)?", supported_languages)
    if not m:
        return "미지원"
    return "음성" if m.group(1) else "자막"


def enrich(deal: Deal) -> Deal:
    r = get(APPDETAILS_URL, params={"appids": deal.store_id, "cc": "kr", "l": "koreana"})
    body = r.json().get(deal.store_id) or {}
    if not body.get("success"):
        return deal
    data = body["data"]
    deal.korean = korean_support(data.get("supported_languages", ""))
    deal.image = data.get("header_image") or deal.image
    if data.get("name"):
        deal.title = data["name"]
    deal.tags = [g["description"] for g in data.get("genres", [])][:3]
    art = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{deal.store_id}"
    deal.art_tall, deal.art_wide = f"{art}/library_600x900_2x.jpg", f"{art}/library_hero.jpg"
    movies = data.get("movies") or []
    movie = next((m for m in movies if m.get("highlight")), movies[0] if movies else None)
    if movie:
        deal.trailer = movie.get("dash_h264", "")
    po = data.get("price_overview")
    if po:  # 검색 결과보다 정확한 최신 가격
        deal.price, deal.regular, deal.discount = po["final"] // 100, po["initial"] // 100, po["discount_percent"]
    return deal


def enrich_many(deals: list[Deal], limit: int = config.STEAM_ENRICH_TOP) -> None:
    for d in deals[:limit]:
        try:
            enrich(d)
        except Exception as e:  # 한 건 실패로 전체를 멈추지 않음
            print(f"[steam] appdetails 실패 {d.store_id}: {e}")
        time.sleep(1.5)  # appdetails 는 5분 200회 정도 제한
