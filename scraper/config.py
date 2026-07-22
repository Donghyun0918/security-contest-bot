"""봇 전역 설정값 모음."""

import os
from pathlib import Path

# 프로젝트 루트 (이 파일 기준 한 단계 위)
BASE_DIR: Path = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """로컬 실행 편의를 위해 .env를 읽어 환경변수에 채운다.

    이미 설정된 환경변수는 덮어쓰지 않는다(GitHub Actions에서는 .env가 없음).
    외부 라이브러리 없이 KEY=VALUE 형식만 간단히 처리한다.
    """
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()

# 디스코드 웹훅 URL. 비어 있으면 main.py가 DRY-RUN 모드로 동작한다.
DISCORD_WEBHOOK_URL: str = os.environ.get("DISCORD_WEBHOOK_URL", "")

# 제목 필터링에 사용할 키워드 (대소문자 무시하고 부분일치 검사)
KEYWORDS: list[str] = [
    "정보보안",
    "정보보호",
    "사이버보안",
    "해킹방어대회",
    "해킹대회",
    "화이트햇",
    "CTF",
    "보안 공모전",
    "보안공모전",
    "취약점",
    "개인정보보호",
]

# 이미 알림 보낸 id 목록을 저장하는 파일 경로
SEEN_STORE_PATH: Path = BASE_DIR / "data" / "seen.json"

# 소스별 설정이 없을 때 쓰는 기본 상한
MAX_ITEMS_PER_SITE: int = 15

# 소스별 1회 실행당 최대 알림 건수. 여기에 없는 소스는 MAX_ITEMS_PER_SITE를 쓴다.
# 키는 각 site 모듈의 SOURCE 상수와 정확히 일치해야 한다.
# 뉴스 매체(보안뉴스)는 키워드 통과량이 많고, 공모전 게시판은 적지만 건당 가치가 높다.
MAX_ITEMS_PER_SOURCE: dict[str, int] = {
    "보안뉴스": 20,
    "씽굿": 20,
    "KISA 공지사항": 10,
    "링커리어": 10,
}

# HTTP 요청 타임아웃 (초)
REQUEST_TIMEOUT: int = 15

# 데스크톱 크롬 User-Agent
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 디스코드 Embed 색상 (진한 파랑)
EMBED_COLOR: int = 0x2B6CB0

# 알림 전송 사이 대기 시간 (초) — rate limit 방지
SEND_DELAY_SECONDS: float = 1.5

# 최초 실행(seen.json이 비어 있음) 시 알림을 보내지 않고 기준점만 채울지 여부.
# True면 첫 실행에서 수십 건이 한꺼번에 전송되는 것을 막고, 그 이후 새로 올라온
# 글부터 알림을 보낸다. 과거 글까지 전부 받고 싶으면 False로 바꾼다.
BOOTSTRAP_ON_FIRST_RUN: bool = True
