"""원문 링크 주소 -> 언론사 이름.

목록에 없는 주소는 도메인(예: example.co.kr)을 그대로 보여준다.
새 언론사는 PRESS_NAMES에 '도메인': '이름' 으로 추가하면 된다.
"""
from urllib.parse import urlparse

PRESS_NAMES = {
    # 통신사
    "yna.co.kr": "연합뉴스", "yonhapnewstv.co.kr": "연합뉴스TV", "newsis.com": "뉴시스", "news1.kr": "뉴스1",
    # 종합지
    "chosun.com": "조선일보", "joongang.co.kr": "중앙일보", "donga.com": "동아일보", "hani.co.kr": "한겨레",
    "khan.co.kr": "경향신문", "hankookilbo.com": "한국일보", "kmib.co.kr": "국민일보", "seoul.co.kr": "서울신문",
    "segye.com": "세계일보", "munhwa.com": "문화일보", "newdaily.co.kr": "뉴데일리", "dailian.co.kr": "데일리안",
    "ohmynews.com": "오마이뉴스", "pressian.com": "프레시안", "nocutnews.co.kr": "노컷뉴스", "sisajournal.com": "시사저널",
    "mediatoday.co.kr": "미디어오늘", "kukinews.com": "쿠키뉴스",
    # 경제지
    "biz.chosun.com": "조선비즈", "mk.co.kr": "매일경제", "hankyung.com": "한국경제", "sedaily.com": "서울경제",
    "mt.co.kr": "머니투데이", "edaily.co.kr": "이데일리", "asiae.co.kr": "아시아경제", "fnnews.com": "파이낸셜뉴스",
    "heraldcorp.com": "헤럴드경제", "ajunews.com": "아주경제", "newspim.com": "뉴스핌", "bizwatch.co.kr": "비즈워치",
    "thebell.co.kr": "더벨", "ebn.co.kr": "EBN", "inthenews.co.kr": "인더뉴스", "businesspost.co.kr": "비즈니스포스트",
    # IT
    "etnews.com": "전자신문", "zdnet.co.kr": "지디넷코리아", "ddaily.co.kr": "디지털데일리", "dt.co.kr": "디지털타임스",
    "inews24.com": "아이뉴스24", "bloter.net": "블로터", "byline.network": "바이라인네트워크", "boannews.com": "보안뉴스",
    "itworld.co.kr": "ITWorld",
    # 방송
    "kbs.co.kr": "KBS", "imbc.com": "MBC", "sbs.co.kr": "SBS", "jtbc.co.kr": "JTBC", "ytn.co.kr": "YTN",
    "ichannela.com": "채널A", "mbn.co.kr": "MBN", "tvchosun.com": "TV조선", "wowtv.co.kr": "한국경제TV",
    "sentv.co.kr": "서울경제TV",
    # 지역/영문/스포츠·연예
    "busan.com": "부산일보", "kookje.co.kr": "국제신문", "imaeil.com": "매일신문", "kwnews.co.kr": "강원일보",
    "koreaherald.com": "코리아헤럴드", "koreatimes.co.kr": "코리아타임스",
    "sportsseoul.com": "스포츠서울", "sports.donga.com": "스포츠동아", "osen.co.kr": "OSEN",
    "xportsnews.com": "엑스포츠뉴스", "starnewskorea.com": "스타뉴스",
    # 네이버
    "news.naver.com": "네이버뉴스",
}

# 긴 도메인부터 비교해야 biz.chosun.com이 chosun.com보다 먼저 잡힌다
_SORTED = sorted(PRESS_NAMES, key=len, reverse=True)


def press_name(url):
    """URL -> 언론사 이름 (모르면 도메인, URL이 없으면 빈 문자열)."""
    host = urlparse(url or "").netloc.lower().split(":")[0]
    if not host:
        return ""
    for domain in _SORTED:
        if host == domain or host.endswith("." + domain):
            return PRESS_NAMES[domain]
    for prefix in ("www.", "m.", "news.", "mobile."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host
