"""KISA(한국인터넷진흥원) 공지사항 목록 수집 어댑터.

과거의 레거시 JSP 게시판(notice_List.jsp)은 폐기되어 403을 반환한다.
현행 사이트는 숫자 경로를 쓰며, 공지사항 목록은 /401 이다.
인증이나 특별한 헤더(Referer 등)는 필요 없고 일반 GET으로 200을 받는다.

필터링은 하지 않고 목록 전체를 반환하며, 키워드 필터와 개수 상한은 main.py가 담당한다.
"""

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from .. import config
from .base import Item, make_item

logger = logging.getLogger(__name__)

SOURCE = "KISA 공지사항"

# ---------------------------------------------------------------------------
# 사이트 구조가 바뀌면 여기 셀렉터/URL만 수정하면 됨
# (아래 값들은 2026-07 기준 실제 페이지에서 확인한 값)
# ---------------------------------------------------------------------------
LIST_URL = "https://www.kisa.or.kr/401?page={page}"
VIEW_URL = "https://www.kisa.or.kr/401/form?postSeq={no}"

# 읽어올 목록 페이지 수 (1페이지당 10건).
# 주의: 페이징 파라미터는 `page`다. `pageIndex`는 무시되고 항상 1페이지가 나온다.
LIST_PAGES = 2
LIST_SELECTOR = "table.tbl_board tbody tr"   # 목록 테이블의 각 행
TITLE_SELECTOR = "td.sbj a"                  # 행 안의 제목 링크
DATE_SELECTOR = "td:nth-of-type(3)"          # 행 안의 등록일 셀
# ---------------------------------------------------------------------------

# 상세 링크에서 게시글 번호를 뽑는 패턴 (/401/form?postSeq=3721&page=1)
POST_SEQ_RE = re.compile(r"postSeq=(\d+)")

# 목록 상단 배너 등에 섞여 들어오는 제목 없는 링크
SKIP_TITLES = {"자세히 보기", "더보기"}

# 페이지 요청 사이 대기 시간 (초)
REQUEST_DELAY = 0.5


def fetch_items() -> list[Item]:
    """KISA 공지사항 목록을 최신순으로 반환한다.

    요청이 실패하거나 셀렉터가 맞지 않으면 빈 리스트를 반환하고 경고만 남긴다.
    """
    rows = []
    for page in range(1, LIST_PAGES + 1):
        try:
            resp = requests.get(
                LIST_URL.format(page=page),
                headers={"User-Agent": config.USER_AGENT},
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("[%s] %d페이지 요청 실패: %s", SOURCE, page, exc)
            continue

        page_rows = BeautifulSoup(resp.text, "html.parser").select(LIST_SELECTOR)
        if not page_rows:
            logger.warning(
                "[%s] %d페이지에서 LIST_SELECTOR(%r)로 행을 찾지 못했습니다. "
                "사이트 구조가 바뀌었을 수 있으니 셀렉터를 확인하세요.",
                SOURCE,
                page,
                LIST_SELECTOR,
            )
            continue
        rows.extend(page_rows)

        if page < LIST_PAGES:
            time.sleep(REQUEST_DELAY)

    if not rows:
        return []

    items: list[Item] = []
    seen_ids: set[str] = set()

    for row in rows:
        anchor = row.select_one(TITLE_SELECTOR)
        if anchor is None:
            continue

        title = anchor.get_text(" ", strip=True)
        if not title or title in SKIP_TITLES:
            continue

        match = POST_SEQ_RE.search(anchor.get("href") or "")
        if not match:
            continue

        post_seq = match.group(1)
        item_id = f"kisa-{post_seq}"
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        date_cell = row.select_one(DATE_SELECTOR)
        published = date_cell.get_text(strip=True) if date_cell else None

        items.append(
            make_item(
                item_id=item_id,
                title=title,
                url=VIEW_URL.format(no=post_seq),
                source=SOURCE,
                published=published or None,
            )
        )

    if not items:
        logger.warning(
            "[%s] 행은 찾았지만 항목을 만들지 못했습니다. "
            "TITLE_SELECTOR(%r)를 확인하세요.",
            SOURCE,
            TITLE_SELECTOR,
        )

    logger.info("[%s] %d건 수집", SOURCE, len(items))
    return items
