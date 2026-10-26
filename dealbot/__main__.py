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

from . import config, curate, history, instagram, motion, posts, render, state
from .models import Deal, FreeGame
from .sources import directg, epic, gog, playstation, steam, steam_events, stove


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
    for name, fn in (("gog", gog.fetch), ("directg", directg.fetch), ("stove", stove.fetch),
                     ("playstation", playstation.fetch)):
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
    history.record_reviews(con, deals)
    print("가격·리뷰 기록 저장 완료")


def prepare():
    deals, free, stores = collect()
    con = history.connect()
    history.record(con, deals)
    history.record_reviews(con, deals)
    history.apply_verdicts(con, deals)
    pc = [d for d in deals if d.store not in curate.CONSOLE_STORES]
    curate.compare_stores(pc)
    curate.compare_console([d for d in deals if d.store in curate.CONSOLE_STORES], pc)
    curate.attach_offers(deals)
    return deals, free, stores, con


POST_KINDS = [*posts.POSTS, "reel", "reel:ending", "reel:console", "story:upcoming-free"]


def build_ctx(kind: str, deals, free, picks, sample: bool) -> dict:
    """리포트/결산에 필요한 부가 정보: 스팀 일정, 기획전, 통계, 누적 장부."""
    ctx: dict = {}
    if kind not in ("report", "recap"):
        return ctx
    try:
        ctx["events"] = steam_events.calendar()
        ctx["spotlights"] = steam_events.spotlights()
    except Exception as e:
        print(f"[steam-events] 조회 실패: {e}")
        ctx["events"], ctx["spotlights"] = [], []
    if kind == "report":
        ctx["stats"] = posts.report_stats(deals, picks, free)
    if kind == "recap":
        rows = state.ledger()
        ctx["ledger_rows"], ctx["ledger"] = rows, state.ledger_summary(rows)
        ctx["events"] = posts.next_week_events(ctx["events"]) or ctx["events"][:3]
        ctx["week_count"] = len(state.used_keys())
    return ctx


def make_post(kind: str, deals, free, stores, con, out, args, sample: bool = False) -> str | None:
    """포맷 하나를 poster 디자인으로 렌더링: out/<폴더>/ 에 PNG(+MP4), caption.txt. 만든 폴더 이름을 돌려준다."""
    if kind.startswith("reel"):
        src = kind.split(":", 1)[1] if ":" in kind else "report"
        picks = posts.select(src, deals, 3)
        if len(picks) < 3:
            src, picks = "report", posts.select("report", deals, 3)
        render.decorate(picks)
        reel = render.render_reel(picks, out, sample=sample, source="weekly" if src == "report" else src)
        if args.gif:
            motion.to_gif(reel, width=270, fps=10)
        print(f"[reel] {reel}")
        return reel.parent.name
    if kind == "console" and not posts.console_ready(deals):
        alt = posts.console_fallback()
        print(f"[console] 콘솔 할인이 기준(인기 {posts.CONSOLE_MAX_RANK}위 안 {posts.CONSOLE_MIN_DISCOUNT}% 이상 "
              f"{posts.CONSOLE_MIN_GAMES}개)에 못 미쳐 '{alt}'로 대체")
        kind = alt
    if kind == "story:upcoming-free":
        games = [g for g in free if g.upcoming] or free
        post = {"key": "free", "kicker": "FREE NEXT", "headline": "", "layout": "poster"}
        slides = [{"kind": "story_free", "game": g, "post": post} for g in games[:1]]
        picks, name, ctx = [], "story-free", {}
    else:
        if kind == "free":
            if not free:
                print("[free] 무료 배포 게임이 없어 건너뜀")
                return None
            if all(g.kr_blocked for g in free if not g.upcoming):
                print("[free] 이번 주 무료 게임이 모두 한국 미제공 → 피드는 건너뛰고 스토리만 만듦")
                return make_post("story:upcoming-free", deals, free, stores, con, out, args, sample)
        exclude = set() if sample else state.used_keys()
        picks = [] if kind == "free" else posts.select(kind, deals, exclude=exclude)
        if kind not in ("story", "guide", "recap"):
            picks = posts.trim(kind, picks)
        if kind not in ("free", "recap") and not picks:
            print(f"[{kind}] 조건에 맞는 게임이 없어 건너뜀")
            return None
        for d in picks:
            if con is not None and not d.history:
                d.history = history.series(con, d)
        render.decorate(picks)
        ctx = build_ctx(kind, deals, free, picks, sample)
        if kind == "report" and picks:
            rows = state.ledger() + [{"week": state.week_id(), "title": picks[0].title, "store": picks[0].store,
                                      "price": picks[0].price, "regular": picks[0].regular}] if sample \
                else state.add_to_ledger(picks[0])
            ctx["ledger"] = state.ledger_summary(rows)
        slides = posts.build(kind, picks, free, stores, ctx)
        name = kind
    if not slides:
        print(f"[{kind}] 만들 슬라이드가 없어 건너뜀")
        return None
    r = render.render_theme(slides, "poster", out, name=name, motion_slides=args.motion,
                            sample=sample, affiliate=args.affiliate)
    text = posts.story_caption(picks[0]) if kind == "story" and picks else posts.caption(
        "free" if name == "story-free" else kind, picks, free, args.affiliate, ctx)
    (out / name / "caption.txt").write_text(text, encoding="utf-8")
    (out / name / "deals.json").write_text(json.dumps([d.to_dict() for d in picks], ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    if not sample and kind not in ("ending", "story", "guide", "recap"):
        state.mark_used(kind, picks)
    if args.gif:
        for mp4 in r["mp4"]:
            motion.to_gif(mp4)
    print(f"[{name}] 이미지 {len(r['png'])}장, 영상 {len(r['mp4'])}개 → {out / name}")
    return name


def cmd_post(args) -> None:
    deals, free, stores, con = prepare()
    out = config.OUTPUT_DIR / datetime.now(render.KST).strftime("%Y-%m-%d")
    for kind in args.kinds:
        make_post(kind, deals, free, stores, con, out, args)


def cmd_today(args) -> None:
    """오늘 편성표대로 만들고, 게시 시각과 폴더를 schedule.json 에 적는다 (instagram.py 가 읽어 올린다).
    이미 인스타에 올린 칸은 다시 만들지 않는다 (금요일 0시 에픽 무료 → 아침 재실행 등)."""
    today = datetime.now(render.KST).strftime("%Y-%m-%d")
    jobs = posts.jobs_for()
    if not any(kind == "story" for _, kind in jobs):
        jobs.append((posts.STORY_AT, "story"))  # 스토리는 매일
    if args.only:
        jobs = [(at, kind) for at, kind in jobs if kind in args.only]
    done = instagram.published(today)
    prev = {e["kind"]: e for e in instagram.schedule(today)}
    print("오늘 편성:", ", ".join(f"{at} {kind}" for at, kind in jobs))
    deals, free, stores, con = prepare()
    out = config.OUTPUT_DIR / today
    entries = [e for e in prev.values() if e["kind"] not in {k for _, k in jobs} or e.get("dir") in done]
    for at, kind in jobs:
        if prev.get(kind, {}).get("dir") in done:
            print(f"[{kind}] 이미 게시됨, 건너뜀")
            continue
        name = make_post(kind, deals, free, stores, con, out, args)
        if name:
            entries.append({"at": at, "kind": kind, "dir": name})
    entries.sort(key=lambda e: e["at"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "schedule.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_publish(args) -> None:
    instagram.publish_due(args.date or datetime.now(render.KST).strftime("%Y-%m-%d"),
                          only=args.dir, dry_run=args.dry_run)


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
                     ("post", cmd_post), ("today", cmd_today), ("publish", cmd_publish)):
        p = sub.add_parser(name)
        if name == "post":
            p.add_argument("kinds", nargs="+", choices=POST_KINDS)
        if name == "today":
            p.add_argument("--only", nargs="*", help="편성표 중 이 포맷만 (예: free)")
        if name == "publish":
            p.add_argument("--date", help="YYYY-MM-DD (기본: 오늘 KST)")
            p.add_argument("--dir", nargs="*", help="이 폴더만 지금 바로 올림 (예: report)")
            p.add_argument("--dry-run", action="store_true", help="API 호출 없이 무엇을 올릴지만 출력")
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
