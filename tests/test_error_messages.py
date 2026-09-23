"""원인을 아는 실패가 사용자가 할 일을 담은 안내로 바뀌는지 지킨다.

2026-09-23에 두 실패가 모두 웹에서 "요청 실패 (500)"로만 떴다. 서버를 켠 채로
다시 인덱싱해 벡터 저장소가 어긋난 경우와, Anthropic API 사용 한도에 걸린 경우다.
할 일이 서로 다른데 화면으로는 구분할 수 없었다.

API는 부르지 않는다. SDK 예외는 생성자 모양이 버전마다 달라, 생성자를 거치지 않고
안내에 쓰는 속성(상태 코드, 응답 몸통)만 채운 진짜 예외 객체를 만든다.
"""

import sys
from types import SimpleNamespace

import anthropic
import pytest
from chromadb.errors import InternalError as ChromaInternalError
from fastapi.testclient import TestClient

from vibecheck import cli
from vibecheck.llm.errors import MissingAPIKey, describe_llm_error
from vibecheck.web.app import app
from vibecheck.web.deps import get_index
from vibecheck.web.errors import STALE_STORE_MESSAGE
from vibecheck.web.routers import ask

USAGE_LIMIT = (
    "You have reached your specified API usage limits. "
    "You will regain access on 2026-10-01 at 00:00 UTC."
)
"""2026-09-23에 실제로 받은 사용 한도 메시지."""


def status_error(status: int, message: str, cls=anthropic.APIStatusError):
    """상태 코드가 있는 SDK 예외를 만든다.

    Args:
        status (int): HTTP 상태 코드.
        message (str): 응답 몸통의 error.message.
        cls (type): 만들 예외 클래스. APIStatusError나 그 하위.

    Returns:
        anthropic.APIStatusError: 안내에 쓰는 속성이 채워진 예외.
    """
    exc = cls.__new__(cls)
    Exception.__init__(exc, f"Error code: {status}")
    exc.message = f"Error code: {status}"
    exc.status_code = status
    exc.body = {"type": "error", "error": {"type": "error", "message": message}}
    return exc


def connection_error():
    """네트워크 연결 실패 예외를 만든다.

    Returns:
        anthropic.APIConnectionError: 연결 실패 예외.
    """
    exc = anthropic.APIConnectionError.__new__(anthropic.APIConnectionError)
    Exception.__init__(exc, "Connection error.")
    exc.message = "Connection error."
    return exc


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (status_error(400, USAGE_LIMIT, anthropic.BadRequestError), "사용 한도"),
        (status_error(401, "invalid x-api-key"), "API 키가 올바르지 않습니다"),
        (status_error(429, "rate limited"), "요청이 너무 잦아"),
        (status_error(529, "Overloaded"), "일시적으로 응답하지 못했습니다"),
        (status_error(418, "teapot"), "상태 418"),
        (connection_error(), "연결하지 못했습니다"),
        (MissingAPIKey("ANTHROPIC_API_KEY가 설정되지 않았습니다."), "ANTHROPIC_API_KEY"),
    ],
)
def test_describe_llm_error(exc, expected):
    """오류 종류마다 할 일이 다른 안내가 나온다.

    Args:
        exc (BaseException): 잡은 예외.
        expected (str): 안내에 들어 있어야 할 말.
    """
    assert expected in describe_llm_error(exc)


def test_usage_limit_keeps_resume_time():
    """사용 한도 안내는 API가 알려준 재개 시각을 그대로 싣는다."""
    exc = status_error(400, USAGE_LIMIT, anthropic.BadRequestError)
    assert "2026-10-01" in describe_llm_error(exc)


def test_unknown_error_is_not_described():
    """LLM 오류가 아니면 안내하지 않는다. 모르는 것을 아는 것처럼 말하지 않게."""
    assert describe_llm_error(ValueError("다른 실수")) is None


@pytest.fixture
def client(tmp_path, monkeypatch):
    """가짜 인덱스로 앱을 띄운다. 답변 함수는 테스트마다 바꿔 끼운다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포 경로로 쓴다.
        monkeypatch (pytest.MonkeyPatch): 라우터가 쓰는 이름을 바꿔 끼운다.

    Yields:
        tuple[TestClient, str]: 클라이언트와 레포 경로.
    """
    monkeypatch.setattr(ask, "VectorStore", lambda persist_dir: None)
    monkeypatch.setattr(ask, "AnthropicClient", lambda model: None)
    app.dependency_overrides[get_index] = lambda: ([], str(tmp_path), 0, {})

    yield TestClient(app, raise_server_exceptions=False), str(tmp_path)

    app.dependency_overrides.clear()


def raising(exc: BaseException):
    """부르면 exc를 던지는 함수를 만든다.

    Args:
        exc (BaseException): 던질 예외.

    Returns:
        Callable: 어떤 인자든 받고 exc를 던지는 함수.
    """
    def fail(*args, **kwargs):
        """정해진 예외를 던진다."""
        raise exc

    return fail


def ask_once(client_and_repo) -> "object":
    """질문 하나를 보낸다.

    Args:
        client_and_repo (tuple): 픽스처가 띄운 클라이언트와 레포 경로.

    Returns:
        Response: 응답.
    """
    client, repo = client_and_repo
    return client.post("/api/ask", params={"path": repo}, json={"question": "채점은 어디서?"})


def test_web_usage_limit_is_explained(client, monkeypatch):
    """사용 한도에 걸리면 500이 아니라 502와 할 일이 담긴 안내가 온다.

    Args:
        client (tuple): 픽스처가 띄운 클라이언트와 레포 경로.
        monkeypatch (pytest.MonkeyPatch): 답변 함수를 바꿔 끼운다.
    """
    monkeypatch.setattr(
        ask, "answer", raising(status_error(400, USAGE_LIMIT, anthropic.BadRequestError))
    )

    res = ask_once(client)

    assert res.status_code == 502
    assert "사용 한도" in res.json()["detail"]


def test_web_missing_key_is_explained(client, monkeypatch):
    """키가 없으면 500이되, 무엇을 확인하라는 안내가 온다.

    Args:
        client (tuple): 픽스처가 띄운 클라이언트와 레포 경로.
        monkeypatch (pytest.MonkeyPatch): 클라이언트 생성을 실패하게 바꾼다.
    """
    monkeypatch.setattr(
        ask, "AnthropicClient", raising(MissingAPIKey("ANTHROPIC_API_KEY가 설정되지 않았습니다."))
    )

    res = ask_once(client)

    assert res.status_code == 500
    assert "ANTHROPIC_API_KEY" in res.json()["detail"]


def test_web_stale_store_is_explained(client, monkeypatch):
    """벡터 저장소 내부 오류는 서버를 다시 띄우라는 안내로 바뀐다.

    Args:
        client (tuple): 픽스처가 띄운 클라이언트와 레포 경로.
        monkeypatch (pytest.MonkeyPatch): 답변 함수를 바꿔 끼운다.
    """
    monkeypatch.setattr(
        ask, "answer",
        raising(ChromaInternalError("Error executing plan: Internal error: Error finding id")),
    )

    res = ask_once(client)

    assert res.status_code == 503
    assert res.json()["detail"] == STALE_STORE_MESSAGE


def test_web_unknown_error_stays_500(client, monkeypatch):
    """모르는 예외는 안내를 붙이지 않고 500으로 둔다.

    Args:
        client (tuple): 픽스처가 띄운 클라이언트와 레포 경로.
        monkeypatch (pytest.MonkeyPatch): 답변 함수를 바꿔 끼운다.
    """
    monkeypatch.setattr(ask, "answer", raising(RuntimeError("모르는 실패")))

    res = ask_once(client)

    assert res.status_code == 500


def test_cli_usage_limit_prints_one_line(tmp_path, monkeypatch, capsys):
    """CLI는 트레이스백 대신 안내 한 줄을 오류 출력에 찍고 1로 끝난다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포 경로로 쓴다.
        monkeypatch (pytest.MonkeyPatch): 인덱스와 답변 함수를 바꿔 끼운다.
        capsys (pytest.CaptureFixture): 출력을 받는다.
    """
    monkeypatch.setattr(cli, "open_or_exit", lambda repo: ([], str(tmp_path), {}))
    monkeypatch.setattr(cli, "VectorStore", lambda persist_dir: None)
    monkeypatch.setattr(cli, "AnthropicClient", lambda model: SimpleNamespace())
    monkeypatch.setattr(
        cli, "answer", raising(status_error(400, USAGE_LIMIT, anthropic.BadRequestError))
    )
    monkeypatch.setattr(sys, "argv", ["whyd", "ask", str(tmp_path), "채점은 어디서?"])

    with pytest.raises(SystemExit) as exited:
        cli.main()

    assert exited.value.code == 1
    err = capsys.readouterr().err
    assert "사용 한도" in err
    assert "Traceback" not in err
