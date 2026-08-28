"""인덱싱된 코드베이스에 대해 질문에 답한다.

벡터 검색으로 관련 청크를 찾고, 그 코드를 근거로 LLM이 답변을 생성한다.
레포 전체를 LLM에 넣지 않고 검색으로 좁히는 이유는 두 가지다.
첫째, 큰 레포는 컨텍스트 한계를 넘는다.
둘째, 무관한 코드가 많이 섞이면 답변 품질이 떨어진다.
"""

import json

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

CANDIDATE_MULTIPLIER = 4
"""재정렬에 넘길 후보를 top_k의 몇 배로 뽑을지.

임베딩은 후보를 좁히는 데까지는 성공하나 그 안에서 순서를 매기지 못한다.
"코드를 어떻게 파싱하나요"에서 상위 셋의 거리가 0.6608, 0.6612, 0.6649로
차이가 0.004였고, 정답인 parser.py가 3위라 잘렸다. 문서에서도 같은 일이
있었다. 후보를 넓히면 정답이 그 안에 들어오고, 고르는 일은 LLM이 한다.

3배로 시작했으나 4배로 넓혔다. 두 파일의 관계를 묻는 질문에서 한쪽이
24, 25위에 있어 딱 한 끗 차이로 잘렸다. 이름이 비슷한 파일이 있으면
(index_access와 indexer) 임베딩이 둘을 구분하지 못해 한쪽이 관련
청크를 몰고 상위를 채운다.

넓히는 것이 공짜인 이유는 재정렬이 뒤에 있기 때문이다. 후보가 늘어도
최종 근거 수는 top_k로 고정되므로 답변 품질이 흔들리지 않는다.
재정렬 이전이라면 후보를 넓히는 것이 곧 근거를 넓히는 것이었다.
"""


def rerank(
    question: str,
    candidates: list[Chunk],
    llm: LLMClient,
    top_k: int,
) -> list[Chunk]:
    """후보 청크를 질문에 대한 유용성 순으로 다시 고른다.

    임베딩이 못 하는 일을 맡는다. 벡터 검색은 주제가 비슷한 것과 답이
    들어 있는 것을 구분하지 못한다. 진입점을 물으면 EntryPoint 클래스가
    1위로 오는데, 그것은 진입점을 다루는 코드일 뿐 진입점이 어디인지는
    말해주지 않는다.

    청크 전문이 아니라 요약과 심볼 이름만 넘긴다. 20개 전문을 넣으면
    프롬프트가 거대해지고, 고르는 데 필요한 것은 "이 청크에 무엇이
    들어 있는가"이지 코드 자체가 아니다.

    실패하면 원래 순서 그대로 자른다. 재정렬은 순서를 개선하는 층이고,
    이것 때문에 질문 자체가 실패하면 잃는 것이 더 크다.

    Args:
        question (str): 사용자 질문.
        candidates (list[Chunk]): 임베딩 검색이 뽑은 후보 목록.
        llm (LLMClient): 재정렬에 사용할 LLM 클라이언트.
        top_k (int): 최종적으로 남길 청크 수.

    Returns:
        list[Chunk]: 재정렬된 청크 목록. 실패하면 후보 앞에서 top_k개.
    """
    if len(candidates) <= top_k:
        return candidates

    lines = [
        f"{i}. [{c.kind}] {c.symbol} — {c.summary or '요약 없음'}"
        for i, c in enumerate(candidates, start=1)
    ]
    user = (
        f"질문: {question}\n\n"
        f"고를 개수: {top_k}\n\n"
        f"후보:\n" + "\n".join(lines)
    )

    try:
        raw = llm.complete(load_prompt("rerank"), user, max_tokens=300)
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return candidates[:top_k]

        picked = json.loads(raw[start : end + 1]).get("selected", [])
    except Exception:
        return candidates[:top_k]

    found: list[Chunk] = []
    seen: set[int] = set()

    for n in picked:
        # 범위 밖 번호와 중복은 버린다. 모델이 없는 번호를 만들거나
        # 같은 것을 두 번 고르는 경우가 있다.
        if not isinstance(n, int) or not 1 <= n <= len(candidates):
            continue
        if n in seen:
            continue

        seen.add(n)
        found.append(candidates[n - 1])

        if len(found) >= top_k:
            break

    # 모델이 요청한 개수보다 적게 골랐으면 원래 순서로 채운다.
    # 근거 수가 조건마다 달라지면 답변 품질 비교가 불가능해진다.
    for i, chunk in enumerate(candidates, start=1):
        if len(found) >= top_k:
            break
        if i not in seen:
            found.append(chunk)

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
    candidates = search_by_kind(question, chunks, store, top_k * CANDIDATE_MULTIPLIER)
    found = rerank(question, candidates, llm, top_k)

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