"""에픽게임즈 무료 배포 + 할인."""
from __future__ import annotations

from ..http import get
from ..models import Deal, FreeGame

URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"


def _slug(e: dict) -> str:
    for m in (e.get("catalogNs") or {}).get("mappings") or []:
        if m.get("pageSlug"):
            return m["pageSlug"]
    return e.get("productSlug") or e.get("urlSlug") or ""


def _image(e: dict) -> str:
    imgs = {i["type"]: i["url"] for i in e.get("keyImages", [])}
    for t in ("OfferImageWide", "DieselStoreFrontWide", "Thumbnail", "OfferImageTall"):
        if t in imgs:
            return imgs[t]
    return ""


def _image_tall(e: dict) -> str:
    imgs = {i["type"]: i["url"] for i in e.get("keyImages", [])}
    return imgs.get("OfferImageTall") or imgs.get("DieselStoreFrontTall") or ""


def _offers(e: dict, kind: str) -> list[dict]:
    p = e.get("promotions") or {}
    return [o for g in p.get(kind) or [] for o in g.get("promotionalOffers", [])]


def fetch() -> tuple[list[FreeGame], list[Deal]]:
    data = get(URL, params={"locale": "ko", "country": "KR", "allowCountries": "KR"}).json()
    elements = data["data"]["Catalog"]["searchStore"]["elements"]
    free, deals = [], []
    for e in elements:
        slug = _slug(e)
        url = f"https://store.epicgames.com/ko/p/{slug}" if slug else "https://store.epicgames.com/ko/free-games"
        price = e["price"]["totalPrice"]
        div = 10 ** (price.get("currencyInfo") or {}).get("decimals", 0)  # KRW 는 0
        regular, final = price["originalPrice"] // div, price["discountPrice"] // div
        for o in _offers(e, "promotionalOffers"):
            if final == 0 and regular > 0:
                free.append(FreeGame("epic", e["title"], url, _image(e), o["startDate"], o["endDate"], regular,
                                      image_tall=_image_tall(e)))
            elif final < regular:
                deals.append(Deal("epic", e["id"], e["title"], url, final, regular,
                                  round((1 - final / regular) * 100), image=_image(e), ends_at=o["endDate"]))
        for o in _offers(e, "upcomingPromotionalOffers"):
            if o.get("discountSetting", {}).get("discountPercentage") == 0:
                free.append(FreeGame("epic", e["title"], url, _image(e), o["startDate"], o["endDate"], regular,
                                      upcoming=True, image_tall=_image_tall(e)))
    return free, deals
