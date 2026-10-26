"""기사 본문 수집 컴포넌트.

1순위: 네이버 뉴스 페이지(n.news.naver.com)에서 본문 추출 (구조가 일정해 안정적)
2순위: 언론사 원문 링크에서 본문 추출 (trafilatura가 있으면 사용, 없으면 간이 추출)
"""
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:  # 선택 설치: pip install trafilatura
    import trafilatura
except ImportError:  # pragma: no cover
    trafilatura = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
MIN_BODY_LEN = 100  # 이보다 짧으면 본문 추출 실패로 보고 다음 방법 시도
MAX_REDIRECTS = 5
MAX_HTML_BYTES = 5 * 1024 * 1024  # 이보다 큰 페이지는 받지 않음
MAX_CACHE = 500                   # 캐시에 보관할 기사 수 (넘으면 오래된 것부터 삭제)

_cache = {}  # url -> 결과 (같은 기사를 다시 요청하지 않도록)


class ArticleFetchError(Exception):
    """본문을 가져오지 못했을 때 발생하는 예외."""


def _check_public_url(url):
    """http(s)이고 공인 IP로만 연결되는 주소인지 확인 (내부망 접근(SSRF) 방지)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise requests.exceptions.InvalidURL(f"허용되지 않는 주소: {url}")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 0, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as e:
        raise requests.exceptions.ConnectionError(f"주소를 찾을 수 없음: {parsed.hostname}") from e
    for info in infos:
        if not ipaddress.ip_address(info[4][0].split("%")[0]).is_global:
            raise requests.exceptions.InvalidURL(f"내부망 주소는 허용되지 않음: {parsed.hostname}")


def _get_html(url, timeout=10):
    # 리다이렉트를 직접 따라가며 매번 주소를 검사한다 (외부 주소 -> 내부망 리다이렉트 차단)
    for _ in range(MAX_REDIRECTS + 1):
        _check_public_url(url)
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=False, stream=True)
        if resp.is_redirect:
            resp.close()
            url = urljoin(url, resp.headers["Location"])
            continue
        break
    else:
        raise requests.exceptions.TooManyRedirects(f"리다이렉트가 너무 많음: {url}")

    with resp:
        resp.raise_for_status()
        content = b""
        for chunk in resp.iter_content(64 * 1024):
            content += chunk
            if len(content) > MAX_HTML_BYTES:
                raise requests.exceptions.ContentDecodingError(f"페이지가 너무 큼: {url}")
        resp._content = content
    # 일부 언론사는 EUC-KR이면서 인코딩을 명시하지 않음
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding
    return resp.url, resp.text


def _clean_text(text):
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _og_image(soup):
    """페이지 대표 이미지(og:image) -> [{"src", "caption"}] (없으면 빈 리스트)."""
    og = soup.find("meta", property="og:image")
    src = og.get("content", "") if og else ""
    return [{"src": src, "caption": ""}] if src.startswith("http") else []


def _is_naver_news(url):
    return urlparse(url).netloc.endswith("news.naver.com")


def parse_naver_news(html):
    """네이버 뉴스 기사 페이지 HTML -> dict (본문이 없으면 None)."""
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("#dic_area") or soup.select_one("#newsct_article")
    if body is None:
        return None

    # 이미지: 본문 사진(지연 로딩이라 data-src 우선) + 사진 설명. 없으면 대표 이미지(og:image)
    images = []
    for img in body.select("img"):
        src = img.get("data-src") or img.get("src") or ""
        if not src.startswith("http"):
            continue
        box = img.find_parent(class_="end_photo_org") or img.parent
        cap = box.select_one(".img_desc") if box else None
        images.append({"src": src, "caption": cap.get_text(" ", strip=True) if cap else ""})
    if not images:
        images = _og_image(soup)

    # 부제목(요약 박스)은 따로 보관한 뒤 본문에서 제거
    summary = body.select_one(".media_end_summary") or soup.select_one(".media_end_summary")
    subtitle = _clean_text(summary.get_text("\n")) if summary else ""

    # 사진 설명, 요약 박스, 스크립트 등 본문이 아닌 요소 제거
    for tag in body.select("script, style, .end_photo_org, .img_desc, em.img_desc, .media_end_summary"):
        tag.decompose()
    for br in body.find_all("br"):
        br.replace_with("\n")

    title = soup.select_one("#title_area") or soup.select_one(".media_end_head_headline")
    press = soup.select_one(".media_end_head_top_logo img[alt]")
    date = soup.select_one(".media_end_head_info_datestamp_time")

    return {
        "title": title.get_text(strip=True) if title else "",
        "subtitle": subtitle,
        "images": images[:10],
        "press": press["alt"] if press else "",
        "date": (date.get("data-date-time") or date.get_text(strip=True)) if date else "",
        "body": _clean_text(body.get_text("\n")),
    }


def parse_generic(html, url=""):
    """언론사 페이지 HTML -> dict (본문이 없으면 None)."""
    text = ""
    if trafilatura is not None:
        text = trafilatura.extract(html, url=url, include_comments=False) or ""

    soup = BeautifulSoup(html, "html.parser")
    if len(text) < MIN_BODY_LEN:
        # 간이 추출: <article> 안의 문단, 없으면 페이지 전체에서 긴 문단만 모으기
        for tag in soup.select("script, style, nav, header, footer, aside, form"):
            tag.decompose()
        scope = soup.find("article") or soup
        paragraphs = [p.get_text(" ", strip=True) for p in scope.find_all("p")]
        text = "\n".join(p for p in paragraphs if len(p) >= 30)

    if len(text) < MIN_BODY_LEN:
        return None

    og_title = soup.find("meta", property="og:title")
    og_site = soup.find("meta", property="og:site_name")  # 언론사가 직접 적어둔 매체 이름
    return {
        "title": og_title["content"] if og_title and og_title.get("content") else "",
        "subtitle": "",
        "images": _og_image(soup),
        "press": og_site["content"].strip() if og_site and og_site.get("content") else "",
        "date": "",
        "body": _clean_text(text),
    }


def fetch_article(link, originallink=""):
    """기사 본문을 가져온다.

    Args:
        link:         네이버 API의 link (네이버 뉴스 주소일 수도, 언론사 주소일 수도 있음)
        originallink: 네이버 API의 originallink (언론사 원문 주소)

    Returns:
        {"title", "subtitle", "images": [{"src", "caption"}], "press", "date", "body", "url",
         "source": "naver" | "original"}
    """
    candidates = [u for u in dict.fromkeys([link, originallink]) if u]
    if not candidates:
        raise ArticleFetchError("기사 링크가 없습니다.")

    for url in candidates:
        if url in _cache:
            return _cache[url]

    errors = []
    for url in candidates:
        try:
            final_url, html = _get_html(url)
        except requests.exceptions.RequestException as e:
            errors.append(f"{url}: {e}")
            continue

        parsed = parse_naver_news(html) if _is_naver_news(final_url) else None
        source = "naver"
        if not parsed or len(parsed["body"]) < MIN_BODY_LEN:
            parsed = parse_generic(html, final_url)
            source = "original" if url == originallink else "naver"
        if parsed:
            result = {**parsed, "url": final_url, "source": source}
            if len(_cache) >= MAX_CACHE:
                _cache.pop(next(iter(_cache)))
            _cache[url] = result
            return result
        errors.append(f"{url}: 본문을 찾지 못함")

    raise ArticleFetchError("본문 수집 실패 - " + " / ".join(errors))
