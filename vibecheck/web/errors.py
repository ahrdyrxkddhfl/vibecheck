"""라우터 밖으로 새어 나온 예외 중 원인을 아는 것을 안내 문장으로 바꾼다.

deps.py가 인덱스를 열 때의 실패를 번역하듯, 여기서는 그 뒤에 일어나는 실패를
번역한다. 라우터마다 try를 두지 않고 앱에 한 번 등록해, 질문과 채점은 물론 앞으로
붙을 화면에도 같이 적용되게 한다.

화면은 응답의 detail을 그대로 보여준다(index.html의 body). 그래서 여기서 detail만
제대로 채우면 화면 코드는 고칠 것이 없다.

모르는 예외는 건드리지 않는다. 원인을 모르는 채로 그럴듯한 안내를 붙이면 사용자가
엉뚱한 곳을 고친다. 그런 예외는 지금처럼 500과 트레이스백으로 남는다.
"""

import logging

from chromadb.errors import InternalError as ChromaInternalError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from vibecheck.llm.errors import LLM_ERRORS, MissingAPIKey, describe_llm_error

logger = logging.getLogger(__name__)

STALE_STORE_MESSAGE = (
    "벡터 저장소를 읽지 못했습니다. 인덱싱이 진행 중이었다면 끝난 뒤 다시 시도하세요. "
    "계속되면 whyd serve를 다시 띄우세요."
)
"""벡터 저장소 내부 오류에 붙이는 안내.

서버를 켠 채 다른 프로세스가 whyd index로 다시 인덱싱하면, 서버가 들고 있던
연결은 없는 id를 찾다가 "Error finding id"로 실패했다(2026-09-23). 지금은
store.vector.get_client가 저장소 파일의 수정 시각으로 이를 알아채고 새로 연다.

남는 경우는 인덱싱과 요청이 정확히 겹쳐, 새로 여는 순간 옛 연결로 진행 중이던
요청이 실패하는 것이다. 다시 시도하면 새 연결로 풀린다. 같은 예외가 다른 원인으로도
날 수 있어 원인을 단정하지 않고, 조건과 함께 할 일을 차례로 적는다.
"""


async def llm_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """LLM 호출 실패를 안내 문장으로 바꿔 응답한다.

    상태 코드는 502다. 이 서버가 잘못한 것이 아니라 이 서버가 부른 곳(Anthropic API)이
    거절하거나 응답하지 못한 것이라서다. 키가 없는 경우만 500이다. 그건 이 서버의
    설정 문제다.

    Args:
        request (Request): 들어온 요청.
        exc (Exception): LLM_ERRORS에 속하는 예외.

    Returns:
        JSONResponse: detail에 안내 문장을 담은 응답.
    """
    message = describe_llm_error(exc) or str(exc)
    logger.warning("LLM 호출 실패 (%s): %s", request.url.path, message)
    status = 500 if isinstance(exc, MissingAPIKey) else 502
    return JSONResponse(status_code=status, content={"detail": message})


async def store_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """벡터 저장소 내부 오류를 다시 시도하라는 안내로 바꿔 응답한다.

    원인을 단정하지 않으므로 트레이스백은 서버 로그에 그대로 남긴다. 안내대로 해도
    안 되면 그 로그가 다음 단서다.

    Args:
        request (Request): 들어온 요청.
        exc (Exception): Chroma 내부 오류.

    Returns:
        JSONResponse: 503과 안내 문장.
    """
    logger.error("벡터 저장소 오류 (%s)", request.url.path, exc_info=exc)
    return JSONResponse(status_code=503, content={"detail": STALE_STORE_MESSAGE})


def register_error_handlers(app: FastAPI) -> None:
    """앱에 오류 처리기를 등록한다.

    Args:
        app (FastAPI): 처리기를 붙일 앱.
    """
    for error in LLM_ERRORS:
        app.add_exception_handler(error, llm_error_handler)
    app.add_exception_handler(ChromaInternalError, store_error_handler)
