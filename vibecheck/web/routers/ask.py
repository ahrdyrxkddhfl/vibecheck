"""질문하기 화면이 쓰는 엔드포인트.

`whyd ask`의 웹 대응물이다. 서비스(qa.answer)를 그대로 불러 CLI와 같은
검색, 같은 재정렬, 같은 모델로 답한다. 화면마다 답을 만드는 길이 따로 있으면
같은 질문에 CLI와 웹이 다른 근거를 내놓게 된다.

리포트 라우터와 나눈 이유는 app.py에 적힌 대로 화면 단위로 라우터가 늘어나기
때문이다. 대화 이어가기가 붙으면 이 파일이 자란다.
"""

import logging
import sqlite3

from fastapi import APIRouter
from pydantic import BaseModel, Field

from vibecheck.llm.anthropic import ANSWER_MODEL, AnthropicClient
from vibecheck.services.qa import answer, source_refs
from vibecheck.store.records import connect, get_repo_id, save_ask
from vibecheck.store.vector import VectorStore
from vibecheck.web.deps import Index, RepoPath

logger = logging.getLogger(__name__)

router = APIRouter()


class AskRequest(BaseModel):
    """질문 요청.

    빈 질문을 스키마에서 거르는 이유는 채점 요청과 같다. 답변은 LLM을 두 번
    부르므로(재정렬, 답변 생성) 실수로 빈 폼을 보냈을 때 요금이 나가지 않아야 한다.

    Attributes:
        question: 사용자 질문.
    """

    question: str = Field(min_length=1)


@router.post("/ask")
def post_ask(repo: RepoPath, index: Index, req: AskRequest) -> dict:
    """인덱싱된 레포에 질문하고 답변과 근거를 돌려준다. LLM을 부른다.

    과금되는 요청이라 POST로 둔다. GET이면 새로고침이나 브라우저의 미리
    읽기만으로 다시 불려 요금이 나간다. 리포트 라우터의 채점과 같은 이유다.

    근거는 CLI가 찍는 것과 같은 네 가지(파일, 시작 줄, 끝 줄, 심볼)만 싣는다
    (services.qa.source_refs). 기록도 같은 모양으로 남아, 기록 화면이 이 응답을
    그리던 코드로 지난 답을 그린다.

    질문과 답을 기록에 남긴다. 채점 기록과는 테이블이 달라 누적에 섞이지 않는다.
    근거를 못 찾은 답은 남기지 않는다. 다시 볼 내용이 없다.

    저장이 실패해도 답은 그대로 보낸다. 응답은 이 함수가 끝나야 나가므로,
    저장에서 난 예외를 그대로 두면 이미 요금을 낸 답까지 500으로 버려진다.
    대신 `saved`를 거짓으로 실어 화면이 기록에 남지 않았다고 밝히게 한다.

    `stale_count`를 싣는 이유는 개요와 같다. 인덱싱 뒤 바뀐 파일의 청크는
    검색에서 빠지므로, 답이 그 파일을 모르는 이유를 화면이 밝힐 수 있어야 한다.

    Args:
        repo: 정규화된 레포 경로. 기록을 열 때 쓴다.
        index: `open_index()`의 반환값
            (청크, 벡터 저장소 경로, 건너뛴 수, 인덱싱 조건).
        req: 질문.

    Returns:
        dict: `question`, `answer`(마크다운), `sources`(근거 목록), `stale_count`,
            `saved`(기록에 남았는지).
    """
    chunks, chroma_dir, stale, _meta = index

    text, sources = answer(
        req.question,
        chunks,
        VectorStore(persist_dir=chroma_dir),
        AnthropicClient(model=ANSWER_MODEL),
    )

    refs = source_refs(sources)

    saved = False
    if refs:
        try:
            conn = connect(repo)
            try:
                save_ask(conn, get_repo_id(conn, repo), req.question, text, refs)
                saved = True
            finally:
                conn.close()
        except sqlite3.Error:
            logger.exception("질문 기록을 저장하지 못했습니다: %s", repo)

    return {
        "question": req.question,
        "answer": text,
        "sources": refs,
        "stale_count": stale,
        "saved": saved,
    }
