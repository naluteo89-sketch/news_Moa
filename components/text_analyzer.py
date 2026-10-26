"""파이썬 텍스트 분석 컴포넌트: 긍정/부정 비율 + 핵심 키워드.

- 감성 분석: KNU 한국어 감성사전(SentiWord_info.json) 기반
  (없으면 첫 실행 때 data/ 폴더로 자동 다운로드)
- 형태소 분석: kiwipiepy (설치돼 있지 않으면 간이 분석기로 대체)
"""
import json
import math
import os
import re
from collections import Counter

import requests

try:  # pip install kiwipiepy
    from kiwipiepy import Kiwi
    _kiwi = Kiwi()
except Exception:  # 미설치 또는 설치 실패 시 간이 분석기 사용
    _kiwi = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEXICON_PATH = os.getenv(
    "KNU_LEXICON_PATH", os.path.join(BASE_DIR, "data", "SentiWord_info.json")
)
LEXICON_URL = (
    "https://raw.githubusercontent.com/park1200656/KnuSentiLex/master/data/SentiWord_info.json"
)

# 기사에서 흔하지만 의미 없는 단어
STOPWORDS = {
    "기자", "뉴스", "연합뉴스", "뉴시스", "뉴스1", "무단", "전재", "재배포", "금지", "저작권",
    "오늘", "어제", "내일", "이번", "지난", "올해", "작년", "최근", "현재", "관련", "통해",
    "위해", "대해", "가운데", "이날", "당시", "경우", "정도", "이상", "이하", "때문", "사진",
    "제공", "기사", "보도", "앵커", "리포트", "그것", "우리", "모두", "바로", "다른", "모든",
}
# 간이 분석기용 조사/어미 (긴 것부터 제거)
_JOSA = sorted(
    ["으로서", "으로써", "에서는", "에게서", "이라는", "라는", "에서", "에게", "으로", "까지",
     "부터", "보다", "처럼", "만큼", "이다", "였다", "했다", "하는", "하고", "이며", "이고",
     "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "만", "께"],
    key=len, reverse=True,
)
_NEGATORS_AFTER = {"않", "못하", "아니"}
_NEGATORS_BEFORE = {"안", "못"}

_lexicon = None


# ---------------------------------------------------------------- 감성사전
def _download_lexicon(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    resp = requests.get(LEXICON_URL, timeout=30)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)


def load_lexicon(path=None):
    """{단어: 극성(-2~2)} 사전을 반환 (한 번만 읽고 재사용)."""
    global _lexicon
    if _lexicon is not None and path is None:
        return _lexicon
    path = path or LEXICON_PATH
    if not os.path.isfile(path):
        try:
            _download_lexicon(path)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(
                f"감성사전을 내려받지 못했습니다. {LEXICON_URL} 파일을 {path} 에 직접 넣어 주세요. ({e})"
            ) from e
    with open(path, encoding="utf-8-sig") as f:
        entries = json.load(f)
    lexicon = {}
    for e in entries:
        word = str(e.get("word", "")).strip()
        try:
            polarity = int(e.get("polarity", 0))
        except (TypeError, ValueError):
            continue
        if word and polarity:
            lexicon[word] = polarity
    _lexicon = lexicon
    return lexicon


# ---------------------------------------------------------------- 형태소 분석
def tokenize(text):
    """[(형태, 품사)] 리스트. 동사/형용사는 '~다' 기본형으로 돌려준다."""
    if _kiwi is not None:
        tokens = []
        for t in _kiwi.tokenize(text):
            tag = t.tag
            form = t.form + "다" if tag in ("VV", "VA", "VV-I", "VA-I", "VV-R", "VA-R") else t.form
            tokens.append((form, tag.split("-")[0]))
        return tokens

    # 간이 분석기: 한글/영문 단어를 자르고 끝의 조사만 떼어냄
    tokens = []
    for word in re.findall(r"[가-힣]+|[A-Za-z]{2,}", text):
        if word in _NEGATORS_BEFORE:
            tokens.append((word, "MAG"))
            continue
        stem = word
        for j in _JOSA:
            if stem.endswith(j) and len(stem) - len(j) >= 2:
                stem = stem[: -len(j)]
                break
        if stem.isascii():
            tag = "SL"
        elif stem.endswith("다"):  # '있다', '밝혔다' 등 서술어는 키워드에서 제외
            tag = "VV"
        else:
            tag = "NNG"
        tokens.append((stem, tag))
    return tokens


def _lookup(form, tag, lexicon):
    """토큰의 감성 극성. 사전에 없으면 0."""
    if form in lexicon:
        return lexicon[form]
    if tag == "XR" and form + "하다" in lexicon:  # 행복(XR) -> 행복하다
        return lexicon[form + "하다"]
    if _kiwi is None:  # 간이 분석기: '좋았다' -> '좋', '좋다' 식으로 앞부분 일치 시도
        for n in range(len(form) - 1, 0, -1):
            stem = form[:n]
            for cand in (stem + "다", stem + "하다", stem if n >= 2 else None):
                if cand and cand in lexicon:
                    return lexicon[cand]
    return 0


# ---------------------------------------------------------------- 감성 분석
def analyze_sentiment(text, lexicon=None):
    """긍정/부정/중립 비율(%)과 근거 단어를 반환."""
    lexicon = lexicon or load_lexicon()
    tokens = tokenize(text)
    pos_score = neg_score = 0
    pos_words, neg_words = Counter(), Counter()

    for i, (form, tag) in enumerate(tokens):
        polarity = _lookup(form, tag, lexicon)
        if not polarity:
            continue
        # 부정어 처리: '좋지 않다', '안 좋다' -> 극성 반전
        after = {f[:-1] if f.endswith("다") else f for f, _ in tokens[i + 1:i + 3]}
        before = tokens[i - 1][0] if i > 0 else ""
        if after & _NEGATORS_AFTER or before in _NEGATORS_BEFORE:
            polarity = -polarity
        word = form
        if polarity > 0:
            pos_score += polarity
            pos_words[word] += 1
        else:
            neg_score += -polarity
            neg_words[word] += 1

    total = pos_score + neg_score
    if total == 0:
        positive = negative = 0.0
        label = "중립"
    else:
        positive = round(pos_score / total * 100, 1)
        negative = round(100 - positive, 1)
        # AI 판정과 같은 기준: 긍정 35~65%는 중립, 65% 초과 긍정, 35% 미만 부정
        label = "긍정" if positive > 65 else "부정" if positive < 35 else "중립"

    return {
        "label": label,
        "positive": positive,
        "negative": negative,
        "pos_words": [w for w, _ in pos_words.most_common(10)],
        "neg_words": [w for w, _ in neg_words.most_common(10)],
        "matched": sum(pos_words.values()) + sum(neg_words.values()),
    }


# ---------------------------------------------------------------- 키워드
def extract_nouns(text):
    nouns = []
    for form, tag in tokenize(text):
        if tag in ("NNG", "NNP", "SL") and len(form) >= 2 and form not in STOPWORDS:
            nouns.append(form)
    return nouns


def extract_keywords(text, top_n=10):
    """기사 하나의 핵심 키워드 (빈도순)."""
    return [{"word": w, "count": c} for w, c in Counter(extract_nouns(text)).most_common(top_n)]


def page_keywords(texts, exclude="", top_n=15):
    """검색 결과 한 페이지(제목+요약들)에서 많이 나온 단어.

    여러 기사에 나올수록 위로 (기사 수 -> 전체 횟수 순).
    exclude: 검색어 - 모든 기사에 들어가므로 목록에서 뺀다.
    """
    skip = set(extract_nouns(exclude)) | {w for w in re.findall(r"[가-힣A-Za-z0-9]+", exclude)}
    docs = [Counter(extract_nouns(t)) for t in texts if t]
    df, total = Counter(), Counter()
    for d in docs:
        for w, c in d.items():
            if w not in skip:
                df[w] += 1
                total[w] += c
    ranked = sorted(df, key=lambda w: (-df[w], -total[w], w))
    return [{"word": w, "docs": df[w], "count": total[w]} for w in ranked[:top_n]]


def visible_word_count(words, cap=4, min_gap=2):
    """처음에 보여줄 단어 수.

    상위 단어들의 기사 수가 별 차이 없으면(1위와 5위 차이가 min_gap 미만) cap(4)개만 보여주고,
    차이가 뚜렷하면 전부 보여준다.
    """
    if len(words) <= cap:
        return len(words)
    if words[0]["docs"] - words[cap]["docs"] < min_gap:
        return cap
    return len(words)


def aggregate_keywords(texts, top_n=20):
    """여러 기사 전체의 핵심 키워드 (TF-IDF 합산 점수순).

    한 기사에만 몰려 나온 단어보다 여러 기사에 고르게 나온 단어가 아니라,
    '기사 안에서 자주 + 전체에서 너무 흔하지 않은' 단어를 위로 올린다.
    """
    docs = [Counter(extract_nouns(t)) for t in texts if t]
    if not docs:
        return []
    n = len(docs)
    df = Counter(w for d in docs for w in d)
    scores = Counter()
    for d in docs:
        length = sum(d.values()) or 1
        for w, c in d.items():
            scores[w] += (c / length) * (math.log((1 + n) / (1 + df[w])) + 1)
    return [
        {"word": w, "score": round(s, 4), "docs": df[w]}
        for w, s in scores.most_common(top_n)
    ]


# ---------------------------------------------------------------- 문장 / 핵심 문장
def split_paragraphs(text):
    """본문 -> [[문장, ...], ...] (문단별 문장 리스트)."""
    paragraphs = []
    for para in (p.strip() for p in text.split("\n")):
        if not para:
            continue
        if _kiwi is not None:
            sents = [s.text.strip() for s in _kiwi.split_into_sents(para)]
        else:
            sents = re.split(r"(?<=[.!?])\s+", para)
        sents = [s for s in sents if s]
        if sents:
            paragraphs.append(sents)
    return paragraphs


def _match_rate(sentence_nouns, ref_nouns):
    """기준(제목/부제목) 명사 중 문장에 포함된 비율(%)."""
    if not ref_nouns:
        return 0.0
    return round(len(sentence_nouns & ref_nouns) / len(ref_nouns) * 100, 1)


def key_sentences(sentences, title, subtitle="", top_n=5):
    """제목·부제목과 가장 많이 겹치는 문장.

    Args:
        sentences: [(문장번호, 문장)]
    Returns:
        [{"index", "text", "title_match", "subtitle_match", "score"}] (score 높은 순)
    """
    title_nouns = set(extract_nouns(title))
    sub_nouns = set(extract_nouns(subtitle))
    results = []
    for idx, sent in sentences:
        nouns = set(extract_nouns(sent))
        t = _match_rate(nouns, title_nouns)
        s = _match_rate(nouns, sub_nouns)
        score = round(t * 0.6 + s * 0.4, 1) if sub_nouns else t
        if score > 0:
            results.append({"index": idx, "text": sent, "title_match": t,
                            "subtitle_match": s, "score": score})
    results.sort(key=lambda r: (-r["score"], r["index"]))
    return results[:top_n]


def analyze_article(title, body, subtitle="", top_n=30):
    """기사 하나 전체 분석: 문단/문장, 감성, 키워드, 핵심 문장."""
    paragraphs = split_paragraphs(body)
    numbered, idx = [], 0
    for para in paragraphs:
        row = []
        for sent in para:
            row.append({"index": idx, "text": sent})
            idx += 1
        numbered.append(row)
    flat = [(s["index"], s["text"]) for para in numbered for s in para]

    return {
        "paragraphs": numbered,
        "sentiment": analyze_sentiment(body),
        "keywords": extract_keywords(body, top_n),
        "key_sentences": key_sentences(flat, title, subtitle),
        "tokenizer": "kiwipiepy" if _kiwi is not None else "simple",
    }


def analyze_text(text, top_n=10):
    """기사 하나: 감성 + 키워드."""
    return {
        "sentiment": analyze_sentiment(text),
        "keywords": extract_keywords(text, top_n),
        "tokenizer": "kiwipiepy" if _kiwi is not None else "simple",
    }
