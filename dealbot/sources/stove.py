"""스토브 할인.

스토브 스토어는 클라이언트 렌더링(Nuxt)이고 공개 API 문서가 없다.
개발 환경(해외 서버)에서는 검색 결과가 비어 있어 자동 수집을 확인하지 못했다.
그래서 수동으로 채운 CSV(data/stove_manual.csv)를 읽어 다른 스토어와 같은 형식으로 합친다.

CSV 헤더: title,url,price,regular,image,korean,ends_at
"""
from __future__ import annotations

import csv

from .. import config
from ..models import Deal

MANUAL_CSV = config.DATA_DIR / "stove_manual.csv"


def fetch() -> list[Deal]:
    if not MANUAL_CSV.exists():
        return []
    deals = []
    with MANUAL_CSV.open(encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f)):
            price, regular = int(row["price"]), int(row["regular"])
            if regular <= 0 or price >= regular:
                continue
            deals.append(Deal(
                store="stove", store_id=row.get("url") or f"manual-{i}", title=row["title"], url=row["url"],
                price=price, regular=regular, discount=round((1 - price / regular) * 100),
                image=row.get("image", ""), korean=row.get("korean") or None, ends_at=row.get("ends_at") or None,
            ))
    return deals
