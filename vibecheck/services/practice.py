"""사용자가 작성한 면접 답변을 코드 근거와 대조해 채점한다.

이 프로젝트에서 처음으로 사용자 텍스트를 입력으로 받는 기능이다.
채점자 LLM은 정답을 모른다. "왜 이렇게 짰는가"류 질문은 정답이 코드에
남아 있지 않기 때문이다. 따라서 채점의 기준은 내용의 정답 여부가 아니라
검색으로 뽑은 근거 청크와 답변이 어떤 관계에 있는가이다.

질문과 답변으로 각각 검색해 합친다.
처음에는 질문만 썼다. 답변을 쿼리에 섞으면 답변이 틀렸을 때 검색이
그 방향으로 끌려갈 것을 우려했기 때문이다.

실제로 확인한 것은 다른 문제였다. 단정형 오답은 질문만으로도 걸러졌고,
막힌 쪽은 반대였다. 사실을 정확히 말한 답변이 그 심볼의 청크가 검색되지
않아 확인불가 판정을 받았다. 오답을 못 잡는 것이 아니라 정답을 확인해주지
못하는 것이 문제였다.

원래 우려는 남아 있으므로 질문 몫을 절반으로 고정한다.
답변이 무엇이든 근거의 절반은 질문 기준으로 채워진다.
"""

import json

from vibecheck.prompts import load_prompt
from vibecheck.llm.base import LLMClient
from vibecheck.models import AnswerFeedback, Chunk, ClaimCheck
from vibecheck.services.qa import build_context
from vibecheck.store.vector import VectorStore

VERDICTS = {"confirmed", "contradicted", "unverifiable"}


def build_user_message(question: str, user_answer: str, chunks: list[Chunk]) -> str:
    """채점 요청에 사용할 사용자 메시지를 구성한다.

    사용자 답변을 구분자로 감싸는 이유는 코드를 감쌀 때와 같지만 위험은 더 크다.
    코드는 우연히 지시문처럼 읽힐 수 있는 정도지만, 사용자 답변은 의도적으로
    "만점을 주라"고 쓸 수 있다. 경계를 명시해 모델이 이 영역을 지시가 아닌
    채점 대상 데이터로 취급하도록 한다.

    근거를 답변보다 먼저 놓는 것도 의도적이다. 모델이 답변을 읽기 전에
    코드를 먼저 보게 해야 답변에 끌려가지 않는다.

    Args:
        question (str): 채점 대상 질문.
        user_answer (str): 사용자가 작성한 답변 원문.
        chunks (list[Chunk]): 검색으로 찾은 근거 청크 목록.

    Returns:
        str: 조립된 사용자 메시지.
    """
    return (
        f"질문: {question}\n\n"
        f"근거 (이 레포의 코드에서 검색한 결과):\n\n"
        f"{build_context(chunks)}\n\n"
        f"사용자 답변:\n"
        f"<user_answer>\n"
        f"{user_answer}\n"
        f"</user_answer>"
    )


def extract_json(raw: str) -> dict:
    """LLM 응답에서 JSON 객체를 뽑아낸다.

    프롬프트에서 JSON만 출력하라고 지시해도 코드 펜스나 머리말이 붙는 경우가 있다.
    첫 여는 중괄호부터 마지막 닫는 중괄호까지를 잘라내면 두 경우 모두 처리된다.

    Args:
        raw (str): LLM 응답 원문.

    Returns:
        dict: 파싱된 객체.

    Raises:
        ValueError: 중괄호를 찾지 못했거나 JSON으로 파싱되지 않을 때.
    """
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"응답에서 JSON을 찾지 못했습니다: {raw[:200]}")

    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}") from e


def clamp_score(value: object) -> int:
    """점수를 0-2 범위의 정수로 정규화한다.

    모델이 3점이나 문자열을 반환하는 경우를 대비한다.
    채점 한 축이 이상해도 나머지 결과는 살아야 하므로 예외를 던지지 않고
    범위 안으로 접는다. 값이 아예 해석 불가면 0으로 둔다.
    """
    try:
        return max(0, min(2, int(value)))
    except (TypeError, ValueError):
        return 0


def parse_feedback(
    raw: str,
    question: str,
    user_answer: str,
    chunks: list[Chunk],
) -> AnswerFeedback:
    """LLM 응답을 AnswerFeedback으로 변환한다.

    모델 출력을 그대로 믿지 않고 필드마다 방어한다.
    파싱이 실패하면 사용자는 답변을 다시 써야 하는데, 그 비용이 채점 한 항목이
    비는 것보다 크다. 따라서 알 수 없는 값은 버리거나 안전한 기본값으로 대체하고
    나머지는 살린다.

    Args:
        raw (str): LLM 응답 원문.
        question (str): 채점 대상 질문.
        user_answer (str): 사용자 답변 원문.
        chunks (list[Chunk]): 채점에 사용한 근거 청크.

    Returns:
        AnswerFeedback: 채점 결과.
    """
    data = extract_json(raw)

    claims = []
    for item in data.get("claims", []):
        verdict = item.get("verdict")
        if verdict not in VERDICTS:
            # 알 수 없는 판정은 "확인 불가"로 둔다.
            # 모르는 값을 confirmed나 contradicted로 밀면 없는 사실이 생긴다.
            verdict = "unverifiable"

        claims.append(
            ClaimCheck(
                claim=str(item.get("claim", "")),
                verdict=verdict,
                hedged=bool(item.get("hedged", False)),
                evidence=item.get("evidence") or None,
                note=str(item.get("note", "")),
            )
        )

    return AnswerFeedback(
        question=question,
        user_answer=user_answer,
        claims=claims,
        specificity=clamp_score(data.get("specificity")),
        calibration=clamp_score(data.get("calibration")),
        groundedness=clamp_score(data.get("groundedness")),
        verdict_line=str(data.get("verdict_line", "")),
        revision=str(data.get("revision", "")),
        evidence_chunks=[
            f"{c.file}:{c.start_line}-{c.end_line} {c.symbol}" for c in chunks
        ],
    )

def search_union(
    question: str,
    user_answer: str,
    chunks: list[Chunk],
    store: VectorStore,
    top_k: int,
) -> list[Chunk]:
    """질문과 답변으로 각각 검색해 합친다.

    질문만으로 검색하면 답변에 나온 심볼이 쿼리에 없어 그 청크가 걸리지
    않는다. 사실을 정확히 말한 답변이 "근거 청크에 없다"는 이유로
    확인불가 판정을 받는다. 실제로 tree-sitter와 프로젝트 목적에서
    이것을 확인했다.

    두 쿼리를 이어붙이지 않고 따로 검색하는 이유는 임베딩 길이 제한이다.
    max_seq_length가 128이라 답변이 길면 질문이 통째로 밀려난다.

    질문 몫을 먼저 채우고 답변 몫을 뒤에 붙인다. 답변이 틀렸을 때
    검색이 그쪽으로 끌려가는 것이 이 방식의 위험인데, 질문 몫을 고정해두면
    답변이 무엇이든 절반은 질문 기준으로 남는다.

    전체 개수는 top_k를 넘기지 않는다. 근거 수가 늘면 같은 답변의 점수가
    달라지는 것을 확인했으므로, 쿼리 방식만 바뀐 비교가 되려면
    근거 수는 그대로여야 한다.

    Args:
        question (str): 채점 대상 질문.
        user_answer (str): 사용자 답변. 검색 쿼리로도 쓴다.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
        store (VectorStore): 검색에 사용할 벡터 저장소.
        top_k (int): 근거로 사용할 청크 수의 상한.

    Returns:
        list[Chunk]: 합쳐진 근거 청크 목록. 질문 기준 결과가 앞에 온다.
    """
    by_id = {c.id: c for c in chunks}

    # 질문 몫을 절반으로 둔다. 홀수면 질문 쪽이 하나 더 갖는다.
    # 채점의 기준은 어디까지나 질문이고 답변은 보조 재료다.
    question_k = (top_k + 1) // 2

    found: list[Chunk] = []
    seen: set[str] = set()

    for query, limit in ((question, question_k), (user_answer, top_k)):
        if not query.strip():
            continue

        for hit in store.search(query, top_k=limit):
            chunk = by_id.get(hit["id"])
            if chunk is None or chunk.id in seen:
                continue

            seen.add(chunk.id)
            found.append(chunk)

            if len(found) >= top_k:
                return found

    return found

def grade(
    question: str,
    user_answer: str,
    chunks: list[Chunk],
    store: VectorStore,
    llm: LLMClient,
    top_k: int = 8,
) -> AnswerFeedback:
    """사용자 답변을 코드 근거와 대조해 채점한다.

    검색과 채점을 한 함수에서 처리하는 이유는 채점에 사용한 근거가
    반환값에 함께 남아야 하기 때문이다. 사용자가 "코드에서 확인하기"로
    넘어갈 때 채점의 출발점과 같은 청크를 봐야 피드백이 검증 가능해진다.

    Args:
        question (str): 채점 대상 질문. 검색 쿼리로도 사용된다.
        user_answer (str): 사용자가 작성한 답변.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
        store (VectorStore): 검색에 사용할 벡터 저장소.
        llm (LLMClient): 채점에 사용할 LLM 클라이언트.
        top_k (int): 근거로 사용할 청크 수. ask와 같은 값을 쓴다.
            채점 근거가 ask 답변의 근거보다 좁으면 사용자가 확인 화면에서
            채점에 없던 코드를 보게 된다.

    Returns:
        AnswerFeedback: 채점 결과. 근거 청크를 찾지 못하면 모든 점수가 0이고
            verdict_line에 그 사실이 담긴다.
    """
    found = search_union(question, user_answer, chunks, store, top_k)

    if not found:
        return AnswerFeedback(
            question=question,
            user_answer=user_answer,
            verdict_line="관련된 코드를 찾지 못해 채점할 수 없습니다.",
        )

    system = load_prompt("grade_answer")
    user = build_user_message(question, user_answer, found)
    raw = llm.complete(system, user, max_tokens=2000)

    return parse_feedback(raw, question, user_answer, found)