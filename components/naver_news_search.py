"""네이버 뉴스 검색 API 컴포넌트.

웹 서버와 분리된 순수 API 호출 로직만 담당합니다.
"""
import html
import importlib.util
import os
import re
from email.utils import parsedate_to_datetime

import requests

from .press import press_name

API_URL = "https://openapi.naver.com/v1/search/news.json"

# 인증 정보는 프로젝트 밖의 key 파일에서 읽는다 (코드/git에 key를 남기지 않기 위함)
# key 파일 위치는 환경변수 NAVER_KEY_FILE로 바꿀 수 있다.
KEY_FILE = os.getenv("NAVER_KEY_FILE", r"C:\keydata\naver.py")


def _load_keys(path):
    """key 파일(파이썬)에서 CLIENT_ID, CLIENT_SECRET을 읽는다."""
    if not os.path.isfile(path):
        raise RuntimeError(f"key 파일을 찾을 수 없습니다: {path}")
    spec = importlib.util.spec_from_file_location("naver_keys", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.CLIENT_ID, module.CLIENT_SECRET
    except AttributeError as e:
        raise RuntimeError(f"key 파일에 CLIENT_ID / CLIENT_SECRET이 없습니다: {path}") from e


CLIENT_ID, CLIENT_SECRET = _load_keys(KEY_FILE)

VALID_SORTS = {"sim", "date"}

_TAG_RE = re.compile(r"<[^>]+>")


class NaverSearchError(Exception):
    """네이버 API 호출 실패 시 발생하는 예외."""


def _clamp(value, low, high):
    return max(low, min(high, int(value)))


def _clean(text):
    """<b> 등 HTML 태그 제거 + &quot; 같은 엔티티 복원."""
    return html.unescape(_TAG_RE.sub("", text or ""))


def _format_date(pub_date):
    """'Mon, 26 Oct 2026 09:30:00 +0900' -> '2026-10-26 09:30'"""
    try:
        return parsedate_to_datetime(pub_date).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return pub_date or ""


def search_news(query, display=10, start=1, sort="sim", timeout=10):
    """네이버 뉴스 검색을 수행하고 정리된 결과를 반환합니다.

    Args:
        query:   검색어
        display: 결과 수 (1~100)
        start:   시작 위치 (1~1000)
        sort:    sim(정확도) 또는 date(날짜)

    Returns:
        {"total": int, "items": [{"title", "description", "link",
                                  "originallink", "pub_date"}, ...]}
    """
    if not query or not query.strip():
        raise ValueError("검색어(query)가 비어 있습니다.")

    params = {
        "query": query.strip(),
        "display": _clamp(display, 1, 100),
        "start": _clamp(start, 1, 1000),
        "sort": sort if sort in VALID_SORTS else "sim",
    }
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET,
    }

    try:
        response = requests.get(API_URL, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        raise NaverSearchError(f"요청 실패: {e}") from e

    items = [
        {
            "title": _clean(item.get("title")),
            "description": _clean(item.get("description")),
            "link": item.get("link", ""),                  # 네이버 뉴스 링크
            "originallink": item.get("originallink", ""),  # 언론사 원문 링크
            "press": press_name(item.get("originallink") or item.get("link")),  # 출처 언론사
            "pub_date": _format_date(item.get("pubDate")),
        }
        for item in data.get("items", [])
    ]
    return {"total": data.get("total", 0), "items": items}
