"""검색이 필요한 청크에 닿는지 측정한다.

검색을 고칠 때마다 같은 시험지로 재기 위한 도구다.
한 번은 닿고 한 번은 안 닿는 것을 두 번 겪었고, 그때마다 판단이
흔들렸다. 눈으로 근거 목록을 훑는 방식은 매번 기준이 달라진다.

기대 청크는 부분 문자열이 아니라 정확한 심볼로 적는다.
"pyproject"로 훑으면 to_pyproject_chunk 함수까지 걸려 통과로 찍힌다.
실제로 그렇게 잘못 읽은 적이 있다.
"""

import sys
from pathlib import Path

from vibecheck.services.index_access import open_index
from vibecheck.store.vector import VectorStore

CASES = [
    ("이 프로젝트는 어디서부터 실행되나요?", {"pyproject.toml"}),
    ("whyd 명령을 실행하면 어느 함수가 처음 호출되나요?", {"pyproject.toml", "main"}),
    ("이 프로젝트가 무엇을 하는 도구인가요?", {"README.md#VibeCheck"}),
    ("어떤 벡터 데이터베이스를 쓰나요?", {"README.md#기술 스택", "vibecheck/store/vector.py"}),
    ("코드를 어떻게 파싱하나요?", {"vibecheck/core/parser.py"}),
    ("설치하면 어떤 명령이 생기나요?", {"pyproject.toml"}),
]
"""(질문, 기대 심볼 집합) 목록.

기대가 여럿인 경우는 하나라도 나오면 통과다. 같은 사실이 여러 청크에
적혀 있을 때 어느 쪽으로 닿든 답할 수 있기 때문이다.

마지막 항목은 지금도 통과하는 질문이다. 고치는 과정에서 이것이 깨지면
개선이 아니라 이동이므로, 대조군으로 남겨둔다.
"""


def run(repo: Path, top_k: int = 8) -> None:
    """모든 사례를 검색해 통과 여부를 출력한다.

    Args:
        repo (Path): 대상 레포 루트.
        top_k (int): 검색할 청크 수.
    """
    from vibecheck.llm.anthropic import AnthropicClient

    chunks, chroma_dir, _, _ = open_index(repo)
    store = VectorStore(persist_dir=chroma_dir)
    by_id = {c.id: c for c in chunks}
    llm = AnthropicClient(model="claude-haiku-4-5")

    passed = 0

    for question, expected in CASES:
        from vibecheck.services.qa import (
            CANDIDATE_MULTIPLIER,
            rerank,
            search_by_kind,
        )

        candidates = search_by_kind(
            question, chunks, store, top_k * CANDIDATE_MULTIPLIER
        )
        found = [c.symbol for c in rerank(question, candidates, llm, top_k)]
        # 부분 일치가 아니라 정확히 같은 심볼만 통과시킨다.
        rank = next(
            (i + 1 for i, s in enumerate(found) if s in expected), None
        )

        if rank:
            passed += 1
            print(f"[O] {rank:>2}위  {question}")
        else:
            print(f"[.]   -   {question}")
            print(f"          기대: {sorted(expected)}")
            for i, s in enumerate(found, start=1):
                print(f"          {i}. {s}")

    print(f"\n{passed}/{len(CASES)} 통과 (top_k={top_k})")


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    run(target)