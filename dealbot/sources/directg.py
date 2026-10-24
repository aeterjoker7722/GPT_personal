"""다이렉트게임즈 (국내 공식 키셀러) 할인 목록 HTML 파싱.

robots.txt 가 열려 있지 않은 사이트일 수 있으니 하루 몇 회 이내로만 호출하고,
상업적으로 쓰기 전에 이용약관을 확인할 것.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..http import get
from ..models import Deal

BASE = "https://directg.net"
LIST_URL = BASE + "/game/game_list.html"
PLATFORM_ICONS = {"steam_logo": "Steam", "epic": "Epic", "gog": "GOG", "ubisoft": "Ubisoft", "ea": "EA", "xbox": "Xbox"}


def _won(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def parse(markup: str) -> list[Deal]:
    soup = BeautifulSoup(markup, "html.parser")
    deals = []
    for card in soup.select("div.card"):
        a = card.select_one(".product_name_area a")
        rate = card.select_one(".discount-rate")
        final = card.select_one(".price_area strong")
        orig = card.select_one(".price_area s")
        if not (a and rate and final and orig):
            continue
        href = a["href"]
        sku = re.search(r"sku=([\w-]+)", href)
        badges = [b.text.strip() for b in card.select(".badge_area .badge")]
        korean = None
        for b in badges:
            if "한글" in b or "한국어" in b:
                korean = "음성" if "음성" in b else "자막"
        icon = card.select_one(".platform-area img")
        platform = ""
        if icon is not None:
            src = icon.get("src", "")
            platform = next((v for k, v in PLATFORM_ICONS.items() if k in src), "")
        img = card.select_one(".thumb-area img")
        deals.append(Deal(
            store="directg", store_id=sku.group(1) if sku else href,
            title=a.get_text(strip=True), url=urljoin(BASE, href),
            price=_won(final.text), regular=_won(orig.text), discount=_won(rate.text),
            image=img["src"] if img else "", korean=korean,
            tags=[t for t in [platform] if t] + [b for b in badges if b in ("예약구매", "특전")],
        ))
    return deals


def fetch(pages: int = 3) -> list[Deal]:
    deals = []
    for page in range(1, pages + 1):
        r = get(LIST_URL, params={"sort": "discount", "is_promotion": "Y", "page": page})
        batch = parse(r.text)
        if not batch:
            break
        deals.extend(batch)
    seen, unique = set(), []
    for d in deals:
        if d.store_id not in seen:
            seen.add(d.store_id)
            unique.append(d)
    return unique
