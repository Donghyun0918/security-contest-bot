"""링커리어(linkareer.com) 공모전/대외활동 목록 수집 어댑터.

React SPA지만 목록 데이터는 공개 GraphQL API에서 온다. 브라우저 네트워크 탭에서
확인한 결과 이 엔드포인트는 인증(쿠키/토큰) 없이 호출할 수 있어 Playwright 없이
requests만으로 수집한다.

    POST https://api.linkareer.com/graphql

주의: 이 API의 ActivityFilter에는 키워드 검색 필드가 없다(introspection은 막혀 있고
keyword/search/query/title 등을 넣으면 모두 "not defined" 오류). 따라서 최신순으로
목록을 받아온 뒤 main.py의 공통 키워드 필터에 맡긴다.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from .. import config
from .base import Item, make_item

logger = logging.getLogger(__name__)

SOURCE = "링커리어"

API_URL = "https://api.linkareer.com/graphql"
VIEW_URL = "https://linkareer.com/activity/{activity_id}"

# activityTypeID: "3" = 공모전, "1" = 대외활동
# (linkareer.com/list/contest, /list/activity 페이지가 실제로 쓰는 값)
ACTIVITY_TYPE_IDS = ["3", "1"]

# 한 번에 받아올 개수. 키워드 필터를 통과할 확률을 높이려 목록을 넉넉히 받는다.
PAGE_SIZE = 60

QUERY = """
query($f: ActivityFilter, $p: Pagination, $o: ActivityOrder) {
  activities(filterBy: $f, pagination: $p, orderBy: $o) {
    totalCount
    nodes { id title organizationName recruitCloseAt }
  }
}
"""

HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://linkareer.com",
    "Referer": "https://linkareer.com/list/contest",
}


def _format_deadline(epoch_ms: Any) -> str | None:
    """recruitCloseAt(epoch 밀리초)을 "~2026-08-31 마감" 형태로 바꾼다."""
    if not isinstance(epoch_ms, (int, float)):
        return None
    try:
        dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return f"~{dt:%Y-%m-%d} 마감"


def _fetch_type(activity_type_id: str) -> list[dict[str, Any]]:
    """활동 유형 하나에 대해 최신 공고 노드 목록을 반환한다."""
    variables = {
        "f": {"activityTypeID": activity_type_id, "status": "OPEN"},
        "p": {"page": 1, "pageSize": PAGE_SIZE},
        "o": {"direction": "DESC", "field": "CREATED_AT"},
    }
    resp = requests.post(
        API_URL,
        json={"query": QUERY, "variables": variables},
        headers=HEADERS,
        timeout=config.REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()

    if payload.get("errors"):
        # 스키마가 바뀌면 여기서 걸린다. 메시지에 어떤 필드가 문제인지 나온다.
        raise ValueError(payload["errors"][0].get("message", "GraphQL error"))

    return (payload.get("data", {}).get("activities", {}) or {}).get("nodes") or []


def fetch_items() -> list[Item]:
    """링커리어 공모전/대외활동 최신 목록을 반환한다.

    API 호출이 실패하면 빈 리스트를 반환하고 경고만 남겨 다른 소스에 영향을 주지 않는다.
    """
    merged: dict[str, Item] = {}

    for type_id in ACTIVITY_TYPE_IDS:
        try:
            nodes = _fetch_type(type_id)
        except (requests.RequestException, ValueError) as exc:
            logger.warning("[%s] activityTypeID=%s 조회 실패: %s", SOURCE, type_id, exc)
            continue

        logger.info("[%s] activityTypeID=%s → %d건", SOURCE, type_id, len(nodes))
        for node in nodes:
            activity_id = str(node.get("id") or "")
            title = (node.get("title") or "").strip()
            if not activity_id or not title or activity_id in merged:
                continue

            merged[activity_id] = make_item(
                item_id=f"linkareer-{activity_id}",
                title=title,
                url=VIEW_URL.format(activity_id=activity_id),
                source=SOURCE,
                published=_format_deadline(node.get("recruitCloseAt")),
            )

    if not merged:
        logger.warning("[%s] 수집된 항목이 없습니다. GraphQL 스키마를 확인하세요.", SOURCE)

    # id가 클수록 최신 등록이므로 내림차순 정렬.
    # 개수 상한은 main.py가 키워드 필터 뒤에 적용한다.
    return sorted(merged.values(), key=lambda it: int(it["id"].rsplit("-", 1)[1]), reverse=True)
