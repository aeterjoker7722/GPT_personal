"""사용법:
    python -m dealbot run            # 수집 → 판정 → 선별 → 카드뉴스 PNG + 캡션
    python -m dealbot run --no-png   # HTML 미리보기와 캡션만
    python -m dealbot collect        # 가격 기록만 쌓기 (매일 cron 용)
    python -m dealbot sample         # 네트워크 없이 샘플 데이터로 템플릿 확인
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from . import config, curate, history, render
from .models import Deal, FreeGame
from .sources import directg, epic, gog, steam, stove


def collect() -> tuple[list[Deal], list[FreeGame], list[str]]:
    deals: list[Deal] = []
    free: list[FreeGame] = []
    ok_stores = []

    def run(name, fn):
        try:
            result = fn()
            ok_stores.append(name)
            print(f"[{name}] 수집 완료")
            return result
        except Exception as e:
            print(f"[{name}] 수집 실패: {e}")
            return None

    st = run("steam", steam.fetch_specials)
    if st:
        # 상세조회는 선별 기준을 통과할 후보 위주로
        cands = [d for d in st if curate.passes(d)]
        steam.enrich_many(cands)
        deals += st
    ep = run("epic", epic.fetch)
    if ep:
        free, ep_deals = ep
        deals += ep_deals
    for name, fn in (("gog", gog.fetch), ("directg", directg.fetch), ("stove", stove.fetch)):
        got = run(name, fn)
        if got:
            deals += got
        elif name == "stove" and name in ok_stores:
            ok_stores.remove(name)  # 수동 CSV 가 비어 있으면 표지에서 뺀다
    print(f"총 할인 {len(deals)}개, 무료 {len(free)}개")
    return deals, free, ok_stores


def cmd_run(args) -> None:
    deals, free, stores = collect()
    con = history.connect()
    history.record(con, deals)
    history.apply_verdicts(con, deals)
    curate.compare_stores(deals)

    picks = curate.pick(deals, config.HERO_SLIDES + 3)
    picked = {d.key for d in picks}
    more = [d for d in curate.series(deals, "korean", 12) if d.key not in picked][:6]

    out = config.OUTPUT_DIR / datetime.now(render.KST).strftime("%Y-%m-%d")
    out.mkdir(parents=True, exist_ok=True)
    slides = render.build_slides(picks, more, free, stores)
    html_path = out / "carousel.html"
    html_path.write_text(render.render_html(slides, args.affiliate), encoding="utf-8")
    (out / "caption.txt").write_text(render.caption(picks, free, args.affiliate), encoding="utf-8")
    (out / "deals.json").write_text(json.dumps(
        {"picks": [d.to_dict() for d in picks], "more": [d.to_dict() for d in more],
         "free": [g.to_dict() for g in free]}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.no_png:
        pngs = render.render_png(html_path, out)
        print(f"PNG {len(pngs)}장 생성")
    print(f"결과: {out}")


def cmd_collect(_args) -> None:
    deals, _, _ = collect()
    con = history.connect()
    history.record(con, deals)
    print("가격 기록 저장 완료")


def cmd_sample(args) -> None:
    from .sample import sample_data

    picks, more, free = sample_data()
    out = config.OUTPUT_DIR / "sample"
    out.mkdir(parents=True, exist_ok=True)
    slides = render.build_slides(picks, more, free, ["steam", "epic", "gog", "directg", "stove"])
    html_path = out / "carousel.html"
    html_path.write_text(render.render_html(slides, args.affiliate), encoding="utf-8")
    (out / "caption.txt").write_text(render.caption(picks, free, args.affiliate), encoding="utf-8")
    if not args.no_png:
        render.render_png(html_path, out)
    print(f"결과: {out}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="dealbot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("run", cmd_run), ("collect", cmd_collect), ("sample", cmd_sample)):
        p = sub.add_parser(name)
        p.add_argument("--no-png", action="store_true")
        p.add_argument("--affiliate", action="store_true", help="제휴 링크 포함 시 광고 표기 추가")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
