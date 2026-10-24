# dealbot: 게임 할인 인스타그램 카드뉴스 자동화

Steam, Epic, GOG, 다이렉트게임즈(+스토브 수동 입력)의 할인을 모아서 처리합니다.
**최저가 판정, 한국어 지원, 스토어 간 가격 비교**를 붙인 뒤 인스타그램 캐러셀 PNG와 캡션을 만듭니다.

- 운영 전략: [docs/strategy.md](docs/strategy.md)
- 경쟁 조사: [docs/competitor_research.md](docs/competitor_research.md)
- 템플릿 디자인: [docs/template_design.md](docs/template_design.md)

## 설치

```bash
pip install -r requirements.txt
playwright install chromium
```

## 사용

```bash
python -m dealbot run              # 수집 → 판정 → 선별 → output/YYYY-MM-DD/ 에 PNG, caption.txt, deals.json
python -m dealbot run --affiliate  # 제휴 링크를 쓸 때 [광고] 표기 추가
python -m dealbot collect          # 가격 기록만 쌓기 (매일)
python -m dealbot sample           # 네트워크 없이 샘플 데이터로 템플릿 미리보기
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
| 스토브 | `data/stove_manual.csv` 수동 입력 | 공개 API가 없고 해외 서버에서는 검색 결과가 비어 자동 수집 미구현. 예시: `data/stove_manual.example.csv` |

## 최저가 판정

1. `ITAD_API_KEY`(IsThereAnyDeal 무료 키)가 있으면 스팀 게임은 KR 기준 역대 최저가로 판정합니다. *키가 없어 이 경로는 실제 호출로 검증하지 못했습니다.*
2. 그 외에는 `data/price_history.sqlite`의 자체 기록을 씁니다. **7일 이상 쌓여야 판정이 켜지고**, 그전에는 "가격 추적 중"으로 표시됩니다.

`.github/workflows/collect-prices.yml`이 매일 가격을 수집해 sqlite를 커밋합니다. 스케줄 실행은 **기본 브랜치에 머지된 뒤부터** 동작합니다.

## 주요 설정 (환경변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DEALBOT_HANDLE` | `@your_handle` | 카드에 찍힐 계정명 |
| `DEALBOT_MIN_DISCOUNT` | 50 | 최소 할인율 |
| `DEALBOT_MIN_REVIEW_PCT` / `_COUNT` | 75 / 500 | 최소 평가 비율과 리뷰 수 |
| `DEALBOT_HERO_SLIDES` | 5 | 메인 카드 장수 |
| `DEALBOT_USD_KRW` | 1400 | GOG 환산 환율 |
| `ITAD_API_KEY` | (없음) | 역대 최저가 판정 |
| `DEALBOT_CHROMIUM` | (없음) | 시스템 크롬 경로를 쓸 때 |
