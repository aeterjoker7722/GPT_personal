# dealbot: 게임 할인 인스타그램 카드뉴스 자동화

Steam, Epic, GOG, 다이렉트게임즈(+스토브 수동 입력)의 할인을 모아서 처리합니다.
**가격 추적과 최저가 판정, 한국어 지원, 스토어 간 가격 비교**를 붙인 뒤 다음을 만듭니다.

- 요일별 게시물: 주간 TOP, 역대 최저가, 마감 임박, 큐레이션, 무료 게임, 스토리, 계정 안내 (poster 디자인, PNG와 MP4)
- 스팀 트레일러와 공식 로고를 합성한 9:16 릴스 MP4
- 포맷별 캡션과 해시태그

- 주간 운영 계획(편성표): [docs/weekly_plan.md](docs/weekly_plan.md)
- 운영 전략: [docs/strategy.md](docs/strategy.md)
- 경쟁 조사: [docs/competitor_research.md](docs/competitor_research.md)
- 템플릿 시안과 모션: [docs/template_design.md](docs/template_design.md)

## 설치

```bash
pip install -r requirements.txt
playwright install chromium
# 모션/릴스를 만들려면 ffmpeg 도 필요 (macOS: brew install ffmpeg)
```

## 사용

```bash
python -m dealbot today --motion               # 오늘 요일 편성표대로 전부 생성 → output/YYYY-MM-DD/<포맷>/
python -m dealbot post weekly lowest           # 원하는 포맷만 (weekly, lowest, ending, under5k, korean, aaa, console, free, story, guide, reel, reel:ending, reel:console)
python -m dealbot post weekly --motion key     # 표지와 메인 카드를 MP4 로도
python -m dealbot post weekly --affiliate      # 제휴 링크를 쓸 때 [광고] 표기 추가
python -m dealbot run --theme receipt          # 다른 시안(editorial/receipt/ticker)으로 주간 TOP
python -m dealbot collect          # 가격 기록만 쌓기 (매일)
python -m dealbot sample --post weekly free     # 네트워크 없이 샘플 데이터로 미리보기
```

결과물의 `carousel.html`을 브라우저로 열면 PNG 렌더링 전에 확인할 수 있습니다.
**업로드 전에 가격, 링크, 한국어 지원 여부를 사람이 최종 검수하세요.**

## 데이터 소스

| 스토어 | 방식 | 비고 |
|---|---|---|
| Steam | 스토어 검색(할인, 인기순) + appdetails(cc=kr) | 원화. 평가는 영어 리뷰 기준. 한국어 지원은 상위 40개만 상세조회 |
| Epic | freeGamesPromotions | 무료 배포(현재, 다음 주)와 할인 |
| GOG | catalog API (판매량순, 할인 중) | 한국은 USD 결제라 `DEALBOT_USD_KRW` 환율로 환산 표시 |
| 다이렉트게임즈 | 할인 목록 HTML 파싱 | 평가 정보가 없어 같은 제목의 스팀 평가를 공유. 상업적으로 쓰기 전에 이용약관 확인 필요 |
| PlayStation (한국) | 스토어 웹의 GraphQL (베스트셀러순, 할인 중인 제품판) | 비공개 API라 스토어 개편 시 해시 갱신 필요. PS Plus 전용 할인 제외. 콘솔은 역대 최저가 판정 대신 PC 가격 비교와 절약액 표시 |
| 스토브 | `data/stove_manual.csv` 수동 입력 | 공개 API가 없고 해외 서버에서는 검색 결과가 비어 자동 수집 미구현. 예시: `data/stove_manual.example.csv` |

## 최저가 판정

1. `ITAD_API_KEY`(IsThereAnyDeal 무료 키)가 있으면 스팀 게임은 KR 기준 역대 최저가로 판정합니다. *키가 없어 이 경로는 실제 호출로 검증하지 못했습니다.*
2. 그 외에는 `data/price_history.sqlite`의 자체 기록을 씁니다. **7일 이상 쌓여야 판정이 켜지고**, 그전에는 "가격 추적 중"으로 표시됩니다.

`.github/workflows/collect-prices.yml`이 매일 가격을 수집해 sqlite를 커밋합니다.
`.github/workflows/daily-drafts.yml`은 매일 아침 오늘 게시물 초안을 만들어 Actions의 Artifacts로 올립니다(금요일 0시 10분에는 무료 게임만 따로).
두 워크플로 모두 스케줄 실행은 **기본 브랜치에 머지된 뒤부터** 동작합니다.

## 주요 설정 (환경변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DEALBOT_HANDLE` | `@your_handle` | 카드에 찍힐 계정명 |
| `DEALBOT_BRAND` | `주간 게임 세일` | 카드에 찍힐 브랜드명 |
| `DEALBOT_THEME` | `poster` | `run` 명령의 기본 시안 |
| `DEALBOT_MIN_DISCOUNT` | 50 | 최소 할인율 |
| `DEALBOT_MIN_REVIEW_PCT` / `_COUNT` | 75 / 500 | 최소 평가 비율과 리뷰 수 |
| `DEALBOT_HERO_SLIDES` | 5 | 메인 카드 장수 |
| `DEALBOT_USD_KRW` | 1400 | GOG 환산 환율 |
| `ITAD_API_KEY` | (없음) | 역대 최저가 판정 |
| `DEALBOT_CHROMIUM` | (없음) | 시스템 크롬 경로를 쓸 때 |
