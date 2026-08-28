"""인덱싱된 코드베이스에 대해 질문에 답한다.

벡터 검색으로 관련 청크를 찾고, 그 코드를 근거로 LLM이 답변을 생성한다.
레포 전체를 LLM에 넣지 않고 검색으로 좁히는 이유는 두 가지다.
첫째, 큰 레포는 컨텍스트 한계를 넘는다.
둘째, 무관한 코드가 많이 섞이면 답변 품질이 떨어진다.
"""

from vibecheck.prompts import load_prompt
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
            f"심볼: {c.symbol} ({c.kind})\n"
            f"위치: {c.start_line}-{c.end_line}행\n"
            f"요약: {c.summary or '없음'}\n"
            f"\n"
            f"{c.code}\n"
            f"</chunk>"
        )
    return "\n\n".join(blocks)

KIND_QUOTAS = [
    (None, 4),
    (["file"], 2),
    (["doc"], 1),
    (["config"], 1),
]
"""검색 결과에서 청크 종류별로 확보할 자리.

같은 판에서 경쟁시키면 함수·클래스 청크가 전부 차지한다. 이 레포에서
155개 중 121개가 L2라 상위 8칸에 나머지가 낄 자리가 없었다.

증상은 일관됐다. "어떤 벡터 DB를 쓰나요"에 VectorStore 클래스가 1위로
오고 정작 ChromaDB라고 적힌 문서는 오지 않는다. 개념을 물으면 그 개념을
구현한 코드가 먼저 오고 그 개념을 설명한 글이 밀린다.

pyproject.toml 청크의 kind가 file이라 설정 파일은 L1과 같은 몫을 쓴다.
따로 떼면 몫이 하나뿐인 종류가 생기는데, 설정 파일이 없는 레포에서는
그 자리가 통째로 낭비된다.

첫 줄이 None인 것은 종류를 가리지 않는다는 뜻이다. 이 자리는 원래의
검색 결과 그대로이고, 나머지가 그 위에 얹히는 구조다.
"""


def search_by_kind(
    question: str,
    chunks: list[Chunk],
    store: VectorStore,
    top_k: int,
) -> list[Chunk]:
    """청크 종류별로 자리를 나눠 검색한 뒤 합친다.

    몫을 채우지 못한 자리는 비워두지 않고 종류를 가리지 않는 검색으로
    메운다. 문서가 없는 레포에서 그 자리가 놀면 근거가 그만큼 줄어든다.

    Args:
        question (str): 사용자 질문.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
        store (VectorStore): 검색에 사용할 벡터 저장소.
        top_k (int): 근거로 사용할 청크 수.

    Returns:
        list[Chunk]: 합쳐진 근거 청크 목록.
    """
    by_id = {c.id: c for c in chunks}

    found: list[Chunk] = []
    seen: set[str] = set()

    def take(kinds: list[str] | None, limit: int) -> None:
        """한 종류에서 limit개까지 골라 담는다."""
        for hit in store.search(question, top_k=limit, kinds=kinds):
            chunk = by_id.get(hit["id"])
            if chunk is None or chunk.id in seen:
                continue

            seen.add(chunk.id)
            found.append(chunk)

            if len(found) >= top_k:
                return

    for kinds, quota in KIND_QUOTAS:
        take(kinds, quota)
        if len(found) >= top_k:
            return found

    # 남은 자리는 종류를 가리지 않고 채운다.
    if len(found) < top_k:
        take(None, top_k)

    return found

def answer(
    question: str,
    chunks: list[Chunk],
    store: VectorStore,
    llm: LLMClient,
    top_k: int = 8,
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
            실험 A3에서 5에서 8로 늘렸을 때 답변 점수가 21에서 23으로 올랐다.
            정답이 큰 함수 안에 있어 상위 5개에 들지 못하던 경우가 해소됐다.
            ctxd 규모(67청크)에서 관찰된 값이므로 일반적 최적값은 아니다.

    Returns:
        tuple[str, list[Chunk]]: 답변 텍스트와 근거로 사용된 청크 목록.
            근거를 함께 반환하는 이유는 사용자가 답변의 출처를 직접 확인할 수 있어야 하기 때문이다.
            LLM답변은 검증 가능해야 한다.
    """
    found = search_by_kind(question, chunks, store, top_k)

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