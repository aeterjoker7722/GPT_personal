# GameSaleInsta: 일주일 평가용 결과물

`daily-drafts` 워크플로가 매일 08:37 KST(금요일은 00:10 에픽 무료 게임 포함)에 만든 게시물을 날짜별로 여기에 쌓습니다.

```
GameSaleInsta/
  2026-10-26/          월: 스팀 리포트 + 릴스
    slide_01.png …     캐러셀 이미지 (1080×1350)
    slide_01.mp4       움직이는 슬라이드
    reel.mp4           릴스
    caption.txt        본문 캡션
  2026-10-27/          화: 대작 할인
  …
```

요일 편성: 월 리포트, 화 대작, 수 인디, 목 5천 원 이하/한국어(격주), 금 에픽 무료 + 마감 임박, 토 콘솔(할인이 충분할 때만), 일 주간 결산.

## 내 컴퓨터로 받기

처음 한 번 (GameSaleInsta 폴더가 비어 있어야 합니다):

```
git clone --filter=blob:none --sparse https://github.com/aeterjoker7722/GPT_personal.git GameSaleInsta
cd GameSaleInsta
git sparse-checkout set GameSaleInsta
```

그 다음부터는 그 폴더에서 매일 `git pull` 하면 새 날짜 폴더가 생깁니다. 결과물은 `GameSaleInsta/GameSaleInsta/<날짜>/` 에 있습니다.

## 평가 메모

[평가.md](평가.md)에 날짜별로 적어 두면 다음 수정 때 그대로 반영합니다.
