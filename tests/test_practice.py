"""채점 근거를 줄이는 compact_file_chunk의 테스트.

줄이다가 채점에 필요한 것을 떨어뜨리면 사실을 말한 사용자가 다시
확인불가를 받는다. 개요에 무엇이 남아야 하는지를 여기서 고정한다.
"""

from vibecheck.models import Chunk
from vibecheck.services.practice import compact_file_chunk

SOURCE = '''"""채점 라우터.

긴 설명.
"""

from vibecheck.store.records import save_answer


def post_practice():
    """채점하고 저장한다."""
    body = "함수 본문은 개요에 실리지 않아야 한다"
    save_answer(body)
'''


def sample() -> list[Chunk]:
    """원문이 코드 자리에 들어간 파일 청크와, 그 파일의 함수 하나."""
    file_chunk = Chunk(
        file="web/report.py",
        symbol="web/report.py",
        kind="file",
        start_line=1,
        end_line=13,
        code=SOURCE,
        imports=["vibecheck.store.records"],
    )
    func = Chunk(
        file="web/report.py",
        symbol="post_practice",
        kind="function",
        start_line=10,
        end_line=13,
        code="",
        summary="채점하고 저장한다.",
        calls=["store/records.py::save_answer"],
    )
    return [file_chunk, func]


def test_body_is_dropped_but_imports_and_calls_remain():
    """함수 본문은 빠지고, import 목록과 호출 목록은 남는다.

    호출 목록이 빠지면 "post_practice가 save_answer를 부른다"를 확인할 수 없다.
    측정에서 개요만 넣었을 때 세 판 모두 그랬다.
    """
    chunks = sample()
    out = compact_file_chunk(chunks[0], chunks).code

    assert "함수 본문은 개요에 실리지 않아야 한다" not in out
    assert "vibecheck.store.records" in out
    assert "post_practice -> store/records.py::save_answer" in out


def test_module_docstring_is_kept():
    """모듈 독스트링이 파일 설명으로 남는다. 무슨 파일인지 먼저 읽혀야 한다."""
    chunks = sample()

    assert "채점 라우터." in compact_file_chunk(chunks[0], chunks).code


def test_non_file_chunks_pass_through():
    """함수 청크는 건드리지 않는다. 함수 본문은 채점의 가장 직접적인 근거다."""
    chunks = sample()

    assert compact_file_chunk(chunks[1], chunks) is chunks[1]


def test_non_python_file_chunks_pass_through():
    """pyproject.toml처럼 파이썬이 아닌 파일 청크는 그대로 둔다."""
    toml = Chunk(
        file="pyproject.toml", symbol="pyproject.toml", kind="file",
        start_line=1, end_line=3, code="[project]\nname = 'x'\n",
    )

    assert compact_file_chunk(toml, [toml]) is toml
