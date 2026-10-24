"""공통 데이터 모델."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Deal:
    store: str                      # steam / gog / epic / directg / stove
    store_id: str                   # 스토어 내부 ID (appid, slug 등)
    title: str
    url: str
    price: int                      # 할인가 (원)
    regular: int                    # 정가 (원)
    discount: int                   # 할인율 %
    image: str = ""
    currency_note: str = ""         # "USD 환산" 등 표시용
    korean: Optional[str] = None    # "음성" / "자막" / "미지원" / None(미확인)
    review_pct: Optional[int] = None
    review_count: Optional[int] = None
    review_desc: str = ""
    ends_at: Optional[str] = None   # ISO8601
    tags: list[str] = field(default_factory=list)
    art_tall: str = ""              # 세로 키아트 (600x900)
    art_wide: str = ""              # 와이드 키아트 (library hero)
    trailer: str = ""               # 트레일러 DASH(h264) manifest URL
    logo: str = ""                  # 공식 로고 (투명 PNG)
    developer: str = ""
    publisher: str = ""
    release_year: Optional[int] = None

    # 가공 단계에서 채움
    verdict: str = "unknown"        # best / near / wait / unknown
    verdict_note: str = ""
    history_low: Optional[int] = None
    cheaper_elsewhere: Optional[dict] = None  # {"store": .., "price": .., "url": ..}
    score: float = 0.0
    history: list = field(default_factory=list)   # [[YYYY-MM-DD, price], ...]
    palette: dict = field(default_factory=dict)   # {"accent": "#hex", "deep": "#hex"}

    @property
    def key(self) -> str:
        return f"{self.store}:{self.store_id}"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FreeGame:
    store: str
    title: str
    url: str
    image: str
    starts_at: str
    ends_at: str
    regular: int = 0
    upcoming: bool = False
    image_tall: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
