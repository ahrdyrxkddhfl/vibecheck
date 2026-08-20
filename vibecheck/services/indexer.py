"""파이프라인 전체를 조립해 레포를 인덱싱한다.

수집, 파싱, 청킹, 요약을 순서대로 실행한다. 각 단계의 구현은 core 모듈에 있고,
이 모듈은 순서와 흐름만 담당한다. 조립을 별도 계층으로 분리해야 CLI와 향후 웹 API가
같은 파이프라인을 공유할 수 있다.
"""

from vibecheck.core.chunker import to_chunks
from vibecheck.core.collector import collect_files, to_relative
from vibecheck.core.parser import parse_file, walk
from vibecheck.core.summarizer import summarize_all
from vibecheck.llm.base import LLMClient
from vibecheck.models import Chunk

def index_repo(root: str, llm: LLMClient, verbose: bool = True) -> list[Chunk]:
    """레포를 인덱싱해 요약이 채워진 청크 목록을 반환한다.

    Args:
        root (str): 레포 루트 경로.
        llm (LLMClient): 요약에 사용할 LLM 클라이언트.
        verbose (bool): 진행 상황 출력 여부. 인덱싱은 파일 수에 비례해
            수 분이 걸릴 수 있으므로 기본값을 True로 두어 사용자가 멈춘
            것으로 오해하지 않게 한다.
    Returns:
        list[Chunk]: 요약이 채워진 청크 목록.
    """
    files = collect_files(root)
    if verbose:
        print(f"[1/3] 파일 {len(files)}개 수집")

    chunks: lsit[Chunk] = []
    for path in files:
        tree, source = parse_file(str(path))
        symbols = walk(tree.root_node, source)
        chunks.extend(to_chunks(symbols, source, to_relative(path, root)))

    if verbose:
        print(f"[2/3] 청크 {len(chunks)}개 생성")
        print(f"[3/3] 요약 생성 중...")

    return summarize_all(chunks, llm)

if __name__ == "__main__":
    import sys

    from vibecheck.llm.anthropic import AnthropicClient
    from vibecheck.store.vector import VectorStore

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    chunks = index_repo(target, AnthropicClient())

    store = VectorStore()
    store.add(chunks)
    print(f"\n저장 완료: {store.count()}개 청크")