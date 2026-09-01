"""검색이 필요한 청크에 닿는지 측정한다.

검색을 고칠 때마다 같은 시험지로 재기 위한 도구다.
한 번은 닿고 한 번은 안 닿는 것을 두 번 겪었고, 그때마다 판단이
흔들렸다. 눈으로 근거 목록을 훑는 방식은 매번 기준이 달라진다.

기대 청크는 부분 문자열이 아니라 정확한 심볼로 적는다.
"pyproject"로 훑으면 to_pyproject_chunk 함수까지 걸려 통과로 찍힌다.
실제로 그렇게 잘못 읽은 적이 있다.

시험지가 둘인 이유는 v1을 고치면 그것으로 잰 과거 점수와 비교할 수
없기 때문이다. v1은 재정렬 도입 전후를 비교한 기록이므로 동결한다.
"""

import sys
from pathlib import Path

from vibecheck.services.index_access import open_index
from vibecheck.store.vector import VectorStore

CASES_V1 = [
    ("이 프로젝트는 어디서부터 실행되나요?", "any", {"pyproject.toml"}),
    (
        "whyd 명령을 실행하면 어느 함수가 처음 호출되나요?",
        "any",
        {"pyproject.toml", "main"},
    ),
    ("이 프로젝트가 무엇을 하는 도구인가요?", "any", {"README.md#VibeCheck"}),
    (
        "어떤 벡터 데이터베이스를 쓰나요?",
        "any",
        {"README.md#기술 스택", "vibecheck/store/vector.py"},
    ),
    ("코드를 어떻게 파싱하나요?", "any", {"vibecheck/core/parser.py"}),
    ("설치하면 어떤 명령이 생기나요?", "any", {"pyproject.toml"}),
]
"""동결된 첫 시험지. 고치지 않는다.

기대를 특정 청크 하나로 좁게 잡았고 전부 사실 조회형이라, 이 도구가
실제로 잘하는 일(흩어진 답 모으기, 독스트링에 적힌 '왜' 답하기)을
재지 못한다. 그럼에도 남겨두는 이유는 종류별 몫 도입 1/6 -> 4/6,
재정렬 도입 후 순위 상승을 이 시험지로 쟀기 때문이다.
"""

CASES_V2 = [
    (
        "parser.py랑 collector.py의 차이가 뭐예요?",
        "all",
        {"vibecheck/core/parser.py", "vibecheck/core/collector.py"},
    ),
    (
        "indexer.py랑 index_access.py의 관계가 어떻게 돼요?",
        "all",
        {"vibecheck/services/indexer.py", "vibecheck/services/index_access.py"},
    ),
    (
        "store를 따로 분류한 이유는 뭐고, records.py를 왜 그 안에 넣어뒀어요?",
        "any",
        {"vibecheck/store/records.py"},
    ),
    (
        "group_quirks 함수에서 묶는 기준을 파일이 아니라 인자 이름으로 잡은 이유가 뭐예요?",
        "any",
        {"group_quirks"},
    ),
    (
        "요약을 캐시할 때 왜 파일 수정 시각이 아니라 해시를 쓰나요?",
        "any",
        {"vibecheck/store/manifest.py", "Manifest.apply"},
    ),
    (
        "인덱싱한 뒤에 코드를 수정하면 어떻게 되나요?",
        "all",
        {"Manifest.apply", "VectorStore.add"},
    ),
]
"""두 번째 시험지.

여섯 중 다섯이 사용자가 직접 낸 질문이다. 무엇이 잘 검색되는지 아는
상태에서 문항을 고르면 통과할 질문만 고르게 되므로, 고르는 일은
결과를 보지 않은 쪽이 해야 한다.

절반이 all인 것은 v1이 못 재던 자리다. "차이가 뭐냐", "관계가 어떻게
되냐"는 두 대상이 모두 근거에 있어야 답할 수 있는데, 하나만 나와도
통과로 치면 그 실패가 보이지 않는다.
"""

CASES_V3 = [
    ("child_by_field_name", "any", {"walk", "extract_imports.scan"}),
    (
        "이 프로젝트는 어디서부터 실행되나요?",
        "any",
        {"pyproject.toml", "find_script_entries", "EntryPoint"},
    ),
    ("prune은 언제 호출되나요?", "any", {"VectorStore.prune"}),
    ("요약을 캐시할 때 왜 해시를 쓰나요?", "any", {"Manifest.apply"}),
]
"""식별자 검색용 시험지.

앞의 셋은 식별자나 식별자가 섞인 질의다. 넷째는 대조군으로 v2에서
이미 통과하는 순수 자연어 질문이며, 하이브리드 검색이 자연어 경로를
망가뜨리지 않는지 보기 위해 넣었다.

통과 여부가 아니라 순위를 기록한다. 식별자 질의는 벡터 검색에서
69등까지 밀리므로 재정렬 후보에도 들지 못한다. 통과/실패만 보면
0에서 0으로 남아 고쳐도 나아졌는지 알 수 없다.

2번은 원래 `콘솔 스크립트 진입점`으로 `main`을 기대했다.
독스트링에서 떼어낸 인공 질의였고 `main` 본문이 app() 한 줄이라
실제로 답에 쓰이지 않는다. 실제 면접 질문으로 바꾸고 답변이
실제로 쓴 근거를 기대로 삼았다.
"""

REJECT_CASES = [
    "spring AI를 적용한 이유가 뭐예요?",
    "advisor 호출 흐름을 설명해 보세요.",
]
"""이 레포에 답이 없는 질문.

Spring AI는 자바 프레임워크이고 이 프로젝트에 advisor라는 것도 없다.
검색을 넓히다 보면 무엇을 물어도 그럴듯한 것을 가져오는 방향으로
갈 수 있는데, 그것을 막을 항목이 시험지에 하나는 있어야 한다.

여기서 재는 것은 청크가 아니라 답변이다. 검색은 어차피 무언가를
돌려주므로, 그 근거를 받은 모델이 "없다"고 말하는지를 봐야 한다.
자동 판정하지 않고 사람이 읽는다. 없다고 말하는 방식이 여러 가지라
문자열로 판정하면 맞는 답을 틀렸다고 찍는다.
"""


def run(repo: Path, cases: list, label: str, top_k: int = 8) -> None:
    """시험지 하나를 돌려 통과 여부를 출력한다.

    Args:
        repo (Path): 대상 레포 루트.
        cases (list): (질문, 방식, 기대 심볼 집합) 목록.
            방식이 "all"이면 기대를 모두 찾아야 통과한다.
        label (str): 출력에 표시할 시험지 이름.
        top_k (int): 검색할 청크 수.
    """
    from vibecheck.llm.anthropic import AnthropicClient
    from vibecheck.services.qa import (
        CANDIDATE_MULTIPLIER,
        rerank,
        search_by_kind,
    )

    chunks, chroma_dir, _, _ = open_index(repo)
    store = VectorStore(persist_dir=chroma_dir)
    llm = AnthropicClient(model="claude-haiku-4-5")

    passed = 0
    print(f"\n=== {label}")

    for question, mode, expected in cases:
        candidates = search_by_kind(
            question, chunks, store, top_k * CANDIDATE_MULTIPLIER
        )
        found = [c.symbol for c in rerank(question, candidates, llm, top_k)]

        hit = {s for s in found if s in expected}
        ok = hit == expected if mode == "all" else bool(hit)

        if ok:
            passed += 1
            ranks = sorted(found.index(s) + 1 for s in hit)
            print(f"[O] {ranks}  {question[:40]}")
        else:
            print(f"[.]      {question[:40]}")
            print(f"         기대({mode}): {sorted(expected)}")
            if hit:
                print(f"         찾음: {sorted(hit)}")
            for i, s in enumerate(found, start=1):
                print(f"         {i}. {s}")

    print(f"\n{passed}/{len(cases)} 통과 (top_k={top_k})")

def run_raw(repo: Path, cases: list, label: str, depth: int = 200) -> None:
    """재정렬 이전, 벡터 검색만으로 기대 청크가 몇 등인지 찍는다.

    run()과 달리 통과 여부가 아니라 순위를 남긴다. 식별자 질의는
    상위권에 아예 오지 못해 통과/실패로는 0과 0의 비교가 되고,
    고친 뒤에도 나아졌는지 말할 수 없기 때문이다.

    재정렬을 거치지 않는 이유는 두 가지다. 후보에 들지 못한 청크는
    재정렬이 구제할 수 없어 벡터 단계의 순위가 문제의 실제 위치다.
    또한 LLM을 부르지 않아 여러 번 돌려도 비용과 변동이 없다.

    Args:
        repo (Path): 대상 레포 루트.
        cases (list): (질의, 방식, 기대 심볼 집합) 목록. 방식은 쓰지 않는다.
        label (str): 출력에 표시할 시험지 이름.
        depth (int): 순위를 찾아볼 깊이. 전체 청크 수보다 크면 전부 훑는다.
    """
    _, chroma_dir, _, _ = open_index(repo)
    store = VectorStore(persist_dir=chroma_dir)

    print(f"\n=== {label} (재정렬 전 벡터 순위, depth={depth})")

    for query, _mode, expected in cases:
        found = store.search(query, top_k=depth)
        ranks = {}

        # 심볼명은 파일이 다르면 겹칠 수 있어 먼저 나온 것만 남긴다.
        # 이 레포에서는 기대 심볼이 모두 유일해 문제가 없지만,
        # 다른 레포에 쓰면 동명의 다른 함수를 정답으로 찍을 수 있다.
        for i, hit in enumerate(found, start=1):
            if hit["symbol"] in expected and hit["symbol"] not in ranks:
                ranks[hit["symbol"]] = (i, hit["distance"])

        print(f"\n--- {query}")

        if found:
            print(f"    1등: {found[0]['symbol']} ({found[0]['distance']:.4f})")

        for symbol in sorted(expected):
            if symbol in ranks:
                rank, dist = ranks[symbol]
                print(f"    {symbol}: {rank}등 ({dist:.4f})")
            else:
                print(f"    {symbol}: {depth}등 밖")


def show_rejects(repo: Path, top_k: int = 8) -> None:
    """답이 없는 질문에 무엇을 돌려주는지 보여준다.

    통과 여부를 찍지 않는다. 검색은 언제나 top_k개를 돌려주므로
    여기서 볼 것은 근거가 아니라 답변이고, 그 판정은 사람이 한다.

    Args:
        repo (Path): 대상 레포 루트.
        top_k (int): 검색할 청크 수.
    """
    from vibecheck.llm.anthropic import AnthropicClient
    from vibecheck.services.qa import answer

    chunks, chroma_dir, _, _ = open_index(repo)
    store = VectorStore(persist_dir=chroma_dir)
    llm = AnthropicClient(model="claude-sonnet-4-6")

    print("\n=== 답이 없는 질문 (사람이 읽고 판정)")

    for question in REJECT_CASES:
        text, _ = answer(question, chunks, store, llm, top_k)
        print(f"\n--- {question}")
        print(text[:400])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    target = Path(args[0] if args else ".").resolve()

    if "--v1" in sys.argv:
        run(target, CASES_V1, "v1 (동결)")
    elif "--v3" in sys.argv:
        run_raw(target, CASES_V3, "v3 (식별자)")
    elif "--reject" in sys.argv:
        show_rejects(target)
    else:
        run(target, CASES_V2, "v2")