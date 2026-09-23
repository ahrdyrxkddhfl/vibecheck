"""질문 이어가기의 약속을 지킨다.

이어지는 질문("그거 지우는 기능도 있어?")은 앞을 가리켜 그것만으로는 검색 단서도,
무엇을 묻는지도 없다. 세 가지를 확인한다.

1. 검색에는 직전 질문을 붙이고, 답변에는 앞선 대화를 붙인다. 직전 턴만 답까지 싣는다.
2. 앞 대화는 화면이 보내지 않고 서버가 기록에서 parent_id를 따라 불러온다.
3. 이어가기 전에 만든 records.db도 열면 parent_id 칸이 생긴다.

LLM과 벡터 저장소는 가짜로 바꾼다. 확인하려는 것은 무엇을 모델에 넘기느냐다.
"""

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from vibecheck.services import qa
from vibecheck.services.history import load_history
from vibecheck.store.records import (
    connect,
    db_path,
    get_ask_chain,
    get_repo_id,
    list_asks,
    save_ask,
)
from vibecheck.web.app import app
from vibecheck.web.deps import get_index
from vibecheck.web.routers import ask

SOURCE = {"file": "vibecheck/store/records.py", "start_line": 1, "end_line": 9, "symbol": "save_ask"}


# ---------- 기록 ----------


def test_old_asks_table_gets_parent_id(tmp_path):
    """parent_id 칸이 없던 asks 테이블도 열면 칸이 생기고, 기존 기록은 남는다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포로 쓴다.
    """
    path = db_path(tmp_path)
    path.parent.mkdir(parents=True)
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE repos (id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);"
        "CREATE TABLE asks (id INTEGER PRIMARY KEY, repo_id INTEGER NOT NULL, question TEXT NOT NULL,"
        " answer TEXT NOT NULL, sources TEXT NOT NULL, created_at TEXT NOT NULL);"
        "INSERT INTO repos VALUES (1, 'x', 't');"
        "INSERT INTO asks VALUES (1, 1, '옛 질문', '옛 답', '[]', '2026-09-22');"
    )
    old.commit()
    old.close()

    conn = connect(tmp_path)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(asks)")}
    row = conn.execute("SELECT question, parent_id FROM asks WHERE id = 1").fetchone()
    conn.close()

    assert "parent_id" in columns
    assert row["question"] == "옛 질문"
    assert row["parent_id"] is None


def test_ask_chain_goes_back_oldest_first_within_limit(tmp_path):
    """앞 질문을 거슬러 올라가 오래된 것부터 돌려주고, limit에서 멈춘다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포로 쓴다.
    """
    conn = connect(tmp_path)
    repo_id = get_repo_id(conn, tmp_path)
    first = save_ask(conn, repo_id, "Q1", "A1", [SOURCE])
    second = save_ask(conn, repo_id, "Q2", "A2", [SOURCE], parent_id=first)
    third = save_ask(conn, repo_id, "Q3", "A3", [SOURCE], parent_id=second)

    assert [r["question"] for r in get_ask_chain(conn, repo_id, third, 10)] == ["Q1", "Q2", "Q3"]
    assert [r["question"] for r in get_ask_chain(conn, repo_id, third, 2)] == ["Q2", "Q3"]
    assert get_ask_chain(conn, repo_id, 999, 10) == []

    rows = list_asks(conn, repo_id)
    conn.close()
    assert rows[0]["parent_question"] == "Q2"
    assert rows[-1]["parent_question"] is None


# ---------- 답변에 넘기는 것 ----------


@pytest.fixture
def captured(monkeypatch):
    """검색과 재정렬을 가짜로 바꾸고, 검색어와 모델에 넘긴 글을 받아 둔다.

    Args:
        monkeypatch (pytest.MonkeyPatch): qa 모듈의 이름을 바꿔 끼운다.

    Returns:
        dict: "queries"(검색어 목록)와 "user"(모델에 넘긴 사용자 메시지).
    """
    seen = {"queries": [], "user": None}
    chunk = SimpleNamespace(id="c", file="vibecheck/store/records.py")

    def fake_search(query, chunks, store, top_k):
        """검색어를 적어두고 청크 하나를 돌려준다."""
        seen["queries"].append(query)
        return [chunk]

    monkeypatch.setattr(qa, "search_by_kind", fake_search)
    monkeypatch.setattr(qa, "rerank", lambda query, candidates, llm, k: candidates)
    monkeypatch.setattr(qa, "pick_distinct", lambda picked, candidates, k: picked)
    monkeypatch.setattr(qa, "find_callers", lambda query, chunks: {})
    monkeypatch.setattr(qa, "build_context", lambda found: "(코드)")

    class FakeLLM:
        """받은 사용자 메시지를 적어두는 가짜 모델."""

        def complete(self, system, user, max_tokens=1024):
            """받은 글을 적어두고 정해진 답을 돌려준다."""
            seen["user"] = user
            return "답"

    seen["llm"] = FakeLLM()
    return seen


def test_first_question_has_no_history(captured):
    """첫 질문은 그대로 검색하고, 앞선 대화를 붙이지 않는다.

    Args:
        captured (dict): 검색어와 모델에 넘긴 글.
    """
    qa.answer("질문 기록은 어디에 저장돼?", [], None, captured["llm"])

    assert captured["queries"] == ["질문 기록은 어디에 저장돼?"]
    assert "앞선 대화" not in captured["user"]


def test_followup_joins_previous_question_and_carries_last_answer_only(captured):
    """검색에는 직전 질문을 붙이고, 답변에는 직전 턴만 답까지 싣는다.

    Args:
        captured (dict): 검색어와 모델에 넘긴 글.
    """
    history = [
        {"question": "Q1 오래된 질문", "answer": "A1 오래된 답"},
        {"question": "질문 기록은 어디에 저장돼?", "answer": "asks 테이블에 저장됩니다."},
    ]

    qa.answer("그거 지우는 기능도 있어?", [], None, captured["llm"], history=history)

    assert captured["queries"] == ["질문 기록은 어디에 저장돼? 그거 지우는 기능도 있어?"]
    user = captured["user"]
    assert "사실의 근거로 쓰지 않습니다" in user
    assert "이전 질문: Q1 오래된 질문" in user
    assert "A1 오래된 답" not in user
    assert "직전 질문: 질문 기록은 어디에 저장돼?" in user
    assert "asks 테이블에 저장됩니다." in user
    assert user.index("앞선 대화") < user.index("질문: 그거 지우는 기능도 있어?")


def test_answer_prompt_says_history_is_not_evidence():
    """답변 프롬프트에 앞 답은 근거가 아니라는 규칙이 있다."""
    prompt = qa.load_prompt("answer_question")

    assert "사실의 근거는 이번에 주어진 코드 조각뿐입니다" in prompt
    assert "앞선 답변이 이번 코드 조각과 어긋나면" in prompt


# ---------- API ----------


@pytest.fixture
def api(tmp_path, monkeypatch):
    """가짜 답변과 가짜 인덱스로 앱을 띄운다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포 경로로 쓴다.
        monkeypatch (pytest.MonkeyPatch): 라우터가 쓰는 이름을 바꿔 끼운다.

    Yields:
        tuple[TestClient, list, str]: 클라이언트, 답변 함수가 받은 앞선 대화 목록, 레포 경로.
    """
    histories: list = []

    def fake_answer(question, chunks, store, llm, top_k=8, history=None):
        """받은 앞선 대화를 적어두고 근거가 있는 답을 돌려준다."""
        histories.append(history)
        src = SimpleNamespace(**SOURCE)
        return f"{question}에 대한 답", [src]

    monkeypatch.setattr(ask, "answer", fake_answer)
    monkeypatch.setattr(ask, "VectorStore", lambda persist_dir: None)
    monkeypatch.setattr(ask, "AnthropicClient", lambda model: None)
    app.dependency_overrides[get_index] = lambda: ([], str(tmp_path), 0, {})

    yield TestClient(app), histories, str(tmp_path)

    app.dependency_overrides.clear()


def post(client, repo, question, parent_id=None):
    """질문 하나를 보낸다.

    Args:
        client (TestClient): 클라이언트.
        repo (str): 레포 경로.
        question (str): 질문.
        parent_id (int | None): 이어서 묻는 앞 질문의 id.

    Returns:
        Response: 응답.
    """
    body = {"question": question}
    if parent_id is not None:
        body["parent_id"] = parent_id
    return client.post("/api/ask", params={"path": repo}, json=body)


def test_followup_loads_history_from_records(api):
    """이어지는 질문은 서버가 기록에서 앞 대화를 불러와 넘기고, 이어진 채로 남긴다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 기록.
    """
    client, histories, repo = api

    first = post(client, repo, "질문 기록은 어디에 저장돼?").json()
    second = post(client, repo, "그거 지우는 기능도 있어?", parent_id=first["id"]).json()

    assert histories[0] == []
    assert histories[1] == [
        {"question": "질문 기록은 어디에 저장돼?", "answer": "질문 기록은 어디에 저장돼?에 대한 답"}
    ]
    assert second["parent_id"] == first["id"]
    assert second["id"] != first["id"]

    latest = load_history(Path(repo))["asks"][0]
    assert latest["parent_id"] == first["id"]
    assert latest["parent_question"] == "질문 기록은 어디에 저장돼?"


def test_unknown_parent_stops_before_llm(api):
    """없는 앞 질문에 이어 물으면 LLM을 부르기 전에 404로 끝난다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 기록.
    """
    client, histories, repo = api

    res = post(client, repo, "그거 지우는 기능도 있어?", parent_id=42)

    assert res.status_code == 404
    assert histories == []
