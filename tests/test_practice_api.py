"""웹 채점 API(/api/practice)가 기록과 맺은 약속을 지킨다.

채점은 기록에 남고, 저장이 실패해도 이미 요금을 낸 채점 결과는 버려지지
않는다. 예전에는 저장 예외가 그대로 올라가 결과까지 500으로 사라졌다.

채점 함수와 LLM, 벡터 저장소는 가짜로 바꾼다. 확인하려는 것은 채점의 내용이
아니라 저장 실패를 어떻게 다루느냐다. 기록은 임시 폴더의 records.db에 실제로 쓴다.
"""

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from vibecheck.services.history import load_history
from vibecheck.web.app import app
from vibecheck.web.deps import get_index
from vibecheck.web.routers import report


def fake_feedback(question: str, answer: str) -> SimpleNamespace:
    """save_answer와 라우터가 읽는 항목만 갖춘 채점 결과를 만든다.

    Args:
        question (str): 채점한 질문.
        answer (str): 사용자 답변.

    Returns:
        SimpleNamespace: AnswerFeedback 흉내.
    """
    claim = SimpleNamespace(
        claim="grade가 채점한다",
        verdict="confirmed",
        hedged=False,
        evidence="vibecheck/services/practice.py",
        note=None,
    )
    return SimpleNamespace(
        question=question,
        user_answer=answer,
        specificity=2,
        calibration=2,
        groundedness=1,
        total=5,
        claims=[claim],
        risky_claims=[],
        verdict_line="대체로 근거가 있습니다.",
        revision=None,
        evidence_chunks=[],
    )


@pytest.fixture
def api(tmp_path, monkeypatch):
    """가짜 채점과 가짜 인덱스로 앱을 띄운다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포 경로로 쓴다.
        monkeypatch (pytest.MonkeyPatch): 라우터가 쓰는 이름을 바꿔 끼운다.

    Yields:
        tuple[TestClient, str]: 클라이언트와 레포 경로.
    """
    monkeypatch.setattr(
        report, "grade", lambda question, answer, *a, **k: fake_feedback(question, answer)
    )
    monkeypatch.setattr(report, "VectorStore", lambda persist_dir: None)
    monkeypatch.setattr(report, "AnthropicClient", lambda model: None)
    app.dependency_overrides[get_index] = lambda: ([], str(tmp_path), 0, {})

    yield TestClient(app), str(tmp_path)

    app.dependency_overrides.clear()


def test_practice_is_recorded(api):
    """채점 결과가 기록에 남고, 응답은 남았다고 알린다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 레포 경로.
    """
    client, repo = api

    res = client.post(
        "/api/practice",
        params={"path": repo},
        json={"question": "채점은 어디서?", "answer": "grade에서 합니다."},
    )

    assert res.status_code == 200
    assert res.json()["total"] == 5
    assert res.json()["saved"] is True
    assert load_history(Path(repo))["answer_count"] == 1


def test_grading_survives_failed_save(api, monkeypatch):
    """저장이 실패해도 이미 요금을 낸 채점 결과는 그대로 받는다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 레포 경로.
        monkeypatch (pytest.MonkeyPatch): 저장 함수를 실패하게 바꾼다.
    """
    client, repo = api

    def broken_save(*args, **kwargs):
        """디스크가 잠긴 것처럼 실패한다."""
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(report, "save_answer", broken_save)

    res = client.post(
        "/api/practice",
        params={"path": repo},
        json={"question": "채점은 어디서?", "answer": "grade에서 합니다."},
    )

    assert res.status_code == 200
    assert res.json()["total"] == 5
    assert res.json()["saved"] is False
