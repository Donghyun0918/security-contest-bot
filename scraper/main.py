"""수집 → 키워드 필터 → 중복 제거 → 디스코드 알림 파이프라인."""

import logging
import sys
import time
from types import ModuleType

from . import config, store
from .discord_notify import send_discord_embed
from .sites import boannews, kisa_notice, linkareer, thinkcontest

logger = logging.getLogger("scraper")

# 새 사이트를 추가하려면 scraper/sites/ 에 fetch_items()가 있는 모듈을 만들고
# import 한 뒤 아래 목록에 등록하면 된다.
SITES: list[ModuleType] = [
    boannews,
    kisa_notice,
    thinkcontest,
    linkareer,
]


def setup_logging() -> None:
    """stderr로 INFO 이상 로그를 출력하도록 설정한다."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def matches_keyword(title: str) -> bool:
    """제목에 KEYWORDS 중 하나라도 포함되는지 검사한다 (대소문자 무시)."""
    lowered = title.lower()
    return any(keyword.lower() in lowered for keyword in config.KEYWORDS)


def source_limit(source: str) -> int:
    """해당 소스의 1회 실행당 알림 상한을 반환한다."""
    return config.MAX_ITEMS_PER_SOURCE.get(source, config.MAX_ITEMS_PER_SITE)


def cap_per_source(items: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """소스별 상한까지만 남기고, (남은 항목, 소스별 잘린 건수)를 반환한다.

    입력 순서(최신순)를 유지하므로 잘려나가는 것은 항상 오래된 쪽이다.
    """
    counts: dict[str, int] = {}
    dropped: dict[str, int] = {}
    capped: list[dict] = []
    for item in items:
        source = item.get("source", "")
        if counts.get(source, 0) >= source_limit(source):
            dropped[source] = dropped.get(source, 0) + 1
            continue
        counts[source] = counts.get(source, 0) + 1
        capped.append(item)
    return capped, dropped


def collect_all() -> list[dict]:
    """등록된 모든 사이트에서 항목을 수집한다.

    한 사이트에서 예외가 나도 나머지 사이트 수집은 계속 진행한다.
    """
    collected: list[dict] = []
    for site in SITES:
        name = site.__name__.rsplit(".", 1)[-1]
        try:
            items = site.fetch_items()
        except Exception as exc:  # 사이트 하나의 실패를 격리
            logger.warning("[%s] 수집 중 예외 발생, 건너뜁니다: %s", name, exc)
            continue
        logger.info("[%s] %d건 수집됨", name, len(items))
        collected.extend(items)
    return collected


def bootstrap(filtered: list[dict]) -> int:
    """최초 실행 처리: 알림 없이 현재 항목들을 seen에 기록만 한다.

    다음 실행부터는 여기서 기록한 것 이후에 새로 올라온 글만 알림이 간다.
    """
    ids = {item["id"] for item in filtered}
    logger.info(
        "최초 실행입니다. 알림을 보내지 않고 현재 %d건을 기준점으로 기록합니다. "
        "(다음 실행부터 새 글만 알림) 과거 글까지 받으려면 "
        "config.BOOTSTRAP_ON_FIRST_RUN = False 로 바꾸세요.",
        len(ids),
    )
    for item in filtered:
        logger.info("  기준점: [%s] %s", item["source"], item["title"])

    if not config.DISCORD_WEBHOOK_URL:
        logger.info("DRY-RUN이므로 seen.json을 갱신하지 않습니다.")
    else:
        store.save_seen(ids)
    return 0


def main() -> int:
    """전체 파이프라인을 실행하고 종료 코드를 반환한다."""
    setup_logging()

    if not config.DISCORD_WEBHOOK_URL:
        logger.warning(
            "DISCORD_WEBHOOK_URL이 설정되지 않았습니다. DRY-RUN 모드로 실행합니다."
        )

    items = collect_all()
    logger.info("총 %d건 수집", len(items))

    # 1) 키워드 필터 (상한은 아직 적용하지 않는다)
    matched = [item for item in items if matches_keyword(item["title"])]
    logger.info("키워드 필터 통과: %d건", len(matched))

    # 2) 이미 알림 보낸 항목 제외 (이번 실행 내 중복도 함께 제거)
    seen = store.load_seen()

    # 2-a) 최초 실행이면 알림을 보내지 않고 기준점만 기록한다.
    #      (그러지 않으면 첫 실행에서 수십 건이 한꺼번에 전송된다)
    #      상한을 적용하지 않은 전체를 기록해야 과거 글이 미아로 남지 않는다.
    if config.BOOTSTRAP_ON_FIRST_RUN and not seen and matched:
        return bootstrap(matched)

    new_items: list[dict] = []
    batch_ids: set[str] = set()
    for item in matched:
        if item["id"] in seen or item["id"] in batch_ids:
            continue
        batch_ids.add(item["id"])
        new_items.append(item)
    logger.info("새 항목: %d건", len(new_items))

    # 2-b) 소스별 상한 적용. 중복 제거 "뒤"에 적용해야 상한이
    #      "1회 실행당 소스별 최대 신규 알림 건수"라는 의미를 갖는다.
    new_items, dropped = cap_per_source(new_items)
    for source, count in dropped.items():
        logger.warning(
            "[%s] 상한(%d건)을 넘겨 %d건을 이번 실행에서 제외했습니다. "
            "seen에 기록하지 않으므로 다음 실행에서 재시도됩니다. "
            "반복되면 config.MAX_ITEMS_PER_SOURCE 값을 올리세요.",
            source,
            source_limit(source),
            count,
        )
    if dropped:
        logger.info("상한 적용 후: %d건", len(new_items))

    if not new_items:
        logger.info("보낼 새 항목이 없습니다.")
        return 0

    # 3) 전송 — 항목 사이에 sleep을 둬 rate limit을 피한다
    sent_ids: set[str] = set()
    for index, item in enumerate(new_items):
        if send_discord_embed(item):
            sent_ids.add(item["id"])
        if index < len(new_items) - 1:
            time.sleep(config.SEND_DELAY_SECONDS)

    logger.info("전송 성공 %d / %d건", len(sent_ids), len(new_items))

    # 4) 성공한 것만 seen에 반영 (DRY-RUN에서는 상태를 더럽히지 않는다)
    if not config.DISCORD_WEBHOOK_URL:
        logger.info("DRY-RUN이므로 seen.json을 갱신하지 않습니다.")
    elif sent_ids:
        store.save_seen(seen | sent_ids)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
