"""인스타그램 자동 게시 (Instagram Graph API 콘텐츠 게시).

GameSaleInsta/<날짜>/schedule.json 의 칸 중 게시 시각이 지났고 아직 안 올린 것을 올린다.
- 캐러셀: slide_NN.jpg 를 공개 URL(image_url)로 넘긴다. 표지 영상(slide_01.mp4)이 있으면 첫 장을 영상으로.
  API 는 JPEG 만, 최대 10장을 받는다.
- 릴스·스토리 영상: 재개 가능 업로드(rupload)로 파일을 직접 보낸다.
올린 기록은 published.json 에 남겨 같은 글을 두 번 올리지 않는다.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from . import config
from .render import KST

CAROUSEL_MAX = 10
CAPTION_MAX = 2200


def _day(date: str) -> Path:
    return config.DRAFTS_DIR / date


def _load(path: Path, empty):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty


def schedule(date: str) -> list[dict]:
    return _load(_day(date) / "schedule.json", [])


def published(date: str) -> dict:
    return _load(_day(date) / "published.json", {})


def _mark(date: str, folder: str, media_id: str) -> None:
    done = published(date)
    done[folder] = {"id": media_id, "at": datetime.now(KST).isoformat(timespec="minutes")}
    (_day(date) / "published.json").write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")


def due(date: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(KST)
    done = published(date)
    out = []
    for e in schedule(date):
        at = datetime.strptime(f"{date} {e['at']}", "%Y-%m-%d %H:%M").replace(tzinfo=KST)
        if e["dir"] not in done and at <= now <= at + timedelta(hours=config.PUBLISH_WINDOW_HOURS):
            out.append(e)
    return out


def plan(date: str, folder: str) -> dict:
    """폴더 하나를 어떤 형식으로 무엇을 올릴지 정한다."""
    d = _day(date) / folder
    cap = d / "caption.txt"
    if folder.startswith("reel") and not cap.exists():  # 릴스는 원본 게시물 캡션을 쓴다 (reel → report, reel-ending → ending)
        cap = _day(date) / (folder.split("-", 1)[1] if "-" in folder else "report") / "caption.txt"
    caption = cap.read_text(encoding="utf-8").strip() if cap.exists() else ""
    if folder.startswith("reel"):
        return {"type": "reel", "items": [d / "reel.mp4"], "caption": caption[:CAPTION_MAX]}
    slides = sorted(d.glob("slide_*.jpg"))
    if not slides:
        raise FileNotFoundError(f"{d} 에 slide_*.jpg 가 없음")
    if folder.startswith("story"):
        video = d / "slide_01.mp4"
        return {"type": "story", "items": [video if video.exists() else slides[0]], "caption": ""}
    if len(slides) > CAROUSEL_MAX:  # 앞에서부터 9장 + 마지막 장(편성표·안내)
        slides = slides[:CAROUSEL_MAX - 1] + slides[-1:]
    if (d / "slide_01.mp4").exists():
        slides[0] = d / "slide_01.mp4"
    return {"type": "carousel", "items": slides, "caption": caption[:CAPTION_MAX]}


class Graph:
    def __init__(self) -> None:
        self.base = f"https://{config.IG_GRAPH_HOST}/{config.IG_GRAPH_VERSION}"
        self.user = config.IG_USER_ID
        self.token = config.IG_ACCESS_TOKEN

    def _check(self, r: requests.Response) -> dict:
        if not r.ok:
            raise RuntimeError(f"{r.status_code} {r.text[:500]}")
        return r.json()

    def post(self, path: str, **data) -> dict:
        return self._check(requests.post(f"{self.base}/{path}", data={**data, "access_token": self.token}, timeout=60))

    def get(self, path: str, **params) -> dict:
        return self._check(requests.get(f"{self.base}/{path}", params={**params, "access_token": self.token}, timeout=30))

    def image(self, url: str, **fields) -> str:
        return self.post(f"{self.user}/media", image_url=url, **fields)["id"]

    def video(self, path: Path, **fields) -> str:
        res = self.post(f"{self.user}/media", upload_type="resumable", **fields)
        uri = res.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{config.IG_GRAPH_VERSION}/{res['id']}"
        body = path.read_bytes()
        self._check(requests.post(uri, data=body, timeout=300, headers={
            "Authorization": f"OAuth {self.token}", "offset": "0", "file_size": str(len(body))}))
        return res["id"]

    def wait(self, container: str, timeout: int = 600) -> None:
        end = time.time() + timeout
        while time.time() < end:
            status = self.get(container, fields="status_code,status")
            code = status.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"컨테이너 {container} 처리 실패: {status}")
            time.sleep(5)
        raise TimeoutError(f"컨테이너 {container} 처리 시간 초과")

    def publish(self, container: str) -> str:
        self.wait(container)
        return self.post(f"{self.user}/media_publish", creation_id=container)["id"]


def _url(date: str, folder: str, path: Path) -> str:
    if not config.MEDIA_BASE_URL:
        raise RuntimeError("DEALBOT_MEDIA_BASE 가 없어 이미지 공개 URL 을 만들 수 없음")
    return f"{config.MEDIA_BASE_URL}/{date}/{folder}/{path.name}"


def publish_folder(g: Graph, date: str, folder: str) -> str:
    p = plan(date, folder)
    if p["type"] == "reel":
        return g.publish(g.video(p["items"][0], media_type="REELS", caption=p["caption"], share_to_feed="true"))
    if p["type"] == "story":
        item = p["items"][0]
        c = g.video(item, media_type="STORIES") if item.suffix == ".mp4" else \
            g.image(_url(date, folder, item), media_type="STORIES")
        return g.publish(c)
    children = []
    for item in p["items"]:
        c = g.video(item, media_type="VIDEO", is_carousel_item="true") if item.suffix == ".mp4" else \
            g.image(_url(date, folder, item), is_carousel_item="true")
        g.wait(c)
        children.append(c)
    return g.publish(g.post(f"{g.user}/media", media_type="CAROUSEL", children=",".join(children),
                            caption=p["caption"])["id"])


def publish_due(date: str, only: list[str] | None = None, dry_run: bool = False) -> None:
    done = published(date)
    entries = [e for e in schedule(date) if e["dir"] in only and e["dir"] not in done] if only else due(date)
    if not entries:
        print(f"[publish] {date}: 지금 올릴 게시물 없음")
        return
    if not dry_run and not (config.IG_USER_ID and config.IG_ACCESS_TOKEN):
        raise SystemExit("[publish] IG_USER_ID / IG_ACCESS_TOKEN 이 없어 게시하지 않음")
    g, failed = Graph(), []
    for e in entries:
        p = plan(date, e["dir"])
        names = ", ".join(i.name for i in p["items"])
        if dry_run:
            print(f"[publish] (시험) {e['at']} {e['dir']}: {p['type']} {len(p['items'])}개 [{names}]")
            continue
        try:
            media_id = publish_folder(g, date, e["dir"])
        except Exception as exc:  # 한 칸이 실패해도 나머지는 올린다
            print(f"[publish] {e['dir']} 실패: {exc}")
            failed.append(e["dir"])
            continue
        _mark(date, e["dir"], media_id)
        print(f"[publish] {e['at']} {e['dir']} 게시 완료 (media {media_id})")
    if failed:
        raise SystemExit(f"[publish] 실패: {', '.join(failed)}")
