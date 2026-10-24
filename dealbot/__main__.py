"""사용법:
    python -m dealbot today                       # 오늘 편성표(요일별)대로 게시물 전부 생성
    python -m dealbot post weekly lowest          # 원하는 포맷만 생성 (weekly/lowest/ending/under5k/korean/aaa/free/story/reel)
    python -m dealbot post weekly --motion        # 표지는 MP4 도 (--motion key: 메인 카드까지)
    python -m dealbot collect                     # 가격 기록만 쌓기 (매일 cron 용)
    python -m dealbot sample --post weekly        # 네트워크 없이 샘플 데이터로 확인
    python -m dealbot run --theme receipt         # (구) 다른 시안으로 주간 TOP 만들기
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from . import config, curate, history, motion, posts, render
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

    for d in picks + more:
        d.history = history.series(con, d)
    out = config.OUTPUT_DIR / datetime.now(render.KST).strftime("%Y-%m-%d")
    publish(out, picks, more, free, stores, args)


def publish(out, picks, more, free, stores, args, sample=False) -> None:
    out.mkdir(parents=True, exist_ok=True)
    render.decorate(picks + more)
    slides = render.build_slides(picks, more, free, stores)
    (out / "caption.txt").write_text(render.caption(picks, free, args.affiliate), encoding="utf-8")
    (out / "deals.json").write_text(json.dumps(
        {"picks": [d.to_dict() for d in picks], "more": [d.to_dict() for d in more],
         "free": [g.to_dict() for g in free]}, ensure_ascii=False, indent=2), encoding="utf-8")
    themes = list(render.THEMES) if args.theme == "all" else [args.theme]
    for theme in themes:
        r = render.render_theme(slides, theme, out, motion_slides=args.motion, sample=sample, affiliate=args.affiliate)
        if args.gif:
            for mp4 in r["mp4"]:
                motion.to_gif(mp4)
        print(f"[{theme}] 이미지 {len(r['png'])}장, 영상 {len(r['mp4'])}개")
    if args.reel:
        reel = render.render_reel(picks, out, sample=sample, source=src if len(posts.select(src, deals, 3)) >= 3 else "weekly")
        if args.gif:
            motion.to_gif(reel, width=270, fps=10)
        print(f"[reel] {reel}")
    print(f"결과: {out}")


def cmd_collect(_args) -> None:
    deals, _, _ = collect()
    con = history.connect()
    history.record(con, deals)
    print("가격 기록 저장 완료")


def prepare():
    deals, free, stores = collect()
    con = history.connect()
    history.record(con, deals)
    history.apply_verdicts(con, deals)
    curate.compare_stores(deals)
    return deals, free, stores, con


POST_KINDS = [*posts.POSTS, "reel", "reel:ending", "story:upcoming-free"]


def make_post(kind: str, deals, free, stores, con, out, args, sample: bool = False) -> None:
    """포맷 하나를 poster 디자인으로 렌더링: out/<kind>/ 에 PNG(+MP4), caption.txt."""
    if kind.startswith("reel"):
        src = kind.split(":", 1)[1] if ":" in kind else "weekly"
        picks = posts.select(src, deals, 3)
        if len(picks) < 3:
            picks = posts.select("weekly", deals, 3)
        render.decorate(picks)
        reel = render.render_reel(picks, out, sample=sample, source=src if len(posts.select(src, deals, 3)) >= 3 else "weekly")
        if args.gif:
            motion.to_gif(reel, width=270, fps=10)
        print(f"[reel] {reel}")
        return
    if kind == "story:upcoming-free":
        games = [g for g in free if g.upcoming] or free
        post = {"key": "free", "kicker": "FREE NEXT", "headline": ""}
        slides = [{"kind": "story_free", "game": g, "post": post} for g in games[:1]]
        picks, name = [], "story-free"
    else:
        if kind == "free" and not free:
            print("[free] 무료 배포 게임이 없어 건너뜀")
            return
        picks = posts.select(kind, deals) if kind != "free" else []
        if kind not in ("free",) and not picks:
            print(f"[{kind}] 조건에 맞는 게임이 없어 건너뜀")
            return
        for d in picks:
            if con is not None and not d.history:
                d.history = history.series(con, d)
        render.decorate(picks)
        slides = posts.build(kind, picks, free, stores)
        name = kind
    if not slides:
        print(f"[{kind}] 만들 슬라이드가 없어 건너뜀")
        return
    r = render.render_theme(slides, "poster", out, name=name, motion_slides=args.motion,
                            sample=sample, affiliate=args.affiliate)
    text = posts.story_caption(picks[0]) if kind == "story" and picks else posts.caption(
        "free" if name == "story-free" else kind, picks, free, args.affiliate)
    (out / name / "caption.txt").write_text(text, encoding="utf-8")
    (out / name / "deals.json").write_text(json.dumps([d.to_dict() for d in picks], ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    if args.gif:
        for mp4 in r["mp4"]:
            motion.to_gif(mp4)
    print(f"[{name}] 이미지 {len(r['png'])}장, 영상 {len(r['mp4'])}개 → {out / name}")


def cmd_post(args) -> None:
    deals, free, stores, con = prepare()
    out = config.OUTPUT_DIR / datetime.now(render.KST).strftime("%Y-%m-%d")
    for kind in args.kinds:
        make_post(kind, deals, free, stores, con, out, args)


def cmd_today(args) -> None:
    jobs = posts.jobs_for()
    print("오늘 편성:", ", ".join(f"{at} {kind}" for at, kind in jobs))
    deals, free, stores, con = prepare()
    out = config.OUTPUT_DIR / datetime.now(render.KST).strftime("%Y-%m-%d")
    kinds = [kind for _, kind in jobs]
    if "story" not in kinds:
        kinds.append("story")  # 스토리는 매일
    for kind in kinds:
        make_post(kind, deals, free, stores, con, out, args)
    (out / "schedule.txt").write_text("\n".join(f"{at}  {kind}" for at, kind in jobs), encoding="utf-8")


def cmd_sample(args) -> None:
    from .sample import sample_data

    picks, more, free = sample_data()
    out = config.OUTPUT_DIR / "sample"
    stores = ["steam", "epic", "gog", "directg", "stove"]
    if args.theme != "poster" or not args.post:
        publish(out, picks, more, free, stores, args, sample=True)
        return
    deals = picks + more
    for kind in args.post:
        make_post(kind, deals, free, stores, None, out, args, sample=True)


def main() -> None:
    ap = argparse.ArgumentParser(prog="dealbot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("run", cmd_run), ("collect", cmd_collect), ("sample", cmd_sample),
                     ("post", cmd_post), ("today", cmd_today)):
        p = sub.add_parser(name)
        if name == "post":
            p.add_argument("kinds", nargs="+", choices=POST_KINDS)
        if name == "sample":
            p.add_argument("--post", nargs="*", choices=POST_KINDS, help="poster 포맷으로 샘플 생성")
        p.add_argument("--theme", default=config.THEME, choices=[*render.THEMES, "all"])
        p.add_argument("--motion", nargs="?", const="cover", default="", choices=["cover", "key", "all"],
                       help="슬라이드를 MP4 로도 출력 (cover: 표지만, key: 표지+메인카드, all: 전부)")
        p.add_argument("--gif", action="store_true", help="MP4 마다 미리보기 GIF 도 생성")
        p.add_argument("--reel", action="store_true", help="트레일러를 쓴 9:16 릴스 MP4 생성")
        p.add_argument("--affiliate", action="store_true", help="제휴 링크 포함 시 광고 표기 추가")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
