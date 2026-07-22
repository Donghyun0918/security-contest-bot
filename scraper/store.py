"""이미 알림을 보낸 게시글 id를 파일에 저장/조회한다."""

import json
import logging

from . import config

logger = logging.getLogger(__name__)


def load_seen() -> set[str]:
    """seen.json에서 이미 알림 보낸 id 집합을 읽어온다.

    파일이 없거나 깨져 있으면 빈 집합으로 시작한다.
    """
    path = config.SEEN_STORE_PATH
    if not path.exists():
        logger.info("seen 저장소가 없어 빈 집합으로 시작합니다: %s", path)
        return set()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("seen 저장소를 읽지 못해 빈 집합으로 시작합니다: %s", exc)
        return set()

    if isinstance(raw, dict):  # {"seen": [...]} 형태도 허용
        raw = raw.get("seen", [])
    if not isinstance(raw, list):
        logger.warning("seen 저장소 형식이 예상과 달라 빈 집합으로 시작합니다.")
        return set()

    return {str(item) for item in raw}


def save_seen(seen: set[str]) -> None:
    """id 집합을 seen.json에 정렬해서 저장한다."""
    path = config.SEEN_STORE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("seen 저장 완료 (%d건): %s", len(seen), path)
