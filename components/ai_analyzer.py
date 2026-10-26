"""AI(OpenAI) '이 페이지 기사 분위기' 판정 컴포넌트.

- 쓰는 곳: 오른쪽 '이 페이지 기사 분위기' 패널에만 사용 (기사 카드 표식·기사 분석은 감성사전)
- 모델: gpt-6-luna (환경변수 OPENAI_MODEL로 변경 가능)
- 키:   C:\\keydata\\gpt_key.py 의 open_Aikey (환경변수 OPENAI_KEY_FILE로 위치 변경, 저장소에는 넣지 않음)
- 토큰 절약:
    * 본문은 보내지 않고 검색 결과의 제목 + 요약만 보냄
    * 한 페이지 기사를 한 번의 호출로 판정 (기사마다 호출하지 않음)
    * 기사별 결과를 data/ai_cache.json에 저장해서, 이미 판정한 기사는 다시 보내지 않음
    * 출력은 기사 번호와 긍정 비율(정수)만
- 판정 이름(긍정/중립/부정)은 모델이 아니라 코드가 비율로 결정 (긍정 35~65% 중립)
- 키가 없거나 호출이 실패하면 AIError → 패널은 감성사전 판정으로 자동 대체
"""
import hashlib
import importlib.util
import json
import os
import re
import threading

import requests

API_URL = "https://api.openai.com/v1/responses"
MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
KEY_FILE = os.getenv("OPENAI_KEY_FILE", r"C:\keydata\gpt_key.py")
ENABLED = os.getenv("NEWS_AI", "1") != "0"           # NEWS_AI=0 이면 AI 판정을 끔
MAX_ITEMS = 100                                    # 한 번에 판정하는 최대 기사 수 (검색 최대 표시 건수)
ITEM_CHARS = 300                                   # 기사 하나당 보내는 제목+요약 최대 글자 수
PROMPT_VERSION = "page-v1"                         # 지시문을 바꾸면 올려서 캐시를 새로 만듦

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(BASE_DIR, "data", "ai_cache.json")

# 판정 기준: 긍정 비율이 35~65%면 중립, 65% 초과 긍정, 35% 미만 부정 (감성사전 판정과 같은 기준)
NEUTRAL_LOW, NEUTRAL_HIGH = 35, 65

SYSTEM = """당신은 뉴스 기사에 대한 긍정·부정 체크 모델입니다.
번호가 붙은 한국어 뉴스 기사 목록(제목과 요약)을 받아, 각 기사가 다루는 주된 대상(기업·인물·정책·행사 등)에 대해 기사 내용이 긍정적인 쪽에 얼마나 가까운지 0~100으로 체크합니다.

규칙:
- positive는 긍정 정도(0~100 정수)입니다. 부정 정도는 100 - positive로 봅니다.
- 성과·성장·호평·기대·해결이 중심이면 높게, 갈등·사고·손실·비판·우려가 중심이면 낮게 주세요.
- 단순 사실 전달·일정 안내처럼 평가가 거의 없거나, 좋은 점과 나쁜 점이 비슷하면 50에 가깝게 주세요.
- 목록의 모든 번호에 대해 하나씩 답하세요.
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["i", "positive"],
                "properties": {"i": {"type": "integer"}, "positive": {"type": "integer"}},
            },
        },
    },
}


def label_of(positive):
    """긍정 비율(%) → 긍정 / 중립 / 부정. 35~65%는 중립."""
    if positive > NEUTRAL_HIGH:
        return "긍정"
    if positive < NEUTRAL_LOW:
        return "부정"
    return "중립"


class AIError(Exception):
    """AI 판정을 쓸 수 없을 때 (키 없음, 호출 실패, 응답 형식 오류)."""


# ---------------------------------------------------------------- 키
_key = None


def _load_key():
    global _key
    if _key:
        return _key
    if os.getenv("OPENAI_API_KEY"):
        _key = os.environ["OPENAI_API_KEY"]
        return _key
    if not os.path.isfile(KEY_FILE):
        raise AIError(f"OpenAI 키 파일이 없습니다: {KEY_FILE}")
    spec = importlib.util.spec_from_file_location("gpt_key", KEY_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    key = getattr(mod, "open_Aikey", "")
    if not key:
        raise AIError(f"키 파일에 open_Aikey 변수가 없습니다: {KEY_FILE}")
    _key = key.strip()
    return _key


def available():
    """AI 판정을 쓸 수 있는지 (켜져 있고 키가 있음)."""
    if not ENABLED:
        return False
    try:
        _load_key()
        return True
    except AIError:
        return False


# ---------------------------------------------------------------- 캐시
_lock = threading.Lock()
_cache = None


def _load_cache():
    global _cache
    if _cache is None:
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                _cache = json.load(f)
        except (OSError, ValueError):
            _cache = {}
    return _cache


def _save_cache():
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass  # 캐시 저장 실패는 판정 자체에 영향 없음


def _clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _item_key(item):
    """기사 하나의 캐시 키 (같은 기사·같은 요약이면 다른 페이지에서도 재사용)."""
    raw = f"{PROMPT_VERSION}|{MODEL}|{item.get('link', '')}|{item.get('title', '')}|{item.get('description', '')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 호출
def _call_openai(numbered):
    """numbered: [(번호, 제목, 요약)] → {번호: 긍정 비율}"""
    lines = []
    for n, title, desc in numbered:
        text = f"{_clean(title)} / {_clean(desc)}"[:ITEM_CHARS]
        lines.append(f"[{n}] {text}")
    payload = {
        "model": MODEL,
        "input": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "\n".join(lines)},
        ],
        "text": {"format": {"type": "json_schema", "name": "page_mood", "schema": SCHEMA, "strict": True}},
        "reasoning": {"effort": "low"},
        "max_output_tokens": 600 + 20 * len(numbered),
    }
    headers = {"Authorization": f"Bearer {_load_key()}", "Content-Type": "application/json"}
    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 400 and "reasoning" in resp.text:   # 추론 강도를 지원하지 않는 모델
            payload.pop("reasoning")
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        raise AIError(f"OpenAI 호출 실패: {e}") from e
    except ValueError as e:
        raise AIError("OpenAI 응답을 읽지 못했습니다") from e

    # Responses API: output[] 안의 message → content[] 의 output_text
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    try:
                        out = json.loads(c["text"])
                    except ValueError as e:
                        raise AIError("AI 응답이 JSON 형식이 아닙니다") from e
                    return _verify(out, {n for n, _, _ in numbered})
    raise AIError("AI 응답에 결과가 없습니다")


# ---------------------------------------------------------------- 검증
def _verify(raw, wanted):
    """요청한 번호만 받고, 비율은 0~100으로 자름. 판정 이름은 코드가 정함."""
    got = {}
    for row in raw.get("items") or []:
        try:
            n, p = int(row["i"]), int(row["positive"])
        except (KeyError, TypeError, ValueError):
            continue
        if n in wanted:
            got[n] = max(0, min(100, p))
    return got


def _result(pos):
    pos = float(pos)
    return {"label": label_of(pos), "positive": pos, "negative": round(100 - pos, 1),
            "matched": 1, "model": MODEL, "source": "ai"}


def judge_page(items):
    """한 페이지 기사들의 분위기 판정 (호출 1번).

    items: [{"link", "title", "description"}, ...]  (검색 결과 순서)
    Returns: ({순서 번호: 판정}, 이번에 AI에 보낸 기사 수)
    빠진 번호는 AI가 답하지 않은 기사 → 화면이 감성사전 판정으로 채움.
    """
    if not ENABLED:
        raise AIError("AI 판정이 꺼져 있습니다 (NEWS_AI=0)")
    items = items[:MAX_ITEMS]
    results, todo = {}, []
    with _lock:
        cache = _load_cache()
        for n, it in enumerate(items):
            hit = cache.get(_item_key(it))
            if hit is not None:
                results[n] = _result(hit)
            elif (it.get("title") or it.get("description")):
                todo.append((n, it.get("title", ""), it.get("description", "")))
    if todo:
        got = _call_openai(todo)
        with _lock:
            cache = _load_cache()
            for n, pos in got.items():
                cache[_item_key(items[n])] = pos      # 캐시에는 긍정 비율 숫자만 저장
                results[n] = _result(pos)
            _save_cache()
    return results, len(todo)
