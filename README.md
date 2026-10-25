# dealbot: 게임 할인 인스타그램 카드뉴스 자동화

Steam, Epic, GOG, 다이렉트게임즈(+스토브 수동 입력)의 할인을 모아서 처리합니다.
**한국어 지원, 전세계·한국 평가, 스토어·플랫폼 간 가격 비교, 할인 종료 시각**을 붙인 뒤 다음을 만듭니다.

- 요일별 게시물: 월 스팀 리포트, 화 대작, 수 인디, 목 5천 원 이하·한국어, 금 에픽 무료·마감 임박, 토 콘솔(조건부), 일 주간 결산, 매일 스토리 (poster 디자인, 요일마다 다른 배치, PNG와 MP4)
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
python -m dealbot post weekly lowest           # 원하는 포맷만 (report, aaa, indie, under5k, korean, free, ending, console, recap, story, guide, reel, reel:ending, reel:console)
python -m dealbot post weekly --motion key     # 표지와 메인 카드를 MP4 로도
python -m dealbot post weekly --affiliate      # 제휴 링크를 쓸 때 [광고] 표기 추가
python -m dealbot run --theme receipt          # 다른 시안(editorial/receipt/ticker)으로 주간 TOP
python -m dealbot collect          # 가격 기록만 쌓기 (매일)
python -m dealbot sample --post report free    # 네트워크 없이 샘플 데이터로 미리보기 (인디 등 일부 포맷은 샘플에 데이터가 없어 비어 나옴)
```

결과물의 `carousel.html`을 브라우저로 열면 PNG 렌더링 전에 확인할 수 있습니다.
**업로드 전에 가격, 링크, 한국어 지원 여부를 사람이 최종 검수하세요.**

## 데이터 소스

| 스토어 | 방식 | 비고 |
|---|---|---|
| Steam | 스토어 검색(할인, 인기순) + IStoreBrowseService(KR) | 원화, 할인 종료 시각, 전세계·한국어 리뷰, 한국어 지원, 인디 태그, 키아트·로고·트레일러. 상위 100개 상세조회 |
| Steam 일정 | Steamworks 공식 'Upcoming Steam Events' + 스팀 메인 스포트라이트 | 계절 세일, 넥스트 페스트, 테마 페스티벌, 진행 중인 프랜차이즈 기획전 |
| Epic | freeGamesPromotions | 무료 배포(현재, 다음 주)와 할인. 국가 차단 목록에 KR이 있으면 "한국 계정 미제공" 표시 |
| GOG | catalog API (판매량순, 할인 중) | 한국은 USD 결제라 `DEALBOT_USD_KRW` 환율로 환산 표시 |
| 다이렉트게임즈 | 할인 목록 HTML 파싱 | 평가 정보가 없어 같은 제목의 스팀 평가를 공유. 상업적으로 쓰기 전에 이용약관 확인 필요 |
| PlayStation (한국) | 스토어 웹의 GraphQL (베스트셀러순, 할인 중인 제품판) | 비공개 API라 스토어 개편 시 해시 갱신 필요. PS Plus 전용 할인 제외. 콘솔은 역대 최저가 판정 대신 PC 가격 비교와 절약액 표시 |
| 스토브 | `data/stove_manual.csv` 수동 입력 | 공개 API가 없고 해외 서버에서는 검색 결과가 비어 자동 수집 미구현. 예시: `data/stove_manual.example.csv` |

## 최저가 판정 (기본: 표시하지 않음)

판정은 게임을 고르는 점수에만 쓰고, 카드·캡션에는 **기본으로 보여 주지 않습니다**(틀리면 역풍이 커서). `DEALBOT_SHOW_VERDICT=1`이면 표시하며, 이때는 ITAD 키를 함께 쓰는 것을 권장합니다.

1. `ITAD_API_KEY`(IsThereAnyDeal 무료 키)가 있으면 스팀 게임은 KR 기준 역대 최저가로 판정합니다. *키가 없어 이 경로는 실제 호출로 검증하지 못했습니다.*
2. 그 외에는 `data/price_history.sqlite`의 자체 기록을 씁니다(PC 7일, 콘솔 90일 이상 쌓여야 판정).

## 운영 상태 파일

- `data/week_state.json`: 이번 주에 이미 소개한 게임. 요일별 게시물이 같은 게임을 반복하지 않게 합니다.
- `data/ledger.json`: "주간 1위만 매주 샀다면" 누적 장부(일요일 결산).
- `data/price_history.sqlite`: 가격과 리뷰(전세계·한국어) 일별 기록.
- `data/steam_events_manual.csv`(선택): 스팀 일정 보충. 예시: `data/steam_events_manual.example.csv`

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
| `DEALBOT_SHOW_VERDICT` | 0 | 1이면 판정("역대 최저가 (ITAD)")을 카드·캡션에 표시 |
| `DEALBOT_CHROMIUM` | (없음) | 시스템 크롬 경로를 쓸 때 |
