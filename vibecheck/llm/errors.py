"""LLM 호출이 실패했을 때 사용자에게 보일 안내를 만든다.

AnthropicClient는 SDK 예외를 감싸지 않고 그대로 올린다. 그 예외를 그대로
보여주면 웹은 "요청 실패 (500)"만, CLI는 트레이스백만 남아, 사용자가 무엇을
하면 되는지 알 수 없다. 사용 한도에 걸렸을 때 실제로 그렇게 떴다. 사용 한도,
키 오류, 네트워크 문제는 사용자가 할 일이 서로 다르다.

웹과 CLI가 같은 문장을 쓰도록 여기 한 곳에 둔다. 따로 두면 한쪽 문장만 고쳐져
같은 오류를 두 곳이 다르게 말한다.

예외를 클래스 이름이 아니라 상태 코드로 가른다. SDK 버전마다 세부 클래스가
더해지거나 나뉘는데(529 과부하 등), 공통 부모와 상태 코드는 바뀌지 않는다.
"""

import anthropic


class MissingAPIKey(ValueError):
    """API 키가 설정되지 않았다.

    ValueError의 하위로 둔다. 이전에는 ValueError를 그대로 던졌으므로, 그것을
    잡던 코드가 있어도 그대로 동작한다. 새로 잡는 쪽은 이 이름으로 골라 잡는다.
    ValueError 전체를 잡으면 전혀 다른 실수까지 키 문제로 안내하게 된다.
    """


LLM_ERRORS: tuple[type[BaseException], ...] = (anthropic.APIError, MissingAPIKey)
"""호출자가 잡아서 describe_llm_error로 넘길 예외들.

호출자가 SDK를 직접 import하지 않고 이것만 보면 되게 한다. 다른 LLM을 붙일 때
고칠 곳이 이 모듈 하나로 모인다.
"""

USAGE_LIMIT_MARK = "usage limits"
"""사용자가 정한 지출 한도에 닿았을 때 API 오류 메시지에 들어 있는 말.

이 경우 상태 코드가 429가 아니라 400(invalid_request_error)이라, 상태 코드만으로는
요청이 잘못된 것과 구분되지 않는다. 메시지에 재개 시각이 함께 온다.
"""


def api_message(exc: BaseException) -> str:
    """SDK 예외에서 API가 보낸 오류 문장만 꺼낸다.

    예외를 문자열로 바꾸면 "Error code: 400 - {...}"처럼 응답 몸통이 통째로 붙는다.
    몸통에 error.message가 있으면 그것만 쓴다.

    Args:
        exc (BaseException): SDK 예외.

    Returns:
        str: API가 보낸 오류 문장. 없으면 예외 메시지.
    """
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    return str(getattr(exc, "message", None) or exc)


def describe_llm_error(exc: BaseException) -> str | None:
    """LLM 호출 오류를 사용자가 할 일이 담긴 한 문장으로 바꾼다.

    알 수 없는 오류는 None을 돌려준다. 호출자는 None이면 원래 예외를 그대로
    올려, 모르는 것을 아는 것처럼 안내하지 않는다.

    Args:
        exc (BaseException): 잡은 예외.

    Returns:
        str | None: 안내 문장. LLM 오류가 아니면 None.
    """
    if isinstance(exc, MissingAPIKey):
        return str(exc)

    if isinstance(exc, anthropic.APIConnectionError):
        return "Anthropic API에 연결하지 못했습니다. 네트워크 연결을 확인하고 다시 시도하세요."

    if not isinstance(exc, anthropic.APIStatusError):
        if isinstance(exc, anthropic.APIError):
            return f"Anthropic API 호출이 실패했습니다: {api_message(exc)}"
        return None

    status = getattr(exc, "status_code", None)
    message = api_message(exc)

    if status == 400 and USAGE_LIMIT_MARK in message:
        return (
            "Anthropic API 사용 한도에 도달했습니다. Claude Console의 "
            "Settings > Billing에서 한도를 올리거나, 풀릴 때까지 기다리세요. "
            f"(API 안내: {message})"
        )
    if status == 401:
        return "API 키가 올바르지 않습니다. .env의 ANTHROPIC_API_KEY를 확인하세요."
    if status == 403:
        return f"이 API 키로는 요청한 작업을 할 수 없습니다. 키의 권한을 확인하세요. (API 안내: {message})"
    if status == 429:
        return "요청이 너무 잦아 Anthropic API가 잠시 거절했습니다. 잠시 뒤 다시 시도하세요."
    if isinstance(status, int) and status >= 500:
        return "Anthropic API가 일시적으로 응답하지 못했습니다. 잠시 뒤 다시 시도하세요."

    return f"Anthropic API가 요청을 거절했습니다 (상태 {status}): {message}"
