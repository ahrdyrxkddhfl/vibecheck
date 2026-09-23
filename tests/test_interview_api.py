"""면접 질문 API가 세트를 나눠 주고 답한 질문을 알려주는지 지킨다.

첫 세트는 whyd practice의 번호와 맞아야 하므로 1번부터, 뒤 세트는 앞 세트에
이어서 번호를 매긴다. 채점받은 질문에는 answered를 싣는다.

질문 세트와 개요 재료는 가짜로 바꾼다. 세트를 만드는 규칙은 test_interview_sets가 본다.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from vibecheck.services.interview import STAGE_OVERVIEW, STAGE_STRUCTURE, Question
from vibecheck.store.records import connect, get_repo_id, save_answer
from vibecheck.web.app import app
from vibecheck.web.deps import get_index
from vibecheck.web.routers import report


def question(stage: str, text: str) -> Question:
    """테스트용 질문을 만든다.

    Args:
        stage (str): 면접 단계.
        text (str): 질문 문장.

    Returns:
        Question: 질문.
    """
    return Question(stage=stage, text=text, answerable=True, can_say=[], risky=[])


SETS = [
    [question(STAGE_OVERVIEW, "Q1"), question(STAGE_STRUCTURE, "Q2")],
    [question(STAGE_STRUCTURE, "Q3"), question(STAGE_STRUCTURE, "Q4"), question(STAGE_STRUCTURE, "Q5")],
]


@pytest.fixture
def api(tmp_path, monkeypatch):
    """가짜 세트와 가짜 인덱스로 앱을 띄운다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포 경로로 쓴다.
        monkeypatch (pytest.MonkeyPatch): 라우터가 쓰는 이름을 바꿔 끼운다.

    Yields:
        tuple[TestClient, Path]: 클라이언트와 레포 경로.
    """
    monkeypatch.setattr(report, "question_sets", lambda *a, **k: SETS)
    monkeypatch.setattr(report, "build_overview", lambda *a, **k: None)
    monkeypatch.setattr(report, "collect_files", lambda *a, **k: [])
    monkeypatch.setattr(report, "find_quirks", lambda *a, **k: [])
    monkeypatch.setattr(report, "group_quirks", lambda *a, **k: [])
    app.dependency_overrides[get_index] = lambda: ([], str(tmp_path), 0, {})

    yield TestClient(app), tmp_path

    app.dependency_overrides.clear()


def numbers(data: dict) -> list[int]:
    """응답에서 질문 번호를 순서대로 꺼낸다.

    Args:
        data (dict): /api/interview 응답.

    Returns:
        list[int]: 번호 목록.
    """
    return [q["no"] for s in data["stages"] for q in s["questions"]]


def test_first_set_by_default_numbered_from_one(api):
    """세트를 고르지 않으면 첫 세트이고, 번호는 1부터다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 레포 경로.
    """
    client, repo = api

    data = client.get("/api/interview", params={"path": str(repo)}).json()

    assert data["set"] == 1
    assert data["set_count"] == 2
    assert data["total"] == 2
    assert numbers(data) == [1, 2]


def test_later_set_continues_numbering(api):
    """뒤 세트는 앞 세트에 이어 번호를 매긴다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 레포 경로.
    """
    client, repo = api

    data = client.get("/api/interview", params={"path": str(repo), "set": 2}).json()

    assert data["set"] == 2
    assert data["total"] == 3
    assert numbers(data) == [3, 4, 5]


def test_unknown_set_is_404(api):
    """없는 세트 번호는 몇 번까지 있는지 알려주며 404로 끝난다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 레포 경로.
    """
    client, repo = api

    res = client.get("/api/interview", params={"path": str(repo), "set": 3})

    assert res.status_code == 404
    assert "1부터 2까지" in res.json()["detail"]


def test_answered_questions_are_marked(api):
    """채점받은 질문에만 answered가 붙고, 답한 수가 세어진다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 레포 경로.
    """
    client, repo = api
    conn = connect(repo)
    feedback = SimpleNamespace(
        question="Q4", user_answer="답", specificity=1, calibration=1, groundedness=1,
        verdict_line=None, revision=None, claims=[],
    )
    save_answer(conn, get_repo_id(conn, repo), feedback)
    conn.close()

    data = client.get("/api/interview", params={"path": str(repo), "set": 2}).json()
    flags = {q["text"]: q["answered"] for s in data["stages"] for q in s["questions"]}

    assert flags == {"Q3": False, "Q4": True, "Q5": False}
    assert data["answered_count"] == 1
