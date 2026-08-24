"""파이프라인 전체를 조립해 레포를 인덱싱한다.

수집, 파싱, 청킹, 요약을 순서대로 실행한다. 각 단계의 구현은 core 모듈에 있고,
이 모듈은 순서와 흐름만 담당한다. 조립을 별도 계층으로 분리해야 CLI와 향후 웹 API가
같은 파이프라인을 공유할 수 있다.
"""

from vibecheck.store.manifest import Manifest
from vibecheck.core.chunker import to_chunks, to_file_chunk
from vibecheck.core.collector import collect_files, to_relative
from vibecheck.core.summarizer import summarize_all
from vibecheck.core.parser import extract_imports, parse_file, walk
from vibecheck.llm.base import LLMClient
from vibecheck.models import Chunk

def index_repo(
        root: str,
        llm: LLMClient,
        verbose: bool = True,
        persist_dir: str = ".vibecheck",
        exclude_dirs: set[str] | None = None,
    ) -> list[Chunk]:
    """레포를 인덱싱해 요약이 채워진 청크 목록을 반환한다.

    파일 단위로 캐시를 확인한 뒤 요약한다.
    파일이 변경되지 않았다면 저장된 요약을 재사용해 LLM 호출을 건너뛴다.
    인덱싱 비용의 대부분이 요약 호출이므로, 반복 인덱싱에서 이 절감이 크다.

    Args:
        root (str): 레포 루트 경로.
        llm (LLMClient): 요약에 사용할 LLM 클라이언트.
        verbose (bool): 진행 상황 출력 여부. 인덱싱은 파일 수에 비례해
            수 분이 걸릴 수 있으므로 기본값을 True로 두어 사용자가 멈춘
            것으로 오해하지 않게 한다.
        persist_dir (str): 캐시 장부를 저장할 디렉토리.
            벡터 인덱스와 짝을 이루므로 같은 위치를 지정해야 한다. 
        exclude_dirs (set[str] | None): 기본 제외 목록에 더할 디렉토리 이름.
            collect_files로 그대로 전달된다. 실험에서 테스트를 채점용 정답지로 쓸 때
            인덱스에서 빼는 용도이며, 평소에는 넘기지 않는다.
    Returns:
        Returns:
            list[Chunk]: 요약이 채워진 청크 목록.
                함수·클래스 단위 청크(L2)와 파일 단위 개요 청크(L1)가 섞여 있다.
                L1은 함수 단위로는 담기지 않는 import 정보와 심볼 목록을
                검색 대상으로 만들기 위한 것으로, LLM 호출 없이 조립된다.
    """
    files = collect_files(root, exclude_dirs)
    if verbose:
        print(f"[1/3] 파일 {len(files)}개 수집")

    manifest = Manifest(persist_dir=persist_dir)

    all_chunks: list[Chunk] = []
    cache_hits = 0

    for path in files:
        tree, source = parse_file(str(path))
        symbols = walk(tree.root_node, source)
        imports = extract_imports(tree.root_node, source)
        chunks = to_chunks(symbols, source, to_relative(path, root), imports)

        if not chunks:
            continue

        # 캐시를 먼저 채운다. summarize()는 summary가 있으면 건너뛰므로 
        # 이 한 줄로 변경되지 않은 청크의 LLM 호출이 사라진다.
        cache_hits += manifest.apply(chunks, str(path))

        summarize_all(chunks, llm)
        manifest.update(chunks, str(path))

        all_chunks.extend(chunks)

        # L1은 L2 요약을 조립하므로 summarize_all 이후에 만든다.
        # manifest에는 넣지 않는다. 캐시의 단위는 LLM 호출인데
        # L1은 호출 없이 조립되므로 캐싱할 대상이 아니다.
        file_chunk = to_file_chunk(
            chunks,
            to_relative(path, root),
            len(source.decode().splitlines()),
            imports,
        )
        if file_chunk:
            all_chunks.append(file_chunk)

    manifest.save()

    if verbose:
        total = len(all_chunks)
        l1 = sum(1 for c in all_chunks if c.kind == "file")
        print(f"[2/3] 청크 {total}개 생성 (L2 {total - l1}개 + L1 {l1}개)")
        print(f"[3/3] 요약 완료 (캐시 재사용 {cache_hits}개 / 신규 {total - l1 - cache_hits}개)")
    return all_chunks

if __name__ == "__main__":
    import sys

    from vibecheck.llm.anthropic import AnthropicClient
    from vibecheck.store.vector import VectorStore

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    chunks = index_repo(target, AnthropicClient())

    store = VectorStore()
    store.add(chunks)
    print(f"\n저장 완료: {store.count()}개 청크")