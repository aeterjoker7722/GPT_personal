"""PlayStation Store (한국) 할인.

스토어 웹이 쓰는 GraphQL(persisted query)을 그대로 호출한다. 공개 API가 아니라서
스토어가 개편되면 sha256Hash 가 바뀔 수 있다. 그때는 스토어 카테고리 페이지를 브라우저로 열어
categoryGridRetrieve 요청의 해시를 다시 확인할 것.

- 목록: '전체 상품' 카테고리를 베스트셀러순으로 받아 할인 중인 제품판만 남긴다.
- 할인 종료일은 목록에 없어서 표시하지 않는다(역대 최저가 판정도 하지 않음).
"""
from __future__ import annotations

import json
import re
import time

from ..http import session
from ..models import Deal

URL = "https://web.np.playstation.com/api/graphql/v1/op"
ALL_PRODUCTS = "3f772501-f6f8-49b7-abac-874a88ca4897"
GRID_HASH = "88c0b9a1273c6d320c51cd73e390924e21ae28bf09f01cde8b84b1034b16cd03"
HEADERS = {"x-psn-store-locale-override": "ko-KR", "content-type": "application/json", "accept": "application/json"}


def _won(text: str | None) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def strip_languages(name: str) -> str:
    """'BIOHAZARD RE:4 (중국어(간체자), 한국어, 영어)' → 'BIOHAZARD RE:4'. 괄호가 중첩돼 있어 뒤에서부터 짝을 찾는다."""
    name = name.strip()
    if not name.endswith(")"):
        return name
    depth = 0
    for i in range(len(name) - 1, -1, -1):
        depth += {")": 1, "(": -1}.get(name[i], 0)
        if depth == 0:
            inner = name[i + 1:-1]
            return name[:i].strip() if ("한국어" in inner or "영어" in inner) else name
    return name


def _media(product: dict) -> dict:
    out = {}
    for m in product.get("media") or []:
        out.setdefault(m["role"], m["url"])
    return out


def _page(offset: int, size: int = 24) -> list[dict]:
    variables = {
        "id": ALL_PRODUCTS, "pageArgs": {"size": size, "offset": offset},
        "sortBy": {"name": "sales30", "isAscending": False},
        "filterBy": ["storeDisplayClassification:FULL_GAME"], "facetOptions": [],
    }
    ext = {"persistedQuery": {"version": 1, "sha256Hash": GRID_HASH}}
    r = session().get(URL, params={"operationName": "categoryGridRetrieve", "variables": json.dumps(variables),
                                   "extensions": json.dumps(ext)}, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()["data"]["categoryGridRetrieve"]["products"] or []


def fetch(pages: int = 6) -> list[Deal]:
    deals = []
    rank = 0
    for i in range(pages):
        for p in _page(i * 24):
            rank += 1
            price = p.get("price") or {}
            final, base = _won(price.get("discountedPrice")), _won(price.get("basePrice"))
            if price.get("isTiedToSubscription") or not base or final >= base:
                continue  # PS Plus 전용 할인은 제외 (구독자만 받는 가격)
            m = _media(p)
            name = p["name"]
            korean = "지원" if "한국어" in name else None  # 상품명에 언어가 적힌 경우만 (음성/자막 구분은 없음)
            title = strip_languages(name)
            deals.append(Deal(
                store="playstation", store_id=p["id"], title=title,
                url=f"https://store.playstation.com/ko-kr/product/{p['id']}",
                price=final, regular=base, discount=round((1 - final / base) * 100),
                image=m.get("SIXTEEN_BY_NINE_BANNER") or m.get("MASTER", ""),
                art_tall=m.get("PORTRAIT_BANNER") or m.get("GAMEHUB_COVER_ART", ""),
                art_wide=m.get("BACKGROUND", ""), logo=m.get("LOGO", ""),
                trailer=m.get("PREVIEW", ""), korean=korean,
                platforms=p.get("platforms") or [], popularity=rank,
            ))
        time.sleep(1)
    return deals
