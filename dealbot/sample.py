"""네트워크 없이 템플릿을 확인하기 위한 샘플 (실제 수집 결과 스냅샷)."""
import json
from pathlib import Path

from .models import Deal, FreeGame

FIXTURE = Path(__file__).parent / "fixtures" / "sample_deals.json"


def sample_data():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    picks = [Deal(**d) for d in data["picks"]]
    more = [Deal(**d) for d in data["more"]]
    free = [FreeGame(**g) for g in data["free"]]
    return picks, more, free
