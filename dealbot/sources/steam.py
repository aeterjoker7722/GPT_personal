"""Steam 할인 수집.

- 목록: 스토어 검색(specials=1, 인기순) JSON. 리뷰 점수는 영어 평가 기준 툴팁에서 파싱.
- 상세: IStoreBrowseService/GetItems(KR) 로 종료일, 전체 리뷰, 한국어 지원, 로고/키아트, 트레일러 보강.
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .. import config
from ..http import get
from ..models import Deal

SEARCH_URL = "https://store.steampowered.com/search/results/"
STOREBROWSE_URL = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1"
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


ASSET_BASE = "https://shared.akamai.steamstatic.com/store_item_assets/"
TRAILER_BASE = "https://video.akamai.steamstatic.com/store_trailers/"
KOREAN = 4  # Steam ELanguage: 한국어


def korean_support(languages: list[dict]) -> str:
    for lang in languages or []:
        if lang.get("elanguage") == KOREAN and lang.get("supported"):
            return "음성" if lang.get("full_audio") else "자막"
    return "미지원"


def _apply(deal: Deal, it: dict) -> None:
    """IStoreBrowseService/GetItems 결과를 Deal 에 반영."""
    deal.title = it.get("name") or deal.title
    po = it.get("best_purchase_option") or {}
    if po.get("final_price_in_cents"):
        deal.price = int(po["final_price_in_cents"]) // 100
        deal.regular = int(po.get("original_price_in_cents") or po["final_price_in_cents"]) // 100
        deal.discount = po.get("discount_pct") or deal.discount
    ends = [a["discount_end_date"] for a in po.get("active_discounts", []) if a.get("discount_end_date")]
    if ends:
        deal.ends_at = datetime.fromtimestamp(min(ends), timezone.utc).isoformat()
    rv = (it.get("reviews") or {}).get("summary_filtered") or {}
    if rv.get("review_count"):
        deal.review_pct, deal.review_count = rv.get("percent_positive"), rv["review_count"]
        deal.review_desc = rv.get("review_score_label", "")
    deal.korean = korean_support(it.get("supported_languages"))
    assets = it.get("assets") or {}
    fmt = assets.get("asset_url_format", "")
    asset = lambda name: ASSET_BASE + fmt.replace("${FILENAME}", name) if fmt and name else ""
    deal.image = asset(assets.get("header")) or deal.image
    deal.art_tall = asset(assets.get("library_capsule_2x") or assets.get("library_capsule"))
    deal.art_wide = asset(assets.get("library_hero"))
    deal.logo = asset("logo.png")
    info = it.get("basic_info") or {}
    deal.developer = ", ".join(x["name"] for x in info.get("developers", [])[:1])
    deal.publisher = ", ".join(x["name"] for x in info.get("publishers", [])[:1])
    rel = (it.get("release") or {}).get("steam_release_date")
    if rel:
        deal.release_year = datetime.fromtimestamp(rel, timezone.utc).year
    for tr in (it.get("trailers") or {}).get("highlights", []):
        dash = next((a["cdn_path"] for a in tr.get("adaptive_trailers", []) if a.get("encoding") == "dash_h264"), None)
        if dash:
            deal.trailer = TRAILER_BASE + dash
            break


def enrich_many(deals: list[Deal], limit: int = config.STEAM_ENRICH_TOP) -> None:
    """상위 후보를 50개씩 묶어 한 번에 상세 조회 (가격, 종료일, 리뷰, 한국어, 아트, 트레일러)."""
    targets = deals[:limit]
    for i in range(0, len(targets), 50):
        chunk = targets[i:i + 50]
        req = {
            "ids": [{"appid": int(d.store_id)} for d in chunk],
            "context": {"language": "koreana", "country_code": "KR"},
            "data_request": {"include_assets": True, "include_all_purchase_options": True, "include_reviews": True,
                             "include_basic_info": True, "include_supported_languages": True,
                             "include_trailers": True, "include_release": True},
        }
        try:
            items = get(STOREBROWSE_URL, params={"input_json": json.dumps(req)}).json()["response"]["store_items"]
        except Exception as e:
            print(f"[steam] 상세 조회 실패: {e}")
            continue
        by_id = {str(it.get("appid") or it.get("id")): it for it in items if it.get("success") == 1}
        for d in chunk:
            if d.store_id in by_id:
                _apply(d, by_id[d.store_id])
        time.sleep(1)
