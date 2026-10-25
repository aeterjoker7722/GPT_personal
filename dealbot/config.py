"""설정값. 환경변수로 덮어쓸 수 있다."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DEALBOT_DATA_DIR", ROOT / "data"))
OUTPUT_DIR = Path(os.getenv("DEALBOT_OUTPUT_DIR", ROOT / "output"))
DB_PATH = DATA_DIR / "price_history.sqlite"

USER_AGENT = os.getenv("DEALBOT_UA", "dealbot/0.1 (personal deal curation; contact via repo owner)")
HTTP_TIMEOUT = 20

# GOG 는 한국에서 USD 로 결제되므로 표시용 환산 환율
USD_KRW = float(os.getenv("DEALBOT_USD_KRW", "1400"))

# IsThereAnyDeal API 키 (https://isthereanydeal.com/apps/my/ 에서 무료 발급). 없으면 로컬 기록만 사용
ITAD_API_KEY = os.getenv("ITAD_API_KEY", "")

# 수집/선별 기준
STEAM_PAGES = int(os.getenv("DEALBOT_STEAM_PAGES", "4"))      # 페이지당 100개, 인기순
STEAM_ENRICH_TOP = int(os.getenv("DEALBOT_STEAM_ENRICH", "100")) # 한국어/이미지 상세조회 개수
MIN_DISCOUNT = int(os.getenv("DEALBOT_MIN_DISCOUNT", "50"))
MIN_REVIEW_PCT = int(os.getenv("DEALBOT_MIN_REVIEW_PCT", "75"))
MIN_REVIEW_COUNT = int(os.getenv("DEALBOT_MIN_REVIEW_COUNT", "500"))

# 판정('역대 최저가')을 카드·캡션에 보여 줄지. 틀리면 역풍이 크므로 기본은 끔 (ITAD 키를 쓸 때만 켜는 것을 권장)
SHOW_VERDICT = os.getenv("DEALBOT_SHOW_VERDICT", "0") == "1"

# 판정 기준: 역대최저가 대비 이 범위 안이면 "최저가 근접"
NEAR_LOW_RATIO = 1.10
NEAR_LOW_WON = 2000

# 렌더링용 크롬 경로 (playwright install chromium 을 했다면 비워 둠)
CHROMIUM_PATH = os.getenv("DEALBOT_CHROMIUM", "")

# 카드뉴스 구성
HERO_SLIDES = int(os.getenv("DEALBOT_HERO_SLIDES", "5"))
LIST_SLIDE_ITEMS = 6
ACCOUNT_HANDLE = os.getenv("DEALBOT_HANDLE", "@your_handle")
BRAND = os.getenv("DEALBOT_BRAND", "주간 게임 세일")
THEME = os.getenv("DEALBOT_THEME", "poster")
