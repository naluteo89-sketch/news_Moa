"""네이버 뉴스 API 결과 링크로 기사 본문을 가져올 수 있는지 확인하는 스크립트.

실행:  python check_article_fetch.py 커피
       python check_article_fetch.py 커피 20     (검색 건수 지정)

확인하는 것:
  1) API의 link가 네이버 뉴스(n.news.naver.com) 주소인 비율
  2) 네이버 뉴스 페이지에서 본문 영역(#dic_area)을 찾을 수 있는지 + 본문 길이
  3) 언론사 원문 링크(originallink)에서 본문을 찾을 수 있는지
  4) 페이지가 iframe(오버레이 안 원본 표시)을 막는지 (X-Frame-Options / CSP)
"""
import sys
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from components import search_news

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
DELAY = 0.5  # 요청 간격(초) - 차단 방지


def get(url):
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp


def frame_blocked(resp):
    xfo = resp.headers.get("X-Frame-Options", "")
    csp = resp.headers.get("Content-Security-Policy", "")
    return bool(xfo) or "frame-ancestors" in csp, xfo or ("CSP frame-ancestors" if "frame-ancestors" in csp else "-")


def naver_body_len(html):
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("#dic_area") or soup.select_one("#newsct_article")
    return len(body.get_text(" ", strip=True)) if body else 0


def image_info(html):
    """(본문 이미지 수, 대표 이미지 og:image 유무)"""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("#dic_area") or soup.select_one("#newsct_article") or soup.find("article")
    n = 0
    if body:
        n = sum(1 for img in body.select("img") if (img.get("data-src") or img.get("src") or "").startswith("http"))
    og = soup.find("meta", property="og:image")
    return n, bool(og and og.get("content", "").startswith("http"))


def image_loads(url, referer=None):
    """이미지 주소를 실제로 받을 수 있는지 (외부 사이트에서 쓰면 막히는지 확인)"""
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    try:
        r = requests.get(url, headers=headers, timeout=10, stream=True)
        return r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image")
    except requests.exceptions.RequestException:
        return False


def generic_body_len(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, nav, header, footer, aside, form"):
        tag.decompose()
    scope = soup.find("article") or soup
    return sum(len(p.get_text(" ", strip=True)) for p in scope.find_all("p")
               if len(p.get_text(strip=True)) >= 30)


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "커피"
    display = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    result = search_news(query, display=display, sort="date")
    items = result["items"]
    print(f"검색어: {query} / 총 {result['total']:,}건 중 {len(items)}건 점검\n")

    stats = {"naver": 0, "naver_ok": 0, "orig_ok": 0, "frame_blocked": 0, "fail": 0,
             "img_any": 0, "img_ok": 0, "img_tested": 0}
    for i, item in enumerate(items, 1):
        link, orig = item["link"], item["originallink"]
        is_naver = urlparse(link).netloc.endswith("news.naver.com")
        print(f"[{i}] {item['title'][:40]}")
        print(f"    link: {link}")
        try:
            if is_naver:
                stats["naver"] += 1
                resp = get(link)
                n_len = naver_body_len(resp.text)
                blocked, why = frame_blocked(resp)
                stats["naver_ok"] += n_len >= 100
                stats["frame_blocked"] += blocked
                print(f"    네이버 본문: {n_len}자 ({resp.status_code}, 최종주소 {urlparse(resp.url).netloc}) / iframe 차단: {why}")
                n_img, has_og = image_info(resp.text)
                stats["img_any"] += bool(n_img or has_og)
                # 첫 이미지를 '다른 사이트(localhost)에서 불러올 때'처럼 받아보기
                soup = BeautifulSoup(resp.text, "html.parser")
                first = soup.select_one("#dic_area img")
                src = (first.get("data-src") or first.get("src")) if first else None
                if not src:
                    og = soup.find("meta", property="og:image")
                    src = og.get("content") if og else None
                if src:
                    ok = image_loads(src, referer="http://127.0.0.1:5000/")
                    stats["img_tested"] += 1
                    stats["img_ok"] += ok
                    print(f"    이미지: 본문 {n_img}장, 대표이미지 {'있음' if has_og else '없음'} / 외부에서 불러오기: {'가능' if ok else '막힘'}")
                time.sleep(DELAY)
            if orig:
                resp = get(orig)
                g_len = generic_body_len(resp.text)
                blocked, why = frame_blocked(resp)
                stats["orig_ok"] += g_len >= 100
                if not is_naver:
                    stats["frame_blocked"] += blocked
                print(f"    원문 본문(간이): {g_len}자 ({resp.status_code}, {urlparse(orig).netloc}) / iframe 차단: {why}")
                time.sleep(DELAY)
        except requests.exceptions.RequestException as e:
            stats["fail"] += 1
            print(f"    요청 실패: {e}")
        print()

    n = len(items) or 1
    print("=" * 60)
    print(f"네이버 뉴스 링크 비율      : {stats['naver']}/{len(items)} ({stats['naver'] / n:.0%})")
    print(f"네이버 본문 추출 성공      : {stats['naver_ok']}/{stats['naver']}")
    print(f"원문 링크 본문 추출 성공   : {stats['orig_ok']}/{len(items)}")
    print(f"iframe 차단된 기사         : {stats['frame_blocked']}/{len(items)}")
    print(f"요청 실패                  : {stats['fail']}")
    print(f"이미지 있는 네이버 기사    : {stats['img_any']}/{stats['naver']}")
    print(f"이미지 외부 불러오기 가능  : {stats['img_ok']}/{stats['img_tested']}")


if __name__ == "__main__":
    main()
