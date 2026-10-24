"""재시도와 User-Agent 가 설정된 공용 HTTP 세션."""
import time

import requests

from . import config

_session = None


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": config.USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})
    return _session


def get(url: str, *, params=None, retries: int = 3, **kw) -> requests.Response:
    last = None
    for attempt in range(retries):
        try:
            r = session().get(url, params=params, timeout=config.HTTP_TIMEOUT, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} for {url}")
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(2 ** attempt * 2)
    raise last


def post(url: str, *, params=None, json=None, retries: int = 3) -> requests.Response:
    last = None
    for attempt in range(retries):
        try:
            r = session().post(url, params=params, json=json, timeout=config.HTTP_TIMEOUT)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(2 ** attempt * 2)
    raise last
