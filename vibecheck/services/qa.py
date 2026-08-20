"""인덱싱된 코드베이스에 대해 질문에 답한다.

벡터 검색으로 관련 청크를 찾고, 그 코드를 근거로 LLM이 답변을 생성한다.
레포 전체를 LLM에 넣지 않고 검색으로 좁히는 이유는 두 가지다.
첫째, 큰 레포는 컨텍스트 한계를 넘는다.
둘째, 무관한 코드가 많이 섞이면 답변 품질이 떨어진다.
"""

from vibecheck.core.summarizer import load_prompt
from vibecheck.llm.base import LLMClient
from vibecheck.models import Chunk
from vibecheck.store.vector import VectorStore

def build_context(chunks: list[Chunk]) -> str:
    """검색된 청크들을 LLM에 전달할 컨텍스트 문자열로 조립한다.

    각 청크를 구분자로 감싸 경계를 명확히 한다.
    여러 조각을 이어 붙일 때 경계가 모호하면 서로 다른 함수의 코드가 하나로 읽힐 수 있고,
    코드 내부의 텍스트가 지시문으로 해석될 여지도 생긴다.

    Args:
        chunks (list[Chunk]): 컨텍스트에 포함할 청크 목록.

    Returns:
        str: 조립된 컨텍스트 문자열.
    """
    blocks = []
    for c in chunks:
        blocks.append(
            f"<chunk>\n"
            f"파일: {c.file}\n"
            f"심볼: {c.symbol} ({c.kind}\n)"
            f"위치: {c.start_line}-{c.end_line}행\n"
            f"요약: {c.summary or '없음'}\n"
            f"\n"
            f"{c.code}\n"
            f"</chunk>"
        )
    return "\n\n".join(blocks)

def answer(
    question: str,
    chunks: list[Chunk],
    store: VectorStore,
    llm: LLMClient,
    top_k: int = 5,
) -> tuple[str, list[Chunk]]:
    """질문에 대한 답변과 근거 청크를 반환한다.

    벡터 검색은 정답 하나를 맞히는 것이 아니라 후보를 좁히는 역할을 한다.
    상위 top_k개를 모두 전달하면 그 중 관련 있는 것을 LLM이 판단하므로,
    검색 1위가 정답이 아니어도 답변은 정확할 수 있다.

    Args:
        question (str): 사용자 질문.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
            검색 결과의 id로 코드 본문을 찾기 위해 사용한다.
        store (VectorStore): 검색에 사용할 벡터 저장소.
        llm (LLMClient): 답변 생성에 사용할 LLM 클라이언트.
        top_k (int): 컨텍스트에 포함할 청크 수.

    Returns:
        tuple[str, list[Chunk]]: 답변 텍스트와 근거로 사용된 청크 목록.
            근거를 함께 반환하는 이유는 사용자가 답변의 출처를 직접 확인할 수 있어야 하기 때문이다.
            LLM답변은 검증 가능해야 한다.
    """
    hits = store.search(question, top_k=top_k)

    by_id = {c.id: c for c in chunks}
    found = [by_id[h["id"]] for h in hits if h["id"] in by_id]

    if not found:
        return "관련된 코드를 찾지 못했습니다.", []

    system = load_prompt("answer_question")
    user = f"질문: {question}\n\n참고할 코드:\n\n{build_context(found)}"

    return llm.complete(system, user, max_tokens=2000), found

if __name__ == "__main__":
    import sys

    from vibecheck.llm.anthropic import AnthropicClient
    from vibecheck.services.indexer import index_repo

    target = "."
    question = sys.argv[1] if len(sys.argv) > 1 else "파일 수집은 어떻게 이루어지나요?"

    llm = AnthropicClient(model="claude-sonnet-4-6")
    chunks = index_repo(target, llm, verbose=True)

    store = VectorStore()
    store.add(chunks)

    print(f"\n{'=' * 50}")
    print(f"Q. {question}\n")

    text, sources = answer(question, chunks, store, llm)
    print(text)

    print(f"\n{'-' * 50}")
    print("근거: ")
    for c in sources:
        print(f"    {c.file}:{c.start_line}-{c.end_line}    {c.symbol}")