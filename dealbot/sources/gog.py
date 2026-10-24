"""GOG 할인 (한국 계정은 USD 결제이므로 원화는 환산 표시)."""
from __future__ import annotations

from .. import config
from ..http import get
from ..models import Deal

URL = "https://catalog.gog.com/v1/catalog"


def _products(pages: int):
    for page in range(1, pages + 1):  # API 한 번에 최대 48개
        r = get(URL, params={
            "limit": 48, "page": page, "order": "desc:bestselling", "discounted": "eq:true",
            "productType": "in:game,pack", "countryCode": "KR", "currencyCode": "USD", "locale": "en-US",
        })
        yield from r.json().get("products", [])


def fetch(pages: int = 4) -> list[Deal]:
    # 할인율 순으로 받으면 듣보 게임만 나오므로 판매량 순에서 할인 중인 것만 받는다
    deals = []
    for p in _products(pages):
        price = p.get("price") or {}
        try:
            final = float(price["finalMoney"]["amount"])
            base = float(price["baseMoney"]["amount"])
        except (KeyError, TypeError, ValueError):
            continue
        if base <= 0 or final >= base:
            continue
        rating = p.get("reviewsRating")  # 0~50 (별점 x10)
        deals.append(Deal(
            store="gog", store_id=p["slug"], title=p["title"], url=p["storeLink"],
            price=int(round(final * config.USD_KRW, -1)), regular=int(round(base * config.USD_KRW, -1)),
            discount=round((1 - final / base) * 100),
            image=p.get("coverHorizontal") or "",
            currency_note=f"${final:.2f} (약 원화 환산)",
            review_pct=rating * 2 if rating else None,
            review_count=p.get("reviewsCount"),
            tags=[g["name"] for g in p.get("genres", [])][:3],
        ))
    return deals
