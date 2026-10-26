# 인스타그램 자동 게시 설정

`daily-drafts` 가 매일 아침 만든 게시물을 `publish-instagram` 워크플로가 편성 시각에 올립니다.
아래 준비가 끝나고 `DEALBOT_AUTOPUBLISH` 를 켜기 전까지는 아무것도 올라가지 않습니다.

## 1. 인스타 계정 준비 (휴대폰 앱)

1. 인스타 계정을 만들고 **설정 → 계정 유형 및 도구 → 프로페셔널 계정으로 전환** (크리에이터 또는 비즈니스).
2. 페이스북 페이지를 하나 만들고, 인스타 **설정 → 계정 센터**에서 그 페이지와 연결합니다.

## 2. 토큰 발급 (developers.facebook.com)

1. [Meta for Developers](https://developers.facebook.com/) → 내 앱 → 앱 만들기 → 유형 "비즈니스".
2. 앱에 **Instagram** 제품을 추가합니다.
3. **그래프 API 탐색기**에서 그 앱을 고르고 권한 `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement` 를 체크해 사용자 토큰을 만듭니다.
4. 단기 토큰을 장기 토큰(60일)으로 바꿉니다:
   `GET /oauth/access_token?grant_type=fb_exchange_token&client_id={앱 ID}&client_secret={앱 시크릿}&fb_exchange_token={단기 토큰}`
   페이지 토큰(`GET /me/accounts`)은 장기 사용자 토큰으로 받으면 만료가 없습니다. 어느 쪽이든 게시에 쓸 수 있습니다.
5. 인스타 계정 ID 확인: `GET /me/accounts?fields=instagram_business_account{id,username}` → `instagram_business_account.id` (17841… 로 시작하는 숫자).

"Instagram 로그인" 방식(페이스북 페이지 없이)으로 토큰을 받았다면 Variables 에 `IG_GRAPH_HOST=graph.instagram.com` 을 추가하세요.

## 3. GitHub 저장소에 넣기

Settings → Secrets and variables → Actions

| 종류 | 이름 | 값 |
|---|---|---|
| Secret | `IG_USER_ID` | 인스타 계정 ID (숫자) |
| Secret | `IG_ACCESS_TOKEN` | 장기 토큰 |
| Variable | `DEALBOT_BRAND` | 슬라이드 상단 브랜드명 |
| Variable | `DEALBOT_HANDLE` | `@아이디` |
| Variable | `DEALBOT_AUTOPUBLISH` | `true` (자동 게시 켜기, 끄려면 지우거나 `false`) |

## 4. 시험해 보기

Actions → **publish-instagram** → Run workflow

- `dry_run` 체크(기본): 올리지 않고 오늘 무엇을 올릴지만 로그에 찍습니다.
- `dir` 에 `story` 를 넣고 `dry_run` 해제: 오늘 스토리 하나만 실제로 올려 봅니다. 스토리는 24시간 뒤 사라지니 첫 시험용으로 좋습니다.

## 동작 방식

- 편성(`GameSaleInsta/<날짜>/schedule.json`): 매일 09:00 스토리, 월 12:00 리포트·20:00 릴스, 화·수·목 19:00, 목 23:00 에픽 예고 스토리, 금 00:05 에픽 무료(00:30 게시)·18:00 마감 임박·20:00 릴스, 토 12:00 콘솔, 일 20:00 결산.
- GitHub 스케줄은 몇 분~수십 분 늦을 수 있습니다. 게시 시각 3시간 안이면 올리고, 그보다 늦으면 건너뜁니다.
- 올린 기록은 `published.json` 에 남아 같은 글을 두 번 올리지 않고, 아침에 다시 만들 때도 이미 올린 칸은 건드리지 않습니다.
- 캐러셀은 최대 10장(넘으면 앞 9장 + 마지막 장), 표지는 영상입니다. 이미지는 공개 저장소의 raw.githubusercontent.com 주소로 넘깁니다(저장소가 비공개가 되면 이미지 게시가 실패합니다).
- 하루 게시 한도(24시간 50건)에 한참 못 미칩니다.
- 장기 사용자 토큰은 60일마다 갱신해야 합니다. 만료되면 워크플로가 빨간색으로 실패합니다.
