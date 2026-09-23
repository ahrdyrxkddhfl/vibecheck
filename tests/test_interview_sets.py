"""면접 질문 다음 세트가 정한 규칙대로 조립되는지 지킨다.

첫 세트는 whyd practice의 번호가 가리키므로 그대로여야 한다. 둘째 세트부터는
흐름(호출, 타입 참조), 라이브러리, 파일 역할 질문을 인덱스에서 조립한다.
각 질문의 "말할 수 있는 것"은 코드에서 확인되는 사실이어야 한다.

청크와 언어 설정은 가짜로 만든다. 질문이 좋은지는 실제 레포로 뽑아 사람이 읽는다
(vibecheck-tools/probe_question_sets.py).
"""

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from vibecheck.core.overview import RepoOverview
from vibecheck.services import interview


def chunk(file, symbol, kind="function", calls=(), imports=()):
    """테스트용 청크를 만든다.

    Args:
        file (str): 파일 경로.
        symbol (str): 심볼 이름.
        kind (str): 청크 종류.
        calls (tuple): 부르는 대상의 청크 id.
        imports (tuple): 파일 청크의 import 이름.

    Returns:
        SimpleNamespace: 청크 흉내.
    """
    return SimpleNamespace(
        id=f"{file}::{symbol}", file=file, symbol=symbol, kind=kind,
        calls=list(calls), imports=list(imports),
    )


PY = SimpleNamespace(
    dependency_of=lambda imp: (imp.split(".")[0], imp.split(".")[0] in {"os", "json"}),
    collect_type_refs=None,
    type_named_files=False,
)
"""파이썬 흉내. 첫 조각을 라이브러리 이름으로, os와 json을 표준으로 본다."""


@pytest.fixture(autouse=True)
def python_only(monkeypatch):
    """언어 설정을 파이썬 흉내로 고정한다.

    Args:
        monkeypatch (pytest.MonkeyPatch): interview 모듈의 이름을 바꿔 끼운다.
    """
    monkeypatch.setattr(interview, "spec_for", lambda path: PY)


def test_flow_asks_busiest_function_first_with_facts():
    """많이 부르고 불리는 함수부터 묻고, 부르는 함수와 부르는 곳을 사실로 싣는다."""
    chunks = [
        chunk("a.py", "grade", calls=["a.py::search", "a.py::parse"]),
        chunk("a.py", "search", calls=["a.py::parse", "b.py::embed"]),
        chunk("a.py", "parse"),
        chunk("b.py", "embed"),
        chunk("c.py", "run", calls=["a.py::grade", "a.py::search"]),
        chunk("c.py", "Store.__init__", kind="method", calls=["b.py::embed", "a.py::parse"]),
        chunk("c.py", "one", calls=["a.py::parse"]),
    ]

    questions = interview.flow_questions(chunks)
    texts = [q.text for q in questions]

    assert texts[0].startswith("`grade`") or texts[0].startswith("`search`")
    assert not any("__init__" in t for t in texts)
    assert not any(t.startswith("`one`") for t in texts)
    grade = next(q for q in questions if q.text.startswith("`grade`"))
    assert grade.can_say[0] == "부르는 함수: `parse`, `search`"
    assert grade.can_say[1] == "이 함수를 부르는 곳: `run`"


def test_dependency_questions_one_per_library():
    """라이브러리마다 질문 하나, import하는 파일을 싣고, 표준 라이브러리는 뺀다."""
    overview = RepoOverview(root="/r", name="r", external_deps=["chromadb", "httpx"])
    chunks = [
        chunk("a.py", "a.py", kind="file", imports=["chromadb", "os"]),
        chunk("b.py", "b.py", kind="file", imports=["chromadb.utils", "httpx"]),
    ]

    questions = interview.dependency_questions(overview, chunks)

    assert [q.text.split(" — ")[0] for q in questions] == ["`chromadb`", "`httpx`"]
    assert questions[0].can_say == ["import하는 파일: `a.py`, `b.py`"]
    assert "왜 이 라이브러리를 골랐는지는 코드에 없습니다" in questions[0].risky[0]


def test_type_questions_use_relations_neighbors(monkeypatch):
    """Java처럼 호출을 모으지 않는 언어는 관계도의 타입 참조로 묻는다.

    Args:
        monkeypatch (pytest.MonkeyPatch): 언어 설정과 타입 참조를 바꿔 끼운다.
    """
    java = SimpleNamespace(collect_type_refs=object(), type_named_files=True)
    monkeypatch.setattr(interview, "spec_for", lambda path: java)
    neighbors = {
        "src/EvidenceService.java": (Counter({"src/Controller.java": 2}), Counter({"src/Repo.java": 3})),
        "src/Repo.java": (Counter({"src/EvidenceService.java": 3}), Counter()),
        "src/Alone.java": (Counter(), Counter()),
    }
    monkeypatch.setattr(interview, "type_neighbors", lambda repo, chunks, file, spec: neighbors[file])
    chunks = [chunk(f, Path(f).stem, kind="file") for f in neighbors]

    questions = interview.type_questions(chunks, Path("/r"))

    assert [q.text.split(" — ")[0] for q in questions] == [
        "`EvidenceService` (src/EvidenceService.java)",
        "`Repo` (src/Repo.java)",
    ]
    assert questions[0].can_say == ["쓰는 클래스: `Repo`", "이 클래스를 쓰는 곳: `Controller`"]


def test_first_set_is_unchanged_and_later_sets_mix_kinds():
    """첫 세트는 build_questions 그대로, 뒤 세트는 흐름을 앞세워 다섯 개씩 섞는다."""
    overview = RepoOverview(
        root="/r", name="r", external_deps=["chromadb"],
        file_map=[("a.py", ""), ("b.py", ""), ("c.py", "")],
    )
    chunks = [
        chunk("a.py", "a.py", kind="file", imports=["chromadb"]),
        chunk("a.py", "grade", calls=["a.py::search", "a.py::parse"]),
        chunk("a.py", "search", calls=["a.py::parse", "b.py::embed"]),
        chunk("a.py", "parse"),
        chunk("b.py", "embed"),
        chunk("b.py", "load"),
        chunk("c.py", "run"),
    ]

    sets = interview.question_sets(overview, chunks, Path("/r"))

    assert [q.text for q in sets[0]] == [q.text for q in interview.build_questions(overview)]
    later = [q for s in sets[1:] for q in s]
    assert all(len(s) <= interview.SET_SIZE for s in sets[1:])
    assert later[0].text.startswith("`grade`") or later[0].text.startswith("`search`")
    assert later[1].text.startswith("`chromadb`")
    assert any(q.text.startswith("`b.py`") or q.text.startswith("`c.py`") for q in later)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/test/java/com/x/DomainTransitionTest.java", True),
        ("tests/test_report.py", True),
        ("vibecheck/services/report_test.py", True),
        ("src/main/java/com/x/ReviewService.java", False),
        ("vibecheck/services/contest.py", False),
    ],
)
def test_is_test_path(path, expected):
    """폴더 이름과 파일 이름 관례로 테스트 파일을 가른다.

    Args:
        path (str): 파일 경로.
        expected (bool): 테스트 파일인지.
    """
    assert interview.is_test_path(path) is expected


def test_test_files_are_not_asked_about():
    """테스트 파일은 흐름, 라이브러리, 파일 역할 질문의 대상에서 빠진다.

    테스트는 여러 클래스를 한꺼번에 써서 많이 엮인 순으로 고르면 맨 앞에 왔다.
    """
    overview = RepoOverview(
        root="/r", name="r", external_deps=["junit", "httpx"],
        file_map=[("tests/test_a.py", "긴 개요" * 50), ("a.py", "개요"), ("b.py", "짧음")],
    )
    chunks = [
        chunk("tests/test_a.py", "tests/test_a.py", kind="file", imports=["junit"]),
        chunk("a.py", "a.py", kind="file", imports=["httpx"]),
        chunk("tests/test_a.py", "test_all", calls=["a.py::run", "a.py::parse", "b.py::load"]),
        chunk("a.py", "run", calls=["a.py::parse", "b.py::load"]),
        chunk("a.py", "parse"),
        chunk("b.py", "load"),
    ]

    first = interview.build_questions(overview)
    later = [q for s in interview.question_sets(overview, chunks, Path("/r"))[1:] for q in s]
    texts = [q.text for q in first + later]

    assert not any("test" in t.split(" ")[0] for t in texts)
    assert any(t.startswith("`a.py`는") for t in texts)
    assert not any(t.startswith("`junit`") for t in texts)
    assert any(t.startswith("`httpx`") for t in texts)


def test_first_set_file_is_not_asked_again():
    """첫 세트가 역할을 물은 파일은 뒤 세트에서 다시 묻지 않는다.

    첫 세트는 개요 글이 가장 긴 파일을 고르는데, 뒤 세트는 심볼이 가장 많은 파일을
    뺐다. 둘이 달라 같은 질문이 두 번 나왔다.
    """
    overview = RepoOverview(
        root="/r", name="r",
        file_map=[("many.py", "짧음"), ("long.py", "아주 긴 개요" * 20)],
    )
    chunks = [chunk("many.py", f"f{i}") for i in range(5)] + [chunk("long.py", "g")]

    first_file = interview.main_file(overview)
    later = interview.file_questions(overview, chunks)

    assert first_file == "long.py"
    assert [q.text.split(" — ")[0] for q in later] == ["`many.py`"]
