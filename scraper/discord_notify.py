"""디스코드 웹훅으로 Embed 알림을 전송한다."""

import logging
import time
from datetime import datetime, timezone

import requests

from . import config

logger = logging.getLogger(__name__)

# 429 응답을 받았을 때 최대 재시도 횟수
MAX_RETRIES = 3


def build_embed(item: dict) -> dict:
    """item 딕셔너리를 디스코드 Embed 페이로드로 변환한다."""
    return {
        "title": item["title"][:256],  # 디스코드 embed title 길이 제한
        "url": item["url"],
        "color": config.EMBED_COLOR,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": item.get("source", "")},
        "fields": [
            {"name": "출처", "value": item.get("source", "-"), "inline": True},
            # 소스별로 게시일/접수기간/마감일 등이 들어오므로 라벨은 "일정"으로 통일
            {"name": "일정", "value": item.get("published") or "-", "inline": True},
        ],
    }


def send_discord_embed(item: dict) -> bool:
    """item 하나를 디스코드 웹훅으로 전송한다.

    웹훅 URL이 없으면 실제 전송 대신 DRY-RUN 로그만 출력한다.
    429(rate limit) 응답을 받으면 retry_after만큼 대기 후 재시도한다.
    성공하면 True, 실패하면 False를 반환한다.
    """
    if not config.DISCORD_WEBHOOK_URL:
        print(f"[DRY-RUN] would send: {item['title']}")
        return True

    payload = {"embeds": [build_embed(item)]}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                config.DISCORD_WEBHOOK_URL,
                json=payload,
                timeout=config.REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            logger.warning("웹훅 전송 실패 (%d/%d): %s", attempt, MAX_RETRIES, exc)
            time.sleep(2 * attempt)
            continue

        if resp.status_code == 429:
            # 디스코드 rate limit — retry_after(초)만큼 기다렸다 재시도
            try:
                retry_after = float(resp.json().get("retry_after", 1))
            except (ValueError, AttributeError):
                retry_after = 1.0
            logger.warning(
                "rate limit 발생, %.2f초 대기 후 재시도 (%d/%d)",
                retry_after,
                attempt,
                MAX_RETRIES,
            )
            time.sleep(retry_after + 0.5)
            continue

        if 200 <= resp.status_code < 300:
            logger.info("전송 성공: %s", item["title"])
            return True

        logger.warning(
            "웹훅이 %d 응답을 반환했습니다: %s", resp.status_code, resp.text[:200]
        )
        return False

    logger.warning("재시도 횟수를 초과해 전송을 포기합니다: %s", item["title"])
    return False
