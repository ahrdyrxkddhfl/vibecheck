"""웹 질문하기 API(/api/ask)의 약속을 지킨다.

LLM과 벡터 저장소는 가짜로 바꾼다. 확인하려는 것은 답의 품질이 아니라
화면과 맺은 약속이다. 응답 모양(답, 근거, 건너뛴 수, 저장 여부), 빈 질문은
LLM을 부르기 전에 걸러져 요금이 나가지 않는다는 것, 그리고 질문과 답이
기록에 남되 저장이 실패해도 답은 버려지지 않는다는 것이다.

기록은 픽스처가 레포로 쓰는 임시 폴더 안의 records.db에 실제로 쓴다.

인덱스를 여는 의존성(get_index)도 바꿔 끼운다. 실제 인덱스 없이 라우터만 본다.
"""

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from vibecheck.services.history import load_history
from vibecheck.web.app import app
from vibecheck.web.deps import get_index
from vibecheck.web.routers import ask


@pytest.fixture
def api(tmp_path, monkeypatch):
    """가짜 답변과 가짜 인덱스로 앱을 띄운다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포 경로로 쓴다.
        monkeypatch (pytest.MonkeyPatch): 라우터가 쓰는 이름을 바꿔 끼운다.

    Yields:
        tuple[TestClient, list[str], str]: 클라이언트, 답변 함수가 받은 질문 목록,
            레포 경로.
    """
    asked: list[str] = []

    def fake_answer(question, chunks, store, llm, top_k=8):
        """받은 질문을 적어두고 정해진 답을 돌려준다."""
        asked.append(question)
        source = SimpleNamespace(
            file="vibecheck/services/practice.py",
            start_line=218,
            end_line=259,
            symbol="grade",
        )
        return "## 채점 위치\n\n`grade`에서 합니다.", [source]

    monkeypatch.setattr(ask, "answer", fake_answer)
    monkeypatch.setattr(ask, "VectorStore", lambda persist_dir: None)
    monkeypatch.setattr(ask, "AnthropicClient", lambda model: None)
    app.dependency_overrides[get_index] = lambda: ([], str(tmp_path), 2, {})

    yield TestClient(app), asked, str(tmp_path)

    app.dependency_overrides.clear()


def test_ask_returns_answer_sources_and_stale_count(api):
    """답은 마크다운 그대로, 근거는 CLI와 같은 네 항목으로, 건너뛴 수와 함께 온다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 기록.
    """
    client, asked, repo = api

    res = client.post("/api/ask", params={"path": repo}, json={"question": "채점은 어디서?"})

    assert res.status_code == 200
    assert res.json() == {
        "question": "채점은 어디서?",
        "answer": "## 채점 위치\n\n`grade`에서 합니다.",
        "sources": [
            {
                "file": "vibecheck/services/practice.py",
                "start_line": 218,
                "end_line": 259,
                "symbol": "grade",
            }
        ],
        "stale_count": 2,
        "saved": True,
    }
    assert asked == ["채점은 어디서?"]


def test_ask_is_recorded_in_history(api):
    """질문과 답, 근거가 기록에 남고, 채점 누적에는 섞이지 않는다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 기록.
    """
    client, _, repo = api

    client.post("/api/ask", params={"path": repo}, json={"question": "채점은 어디서?"})
    history = load_history(Path(repo))

    assert history["ask_count"] == 1
    assert history["asks"][0]["question"] == "채점은 어디서?"
    assert history["asks"][0]["answer"].startswith("## 채점 위치")
    assert history["asks"][0]["sources"][0]["symbol"] == "grade"
    assert history["answer_count"] == 0
    assert history["tally"]["asserted"] == 0


def test_answer_without_sources_is_not_recorded(api, monkeypatch):
    """근거를 못 찾은 답은 남기지 않는다. 다시 볼 내용이 없다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 기록.
        monkeypatch (pytest.MonkeyPatch): 답변 함수를 근거 없는 답으로 바꾼다.
    """
    client, _, repo = api
    monkeypatch.setattr(
        ask, "answer", lambda *a, **k: ("관련된 코드를 찾지 못했습니다.", [])
    )

    res = client.post("/api/ask", params={"path": repo}, json={"question": "없는 것"})

    assert res.status_code == 200
    assert res.json()["saved"] is False
    assert load_history(Path(repo))["ask_count"] == 0


def test_answer_survives_failed_save(api, monkeypatch):
    """저장이 실패해도 이미 요금을 낸 답은 그대로 받는다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 기록.
        monkeypatch (pytest.MonkeyPatch): 저장 함수를 실패하게 바꾼다.
    """
    client, _, repo = api

    def broken_save(*args, **kwargs):
        """디스크가 잠긴 것처럼 실패한다."""
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ask, "save_ask", broken_save)

    res = client.post("/api/ask", params={"path": repo}, json={"question": "채점은 어디서?"})

    assert res.status_code == 200
    assert res.json()["answer"].startswith("## 채점 위치")
    assert res.json()["saved"] is False


def test_empty_question_is_rejected_before_llm(api):
    """빈 질문은 스키마에서 걸러져 답변 함수까지 가지 않는다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 기록.
    """
    client, asked, repo = api

    res = client.post("/api/ask", params={"path": repo}, json={"question": ""})

    assert res.status_code == 422
    assert asked == []


def test_ask_is_post_only(api):
    """GET으로는 답하지 않는다. 새로고침이나 미리 읽기로 요금이 나가지 않게.

    상태 번호는 405가 아니라 404다. app.py가 정적 파일을 맨 끝에 루트로
    마운트해, 메서드만 다른 요청은 정적 파일 쪽이 "없는 파일"로 받는다.
    지키려는 것은 번호가 아니라 답변 함수가 불리지 않는다는 것이다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 기록.
    """
    client, asked, repo = api

    res = client.get("/api/ask", params={"path": repo})

    assert res.status_code != 200
    assert asked == []
