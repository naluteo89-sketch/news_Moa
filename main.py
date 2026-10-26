"""메인 웹 서버 (Flask) - 네이버 뉴스 검색.

실행:  python main.py  ->  http://127.0.0.1:5000
"""
import os

from flask import Flask, jsonify, render_template, request

from components import (
    ArticleFetchError,
    NaverSearchError,
    analyze_article,
    analyze_sentiment,
    fetch_article,
    page_keywords,
    search_news,
    visible_word_count,
)

app = Flask(__name__)

# 메인 화면 설정: 처음에 보여줄 검색어와, 상단 고정 검색어(핀)의 기본값
# (핀은 화면에서 × / + 로 바꾸면 그 브라우저에 기억됨)
HOME_QUERY = "축제"
SUGGESTIONS = ["야구", "경제", "드라마"]


def _get_search_args():
    return {
        "query": request.args.get("query", "").strip(),
        "display": request.args.get("display", 10, type=int),
        "start": request.args.get("start", 1, type=int),
        "sort": request.args.get("sort", "sim"),
    }


@app.route("/")
def index():
    """검색 페이지 (HTML).

    검색어 없이 처음 들어오면(메인) HOME_QUERY 결과를 보여주고, 추천 검색어를 함께 띄운다.
    """
    args = _get_search_args()
    is_home = "query" not in request.args
    if is_home:
        args["query"] = HOME_QUERY
    result, error, words, cloud = None, None, [], []
    if args["query"]:
        try:
            result = search_news(**args)
            # 이 페이지 기사들의 제목+요약에서 많이 나온 단어 (검색어 제외)
            texts = [f"{it['title']} {it['description']}" for it in result["items"]]
            words = page_keywords(texts, exclude=args["query"])
            cloud = page_keywords(texts, exclude=args["query"], top_n=40)  # 전문가 모드 '한눈에 보는 키워드'용
        except (ValueError, NaverSearchError) as e:
            error = str(e)
    return render_template("index.html", args=args, result=result, error=error,
                           words=words, words_shown=visible_word_count(words),
                           is_home=is_home, suggestions=SUGGESTIONS, cloud=cloud)


@app.route("/api/news")
def api_news():
    """검색 API (JSON).  예: /api/news?query=커피&display=10&sort=date"""
    args = _get_search_args()
    try:
        return jsonify(search_news(**args))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except NaverSearchError as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/preview")
def api_preview():
    """목록용 미리보기: 첫 이미지 주소 + 언론사 이름 + 긍정/부정/중립 판정.

    기사를 가져온 결과는 캐시되므로 나중에 기사를 펼칠 때 다시 요청하지 않는다.
    본문을 못 가져오면 검색 요약(description)으로 판정한다.
    """
    try:
        article = fetch_article(request.args.get("link", ""), request.args.get("originallink", ""))
        # 첫 사진이 아이콘처럼 작을 수 있으므로 후보를 몇 개 보내고, 화면에서 크기를 확인해 고른다
        text, press = article["body"], article.get("press")
        images = [m["src"] for m in (article.get("images") or [])[:4]]
    except ArticleFetchError:
        text, images, press = request.args.get("description", ""), [], None
    try:
        s = analyze_sentiment(text)
        sentiment = {k: s[k] for k in ("label", "positive", "negative", "matched")}
    except RuntimeError:  # 감성사전 없음
        sentiment = None
    return jsonify({"images": images, "press": press or None, "sentiment": sentiment})


@app.route("/api/article")
def api_article():
    """기사 본문 + 파이썬 분석 (JSON).

    파라미터: link, originallink, title, description
    본문 수집에 실패하면 API 요약(description)으로 대신 분석한다.
    """
    link = request.args.get("link", "")
    originallink = request.args.get("originallink", "")
    title = request.args.get("title", "")
    description = request.args.get("description", "")

    warning = warning_detail = None
    try:
        article = fetch_article(link, originallink)
    except ArticleFetchError as e:
        warning = "원문 페이지에서 본문을 가져오지 못해 검색 요약으로 분석했습니다."
        warning_detail = str(e)
        article = {"title": title, "subtitle": "", "images": [], "press": "", "date": "",
                   "body": description, "url": link or originallink, "source": "summary"}

    try:
        analysis = analyze_article(article["title"] or title, article["body"], article["subtitle"])
    except RuntimeError as e:  # 감성사전 없음 등
        return jsonify({"error": str(e)}), 500

    return jsonify({"article": article, "analysis": analysis,
                    "warning": warning, "warning_detail": warning_detail})


if __name__ == "__main__":
    # 디버그 모드(웹 디버거로 코드 실행 가능)는 FLASK_DEBUG=1 일 때만 켠다
    app.run(host="127.0.0.1", port=5000, debug=os.getenv("FLASK_DEBUG") == "1")
