"""보안뉴스(boannews.com) 검색 결과 수집 어댑터.

주의: 이 사이트는 EUC-KR 인코딩을 사용한다. requests가 자동 감지한 인코딩
(resp.apparent_encoding)에 의존하면 한글이 깨질 수 있으므로 반드시
resp.encoding = "euc-kr" 을 명시적으로 설정한 뒤 resp.text를 파싱해야 한다.
"""

import logging
import re
import time
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from .. import config
from .base import Item, make_item

logger = logging.getLogger(__name__)

SOURCE = "보안뉴스"
BASE_URL = "https://www.boannews.com"
SEARCH_URL = BASE_URL + "/search/news_total.asp?search=title&find={keyword}"

# 검색 결과 영역으로 범위를 좁힌다. 페이지 전체에서 view.asp 링크를 긁으면
# 사이드바("많이 본 뉴스" 등)의 무관한 기사까지 섞여 들어온다.
# 사이트 구조가 바뀌면 이 셀렉터만 수정하면 됨
RESULT_SELECTOR = "#news_area .news_list a[href*='view.asp?idx=']"

# 기사 링크에서 idx 숫자를 뽑아내는 패턴
IDX_RE = re.compile(r"idx=(\d+)")

# 키워드별 요청 사이 대기 시간 (초)
REQUEST_DELAY = 0.7


def _fetch_keyword(keyword: str) -> list[Item]:
    """키워드 하나로 검색해 기사 목록을 반환한다."""
    url = SEARCH_URL.format(keyword=quote(keyword, encoding="euc-kr"))
    resp = requests.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT,
    )
    resp.raise_for_status()

    # EUC-KR 명시 (apparent_encoding에 의존하지 않는다)
    resp.encoding = "euc-kr"

    soup = BeautifulSoup(resp.text, "html.parser")
    anchors = soup.select(RESULT_SELECTOR)
    if not anchors:
        logger.warning(
            "[%s] RESULT_SELECTOR(%r)로 결과를 찾지 못했습니다. "
            "사이트 구조가 바뀌었을 수 있습니다.",
            SOURCE,
            RESULT_SELECTOR,
        )

    # 결과 하나당 제목 링크와 요약문 링크가 같은 idx로 두 번 나온다.
    # 제목이 먼저 나오므로 idx별 첫 번째 링크만 취한다.
    by_idx: dict[str, Item] = {}
    for anchor in anchors:
        href = anchor.get("href", "")
        match = IDX_RE.search(href)
        if not match:
            continue

        title = anchor.get_text(strip=True)
        if not title:
            continue  # 썸네일 링크 등 텍스트 없는 <a>는 건너뛴다

        idx = match.group(1)
        if idx in by_idx:
            continue

        by_idx[idx] = make_item(
            item_id=f"boannews-{idx}",
            title=title,
            url=urljoin(BASE_URL, href),
            source=SOURCE,
        )

    return list(by_idx.values())


def fetch_items() -> list[Item]:
    """config.KEYWORDS의 각 키워드로 검색하고 idx 기준으로 dedup해 합친다."""
    merged: dict[str, Item] = {}

    for keyword in config.KEYWORDS:
        try:
            found = _fetch_keyword(keyword)
        except requests.RequestException as exc:
            logger.warning("[%s] '%s' 검색 실패: %s", SOURCE, keyword, exc)
            continue

        logger.info("[%s] '%s' → %d건", SOURCE, keyword, len(found))
        for item in found:
            merged.setdefault(item["id"], item)

        time.sleep(REQUEST_DELAY)

    # idx가 큰 쪽이 최신 기사이므로 내림차순 정렬.
    # 개수 상한은 main.py가 키워드 필터 뒤에 적용한다.
    return sorted(
        merged.values(),
        key=lambda it: int(it["id"].rsplit("-", 1)[1]),
        reverse=True,
    )
