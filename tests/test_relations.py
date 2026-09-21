"""관계도 재료를 조립하는 file_relations의 테스트.

화면에서 틀리면 사용자는 없는 호출 관계를 믿게 된다. 그림은 눈으로 확인하기
어려우므로 방향(부름과 불림)과 제외 규칙을 여기서 고정한다.
"""

from vibecheck.models import Chunk
from vibecheck.services.relations import file_relations


def make(file: str, symbol: str, calls: list[str] | None = None, line: int = 1) -> Chunk:
    """테스트용 함수 청크를 만든다."""
    return Chunk(
        file=file,
        symbol=symbol,
        kind="function",
        start_line=line,
        end_line=line + 1,
        code="",
        calls=calls or [],
    )


def sample() -> list[Chunk]:
    """cli가 service를 부르고, service가 core 둘을 부르는 작은 레포.

    service.py 안에서도 한 번 서로 부른다. 같은 파일 안 호출이 이웃 집계에서
    빠지는지 보기 위해서다.
    """
    return [
        make("cli.py", "main", ["service.py::run"]),
        make("service.py", "run", ["core.py::load", "core.py::save", "service.py::helper"], line=1),
        make("service.py", "helper", ["util.py::fmt"], line=10),
        make("core.py", "load"),
        make("core.py", "save"),
        make("util.py", "fmt"),
        Chunk(file="service.py", symbol="service.py", kind="file", start_line=1, end_line=20, code=""),
    ]


def test_direction_of_neighbor_files():
    """부르는 쪽과 불리는 쪽이 뒤바뀌지 않는다."""
    rel = file_relations(sample(), "service.py")

    assert [n["file"] for n in rel["called_by"]] == ["cli.py"]
    assert [n["file"] for n in rel["calls"]] == ["core.py", "util.py"]


def test_neighbors_sorted_by_count():
    """많이 엮인 파일이 앞에 온다. 화면이 뒤를 접으므로 약한 연결이 가려져야 한다."""
    rel = file_relations(sample(), "service.py")

    assert rel["calls"][0] == {"file": "core.py", "count": 2}


def test_same_file_calls_excluded_from_neighbors_but_kept_in_symbols():
    """같은 파일 안 호출은 이웃 그림에서 빠지고 심볼 목록에는 남는다."""
    rel = file_relations(sample(), "service.py")

    assert all(n["file"] != "service.py" for n in rel["calls"])
    run = next(s for s in rel["symbols"] if s["symbol"] == "run")
    assert "service.py::helper" in run["calls"]
    helper = next(s for s in rel["symbols"] if s["symbol"] == "helper")
    assert helper["called_by"] == ["service.py::run"]


def test_symbols_in_line_order_and_file_chunk_excluded():
    """심볼은 줄 순서이고, 파일 단위 청크는 심볼로 끼지 않는다."""
    rel = file_relations(sample(), "service.py")

    assert [s["symbol"] for s in rel["symbols"]] == ["run", "helper"]


def test_unknown_file_returns_none():
    """함수·클래스가 없는 파일은 None이다. 화면이 404로 안내할 수 있게 한다."""
    assert file_relations(sample(), "nope.py") is None
