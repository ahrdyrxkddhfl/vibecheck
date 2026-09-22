"""근거 목록에 같은 코드가 두 번 실리지 않는지 확인한다.

클래스와 그 메서드가 함께 뽑히면 메서드 코드가 두 번 실려 근거 칸만 차지한다.
담는 쪽을 남기고 안쪽을 빼며, 빈 칸은 다음 후보로 채운다.
"""

from vibecheck.models import Chunk
from vibecheck.services.practice import search_union
from vibecheck.services.qa import drop_contained


def chunk(kind: str, start: int, end: int, file: str = "A.java", name: str = "") -> Chunk:
    """줄 범위만 의미 있는 청크를 만든다.

    Args:
        kind (str): 청크 종류.
        start (int): 시작 줄.
        end (int): 끝 줄.
        file (str): 파일 경로.
        name (str): 심볼 이름. 비우면 종류와 줄로 만든다.

    Returns:
        Chunk: 청크.
    """
    return Chunk(file=file, symbol=name or f"{kind}{start}", kind=kind,
                 start_line=start, end_line=end, code="")


def test_담는_쪽을_남기고_안쪽_중_가장_앞_자리에_넣는다():
    """메서드 둘 뒤에 클래스가 오면 클래스가 첫 메서드 자리로 들어가고 메서드는 빠진다."""
    m1, other, m2, cls = (
        chunk("method", 20, 30),
        chunk("method", 5, 9, file="B.java"),
        chunk("method", 40, 50),
        chunk("class", 10, 100),
    )
    assert drop_contained([m1, other, m2, cls]) == [cls, other]


def test_파일_청크를_개요로_보낼_때는_겹침으로_치지_않는다():
    """채점은 파일 청크를 개요로 줄이므로 그 안의 함수와 겹치지 않는다."""
    f, m = chunk("file", 1, 200), chunk("method", 20, 30)
    assert drop_contained([f, m], file_is_code=False) == [f, m]
    assert drop_contained([f, m], file_is_code=True) == [f]


class FakeStore:
    """질의마다 정해둔 순서로 id를 돌려주는 가짜 벡터 저장소."""

    def __init__(self, results: dict[str, list[str]]) -> None:
        """질의별 결과를 받는다.

        Args:
            results (dict[str, list[str]]): 질의 -> 청크 id 목록.
        """
        self.results = results

    def search(self, query: str, top_k: int = 8, kinds=None) -> list[dict]:
        """정해둔 결과에서 앞의 top_k개를 돌려준다.

        Args:
            query (str): 질의.
            top_k (int): 돌려줄 수.
            kinds: 쓰지 않는다.

        Returns:
            list[dict]: {"id"} 목록.
        """
        return [{"id": i} for i in self.results.get(query, [])[:top_k]]


def test_채점_근거는_겹친_칸을_다음_후보로_채운다():
    """질문 쪽에 클래스와 메서드가 함께 걸려도 칸을 전부 서로 다른 근거로 채운다."""
    m1, cls, m2 = chunk("method", 20, 30), chunk("class", 10, 100), chunk("method", 40, 50)
    others = [chunk("function", 1, 5, file=f"f{i}.py") for i in range(6)]
    chunks = [m1, cls, m2, *others]
    store = FakeStore({
        "질문": [m1.id, cls.id, m2.id, others[0].id, others[1].id, others[2].id],
        "답변": [m1.id, others[3].id, others[4].id, others[5].id],
    })

    found = search_union("질문", "답변", chunks, store, top_k=6)

    assert len(found) == 6
    assert m1 not in found and m2 not in found
    assert cls in found
    # 안쪽 청크가 담는 쪽과 함께 남아 있지 않다.
    assert drop_contained(found, file_is_code=False) == found


def test_ask는_겹침을_빼고_모자라면_나머지_후보로_채운다():
    """재정렬이 한 클래스 안에서만 골라도 top_k칸을 서로 다른 근거로 채운다.

    재정렬이 12개를 골랐는데 대부분이 한 클래스의 메서드라 겹침을 빼면 몇 개만
    남던 경우다. 재정렬이 고른 것은 순서 그대로 앞에 둔다.
    """
    from vibecheck.services.qa import pick_distinct

    cls = chunk("class", 10, 300)
    methods = [chunk("method", 20 + i * 10, 25 + i * 10) for i in range(6)]
    others = [chunk("function", 1, 5, file=f"f{i}.py") for i in range(10)]
    picked = [cls, *methods, others[0]]
    candidates = [*methods, cls, *others]

    found = pick_distinct(picked, candidates, top_k=8)

    assert len(found) == 8
    assert found[:2] == [cls, others[0]]
    assert drop_contained(found) == found
