"""사이트 어댑터 공통 인터페이스."""

from typing import Protocol, TypedDict, runtime_checkable


class Item(TypedDict):
    """수집된 게시글 하나를 표현하는 딕셔너리 구조."""

    id: str          # 중복 판단 기준. URL 또는 게시글 고유번호 기반으로 안정적으로 생성
    title: str       # 게시글 제목
    url: str         # 절대 URL
    source: str      # 사이트 표시명 (예: "보안뉴스")
    published: str | None  # 게시일 문자열. 알 수 없으면 None


@runtime_checkable
class BaseSite(Protocol):
    """각 사이트 모듈이 만족해야 하는 프로토콜.

    모듈 수준에 `fetch_items()` 함수만 있으면 된다.
    """

    def fetch_items(self) -> list[Item]:
        """해당 사이트의 최근 게시글 목록을 Item 리스트로 반환한다."""
        ...


def make_item(
    *,
    item_id: str,
    title: str,
    url: str,
    source: str,
    published: str | None = None,
) -> Item:
    """Item 딕셔너리를 만들어 반환한다 (필드 누락 방지용 헬퍼)."""
    return {
        "id": item_id,
        "title": title.strip(),
        "url": url,
        "source": source,
        "published": published,
    }
