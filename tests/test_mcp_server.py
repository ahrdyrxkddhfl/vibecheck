"""MCP 서버(whyd mcp)의 약속을 지킨다.

1. 채점 재료는 웹 채점과 같은 채점 프롬프트와 입력 메시지로 만든다.
2. 연결한 AI가 돌려준 채점 JSON은 웹과 같은 방식으로 읽고, 기록에 출처(mcp)를 남긴다.
3. 예상한 실패(인덱스 없음, 레포 경로 없음, 읽을 수 없는 JSON)는 할 일을 알려준다.
4. 면접 질문 번호는 웹 면접 탭과 같다.
5. 출처 칸이 없던 옛 기록 파일도 열면 칸이 생긴다.

인덱스와 검색은 가짜로 바꾼다. 임베딩 모델을 내려받지 않는다.
"""

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from vibecheck import mcp_server
from vibecheck.models import Chunk
from vibecheck.prompts import load_prompt
from vibecheck.services import index_access, interview
from vibecheck.services.history import load_history
from vibecheck.services.interview import STAGE_OVERVIEW, STAGE_STRUCTURE, Question
from vibecheck.store.records import connect

EVIDENCE = Chunk(
    file="app/grade.py", symbol="grade", kind="function",
    start_line=1, end_line=3, code="def grade(answer):\n    return len(answer)\n",
)

GRADED = json.dumps({
    "claims": [
        {"claim": "grade는 답의 길이를 돌려준다", "verdict": "confirmed", "hedged": False,
         "evidence": "app/grade.py:1-3", "note": ""},
        {"claim": "성능 때문에 이렇게 했다", "verdict": "unverifiable", "hedged": False,
         "evidence": None, "note": "코드에 이유가 없다"},
    ],
    "specificity": 2, "calibration": 1, "groundedness": 2,
    "verdict_line": "동작은 짚었지만 이유를 단정했다", "revision": "이유는 추측이라고 밝히세요",
})


def call(server, name: str, **arguments) -> dict:
    """도구를 서버 안에서 불러 결과 JSON을 돌려준다.

    Args:
        server: build_server가 만든 서버.
        name (str): 도구 이름.
        **arguments: 도구 인자.

    Returns:
        dict: 도구가 돌려준 값.
    """
    result = asyncio.run(server.call_tool(name, arguments))
    return json.loads(result.content[0].text)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """가짜 인덱스와 가짜 검색을 붙인 레포를 만든다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
        monkeypatch (pytest.MonkeyPatch): 인덱스와 검색을 바꿔 끼운다.

    Returns:
        Path: 레포 경로.
    """
    monkeypatch.setattr(index_access, "open_index", lambda repo: ([EVIDENCE], "/unused", 0, {}))
    monkeypatch.setattr(mcp_server, "evidence_for", lambda *a, **k: [EVIDENCE])
    return tmp_path


def test_grading_material_uses_the_web_grading_prompt(repo):
    """채점 재료는 웹 채점과 같은 프롬프트이고, 답은 채점 대상 데이터로 감싸진다.

    Args:
        repo (Path): 픽스처가 만든 레포.
    """
    server = mcp_server.build_server(repo)

    data = call(server, "grading_material", question="grade는 무엇을 하나요?", answer="길이를 센다")

    assert data["found"] is True
    assert data["instructions"] == load_prompt("grade_answer")
    assert "<user_answer>\n길이를 센다\n</user_answer>" in data["material"]
    assert data["evidence"] == ["app/grade.py:1-3 grade"]


def test_record_grade_saves_with_grader_mark(repo):
    """채점 결과가 기록에 남고, 연결한 AI가 채점했다는 표시가 붙는다.

    Args:
        repo (Path): 픽스처가 만든 레포.
    """
    server = mcp_server.build_server(repo)

    data = call(server, "record_grade", question="grade는 무엇을 하나요?",
                answer="길이를 센다. 성능 때문이다.", grading_json=GRADED)
    history = load_history(repo)

    assert data["saved"] is True
    assert data["total"] == 5
    assert data["risky_count"] == 1
    assert history["answers"][0]["grader"] == "mcp"
    assert history["answers"][0]["question"] == "grade는 무엇을 하나요?"


def test_unknown_verdict_becomes_unverifiable(repo):
    """모르는 판정은 웹 채점과 같이 확인 불가로 둔다.

    Args:
        repo (Path): 픽스처가 만든 레포.
    """
    odd = json.dumps({"claims": [{"claim": "x", "verdict": "probably"}],
                      "specificity": 9, "calibration": 0, "groundedness": 0})
    server = mcp_server.build_server(repo)

    data = call(server, "record_grade", question="q", answer="a", grading_json=odd)

    assert data["claims"][0]["verdict"] == "unverifiable"
    assert data["specificity"] == 2


def test_unreadable_json_explains_what_to_send(repo):
    """JSON이 아니면 무엇을 넘기면 되는지 알린다.

    Args:
        repo (Path): 픽스처가 만든 레포.
    """
    server = mcp_server.build_server(repo)

    with pytest.raises(ToolError, match="JSON만 grading_json"):
        call(server, "record_grade", question="q", answer="a", grading_json="잘했어요")


def test_missing_index_tells_how_to_index_without_key(tmp_path, monkeypatch):
    """인덱스가 없으면 키 없이 인덱싱하는 명령을 알린다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
        monkeypatch (pytest.MonkeyPatch): 인덱스 열기를 실패하게 바꾼다.
    """
    def missing(repo):
        """인덱스가 없는 것처럼 실패한다."""
        raise index_access.IndexNotFound(str(repo))

    monkeypatch.setattr(index_access, "open_index", missing)
    server = mcp_server.build_server(tmp_path)

    with pytest.raises(ToolError, match="--no-summary"):
        call(server, "search_code", query="grade")


def test_repo_is_required_without_default(repo):
    """기본 레포가 없는 서버는 도구마다 경로를 달라고 한다.

    Args:
        repo (Path): 픽스처가 만든 레포.
    """
    server = mcp_server.build_server(None)

    with pytest.raises(ToolError, match="레포 경로가 필요합니다"):
        call(server, "practice_history")

    assert call(server, "practice_history", repo=str(repo))["answer_count"] == 0


def test_interview_numbers_match_the_web_tab(repo, monkeypatch):
    """둘째 세트 번호가 첫 세트에 이어진다. 웹 면접 탭과 같은 번호다.

    Args:
        repo (Path): 픽스처가 만든 레포.
        monkeypatch (pytest.MonkeyPatch): 세트와 개요 재료를 바꿔 끼운다.
    """
    def q(stage, text):
        """테스트용 질문을 만든다."""
        return Question(stage=stage, text=text, answerable=True, can_say=[], risky=[])

    sets = [[q(STAGE_OVERVIEW, "Q1"), q(STAGE_STRUCTURE, "Q2")], [q(STAGE_STRUCTURE, "Q3")]]
    monkeypatch.setattr(interview, "question_sets", lambda *a, **k: sets)
    monkeypatch.setattr("vibecheck.core.overview.build_overview", lambda *a, **k: None)
    monkeypatch.setattr("vibecheck.core.collector.collect_files", lambda *a, **k: [])
    monkeypatch.setattr("vibecheck.core.quirks.find_quirks", lambda *a, **k: [])
    monkeypatch.setattr("vibecheck.core.quirks.group_quirks", lambda *a, **k: [])
    server = mcp_server.build_server(repo)

    data = call(server, "interview_questions", set_no=2)

    assert data["set_count"] == 2
    assert [x["no"] for x in data["questions"]] == [3]
    with pytest.raises(ToolError, match="1부터 2까지"):
        call(server, "interview_questions", set_no=3)


def test_old_records_get_grader_column(tmp_path):
    """출처 칸이 없던 옛 기록 파일도 열면 칸이 생기고, 옛 기록은 VibeCheck 채점으로 읽힌다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    path = tmp_path / ".vibecheck" / "records.db"
    path.parent.mkdir()
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE answers (
            id INTEGER PRIMARY KEY, repo_id INTEGER NOT NULL, question_id INTEGER,
            question_text TEXT NOT NULL, body TEXT NOT NULL, specificity INTEGER NOT NULL,
            calibration INTEGER NOT NULL, groundedness INTEGER NOT NULL,
            verdict_line TEXT, revision TEXT, created_at TEXT NOT NULL);
        INSERT INTO answers VALUES (1, 1, NULL, '옛 질문', '옛 답', 1, 1, 1, '', '', '2026-09-01T00:00:00');
    """)
    old.close()

    conn = connect(tmp_path)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(answers)")}
    grader = conn.execute("SELECT grader FROM answers WHERE id = 1").fetchone()["grader"]
    conn.close()

    assert "grader" in columns
    assert grader is None


def test_grading_includes_readme_and_build_files(repo):
    """채점 근거에 README와 빌드 설정 파일이 늘 들어가고, 비밀이 들 수 있는 설정은 빠진다.

    검색한 코드 조각만으로는 README에 적힌 설계 판단을 보지 못해, 지어낸 이유가
    레포와 어긋나는지 짚지 못했다.

    Args:
        repo (Path): 픽스처가 만든 레포.
    """
    (repo / "README.md").write_text("# 앱\n\nH2 인메모리 DB를 쓴다.\n", encoding="utf-8")
    (repo / "build.gradle").write_text("dependencies { implementation 'x' }\n", encoding="utf-8")
    (repo / "application.yml").write_text("password: secret\n", encoding="utf-8")
    server = mcp_server.build_server(repo)

    data = call(server, "grading_material", question="q", answer="확장성 때문입니다")

    assert "H2 인메모리 DB를 쓴다." in data["material"]
    assert "implementation 'x'" in data["material"]
    assert "secret" not in data["material"]
    assert data["evidence"][-2:] == ["README.md:1-3 README.md", "build.gradle:1-1 build.gradle"]
    assert data["coaching"] == load_prompt("coach_answer")


def test_previous_attempts_counts_earlier_answers(repo):
    """같은 질문에 전에 답한 횟수를 알려준다. 모범 답안을 보여줄지 정하는 재료다.

    Args:
        repo (Path): 픽스처가 만든 레포.
    """
    server = mcp_server.build_server(repo)

    first = call(server, "grading_material", question="grade는 무엇을 하나요?", answer="a")
    call(server, "record_grade", question="grade는 무엇을 하나요?", answer="a", grading_json=GRADED)
    second = call(server, "grading_material", question="grade는 무엇을 하나요?", answer="b")

    assert first["previous_attempts"] == 0
    assert second["previous_attempts"] == 1


def test_tools_are_listed():
    """여섯 도구가 모두 등록된다."""
    tools = asyncio.run(mcp_server.build_server(None).list_tools())

    assert {t.name for t in tools} == {
        "interview_questions", "grading_material", "record_grade",
        "search_code", "file_relations", "practice_history",
    }
