"""씽굿(thinkcontest.com) 공모전 목록 수집 어댑터.

목록은 자바스크립트로 렌더링되지만, 실제 데이터는 아래 내부 JSON API에서 온다.
브라우저 네트워크 탭에서 확인한 결과 이 API는 쿠키/토큰 없이 직접 호출할 수 있어
Playwright 없이 requests만으로 수집한다.

    POST https://www.thinkcontest.com/thinkgood/user/contest/subList.do
    Content-Type: application/json

주의: 페이지가 보내는 `querystr`(cryptoEncode.do가 발급하는 암호화 토큰)은 생략해야 한다.
빈 문자열로라도 넣으면 서버가 빈 목록을 반환한다. 아예 키를 빼면 정상 동작한다.
"""

import logging
import time
from typing import Any

import requests

from .. import config
from .base import Item, make_item

logger = logging.getLogger(__name__)

SOURCE = "씽굿"

API_URL = "https://www.thinkcontest.com/thinkgood/user/contest/subList.do"
VIEW_URL = "https://www.thinkcontest.com/thinkgood/user/contest/view.do?contest_pk={pk}"
LIST_PAGE = "https://www.thinkcontest.com/thinkgood/user/contest/index.do"

# 서버가 응답당 10건으로 고정 반환한다(recordsPerPage를 올려도 늘지 않음).
PAGE_SIZE = 10

# 키워드별 요청 사이 대기 시간 (초)
REQUEST_DELAY = 0.6

HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Content-Type": "application/json; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": LIST_PAGE,
}


def _search(keyword: str) -> list[dict[str, Any]]:
    """키워드로 공모전을 검색해 원본 JSON 레코드 목록을 반환한다."""
    payload = {
        "recordsPerPage": PAGE_SIZE,
        "currentPageNo": 1,
        "searchStatus": "Y",
        "sidx": "putup_sdt",   # 게시일 기준
        "sord": "DESC",        # 최신순
        "searchKeyword": keyword,
        "search_type": "program_nm",
    }
    resp = requests.post(
        API_URL, json=payload, headers=HEADERS, timeout=config.REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("listJsonData") or []


def fetch_items() -> list[Item]:
    """config.KEYWORDS로 검색한 공모전을 contest_pk 기준 dedup해 반환한다.

    API 호출이 실패하면 빈 리스트를 반환하고 경고만 남겨 다른 소스에 영향을 주지 않는다.
    """
    merged: dict[int, Item] = {}

    for keyword in config.KEYWORDS:
        try:
            records = _search(keyword)
        except (requests.RequestException, ValueError) as exc:
            logger.warning("[%s] '%s' 검색 실패: %s", SOURCE, keyword, exc)
            continue

        logger.info("[%s] '%s' → %d건", SOURCE, keyword, len(records))
        for record in records:
            pk = record.get("contest_pk")
            title = (record.get("program_nm") or "").strip()
            if pk is None or not title:
                continue
            if pk in merged:
                continue

            merged[pk] = make_item(
                item_id=f"thinkcontest-{pk}",
                title=title,
                url=VIEW_URL.format(pk=pk),
                source=SOURCE,
                # 접수 기간 문자열 (예: "2026-07-01 ~ 2026-08-31")
                published=(record.get("receive_period") or "").strip() or None,
            )

        time.sleep(REQUEST_DELAY)

    if not merged:
        logger.warning("[%s] 수집된 항목이 없습니다. API 응답 형식을 확인하세요.", SOURCE)

    # contest_pk가 클수록 최신 등록이므로 내림차순 정렬.
    # 개수 상한은 main.py가 키워드 필터 뒤에 적용한다.
    return sorted(merged.values(), key=lambda it: int(it["id"].rsplit("-", 1)[1]), reverse=True)
