"""실험 A 대상 레포(ctxd)를 인덱싱한다.

캐시와 컬렉션 경로를 프로젝트 기본값과 분리한다.
기본값을 그대로 쓰면 남의 코드 청크가 자신의 인덱스에 섞여,
이후 whyd에 무엇을 물어도 ctxd 코드가 검색 결과에 튀어나온다.

테스트를 제외하는 이유는 이번 실험에서 테스트가 채점용 정답지이기 때문이다.
테스트가 인덱스에 있으면 "API 키를 어떤 순서로 찾느냐" 같은 질문에
검색어 test_config를 물어와 정답을 그대로 읽어준다.
평소의 whyd는 테스트를 포함해야 한다. 테스트는 사용 예시를 담고 있어
독스트링이 없는 레포일수록 검색에 도움이 되기 때문이다.
"""

from vibecheck.llm.anthropic import AnthropicClient
from vibecheck.services.indexer import index_repo
from vibecheck.store.vector import VectorStore

from pathlib import Path

# 대상을 인자로 받지 않고 못 박는 이유는 이 파일이 도구가 아니라 실험 기록이기 때문이다.
# 무엇을 어떤 조건으로 쟀는지가 코드에 남아 있어야 나중에 재현할 수 있다.
# 다만 홈 디렉토리 경로는 사용자 이름이 드러나므로 Path.home()으로 대체한다.
TARGET = str(Path.home() / "work/vibecheck-targets/ctxd")
# L1 도입 전 인덱스를 보존한다. 같은 컬렉션에 덮어쓰면
# 실험 A 결과를 재현할 수 없어 개선 전후를 비교할 수 없다.
PERSIST_DIR = ".vibecheck/cache_ctxd_l1"
EXCLUDE = {"tests"}

def main() -> None:
    """대상 레포를 인덱싱하고 벡터 저장소에 적재한다."""
    llm = AnthropicClient(model="claude-haiku-4-5-20251001")

    chunks = index_repo(
        TARGET,
        llm,
        verbose=True,
        persist_dir=PERSIST_DIR,
        exclude_dirs=EXCLUDE,
    )

    store = VectorStore(persist_dir=f"{PERSIST_DIR}/chroma")
    store.add(chunks)

    print(f"\n청크 {len(chunks)}개 적재 완료 -> {PERSIST_DIR}")

    # 요약이 비어 있으면 검색은 되지만 답변 근거가 사라진다.
    # 조용히 진행되는 실패라 여기서 확인한다.
    empty = [c for c in chunks if not c.summary]
    if empty:
        print(f"경고: 요약이 빈 청크{len(empty)}개")

if __name__ == "__main__":
    main()