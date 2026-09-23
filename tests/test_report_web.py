"""리포트를 웹에서 보고 만드는 약속을 지킨다.

리포트는 whyd report가 WHYD_REPORT.md 파일로만 썼다. 웹 리포트 탭이 같은 파일을
읽고(GET, 요금 없음) 새로 만든다(POST, 레포 요약에 LLM 한 번). 두 가지를 확인한다.

1. GET은 만들지 않는다. 파일이 없으면 없다고만 하고 파일도 만들지 않는다.
2. POST로 만든 리포트는 CLI와 같은 파일에 저장되고, 다음 GET이 그것을 돌려준다.

리포트 재료(개요, 특이 지점)와 LLM은 가짜로 바꾼다.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibecheck.services.report import REPORT_FILENAME, report_path, scope_line
from vibecheck.web.app import app
from vibecheck.web.deps import get_index
from vibecheck.web.routers import report

REPORT = "# demo\n\n> **한 줄 요약**"


def test_scope_line_names_every_supported_language():
    """분석 범위 문장이 파이썬만이 아니라 지원 언어를 모두 적는다."""
    line = scope_line("분석하지 못한 파일 3개")

    assert "파이썬" in line
    assert "Java" in line
    assert "파이썬 파일만" not in line


def test_cli_and_web_share_the_report_file():
    """CLI와 웹이 같은 이름의 파일을 쓴다."""
    assert report_path(Path("/repo")) == Path("/repo") / REPORT_FILENAME
    assert REPORT_FILENAME == "WHYD_REPORT.md"


@pytest.fixture
def api(tmp_path, monkeypatch):
    """가짜 리포트 재료와 가짜 인덱스로 앱을 띄운다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포 경로로 쓴다.
        monkeypatch (pytest.MonkeyPatch): 라우터가 쓰는 이름을 바꿔 끼운다.

    Yields:
        tuple[TestClient, list, Path]: 클라이언트, 리포트를 만든 횟수 기록, 레포 경로.
    """
    made: list = []

    def fake_build(overview, chunks, llm, quirk_groups=None):
        """만든 횟수를 적어두고 정해진 리포트를 돌려준다."""
        made.append(True)
        return REPORT

    monkeypatch.setattr(report, "build_report", fake_build)
    monkeypatch.setattr(report, "build_overview", lambda *a, **k: None)
    monkeypatch.setattr(report, "collect_files", lambda *a, **k: [])
    monkeypatch.setattr(report, "find_quirks", lambda *a, **k: [])
    monkeypatch.setattr(report, "group_quirks", lambda *a, **k: [])
    monkeypatch.setattr(report, "AnthropicClient", lambda model: None)
    app.dependency_overrides[get_index] = lambda: ([], str(tmp_path), 0, {})

    yield TestClient(app), made, tmp_path

    app.dependency_overrides.clear()


def test_get_without_report_builds_nothing(api):
    """리포트가 없으면 없다고만 하고, 만들지도 파일을 쓰지도 않는다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 기록.
    """
    client, made, repo = api

    res = client.get("/api/report", params={"path": str(repo)})

    assert res.status_code == 200
    assert res.json()["markdown"] is None
    assert made == []
    assert not report_path(repo).exists()


def test_post_saves_report_that_get_returns(api):
    """POST로 만든 리포트가 파일에 저장되고, 다음 GET이 그대로 돌려준다.

    Args:
        api (tuple): 픽스처가 띄운 클라이언트와 기록.
    """
    client, made, repo = api

    created = client.post("/api/report", params={"path": str(repo)}).json()
    loaded = client.get("/api/report", params={"path": str(repo)}).json()

    assert created["saved"] is True
    assert report_path(repo).read_text(encoding="utf-8") == REPORT
    assert loaded["markdown"] == REPORT
    assert loaded["generated_at"]
    assert made == [True]
