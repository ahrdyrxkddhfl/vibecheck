"""파이프라인 전체를 조립해 레포를 인덱싱한다.

수집, 파싱, 청킹, 요약을 순서대로 실행한다. 각 단계의 구현은 core 모듈에 있고,
이 모듈은 순서와 흐름만 담당한다. 조립을 별도 계층으로 분리해야 CLI와 향후 웹 API가
같은 파이프라인을 공유할 수 있다.
"""

import sys

from vibecheck.store.manifest import Manifest
from vibecheck.core.chunker import (
    to_chunks,
    to_file_chunk,
    to_pyproject_chunk,
    to_readme_chunks,
)
from vibecheck.core.callgraph import build_call_map
from vibecheck.core.collector import (
    collect_source_files,
    format_skipped,
    group_by_extension,
    to_relative,
)
from vibecheck.core.summarizer import summarize_all
from vibecheck.core.languages import spec_for
from vibecheck.core.parser import enclosing, parse_file, walk
from vibecheck.llm.base import LLMClient
from vibecheck.models import CallSite, Chunk, Symbol

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

    수집에서 빠진 파일은 마지막에 확장자별로 보고한다.
    파이썬이 아닌 파일로 이루어진 레포에서도 인덱싱이 성공한 것처럼 끝나면
    사용자는 레포 전체가 분석된 줄 알고 결과를 신뢰한다.
    보고 시점이 수집 직후가 아니라 마지막인 이유는, 무엇이 빠졌는지 말하려면
    무엇이 들어갔는지가 먼저 확정되어야 하기 때문이다.
    README와 pyproject.toml은 수집 대상이 아니면서 별도 경로로 청크가 되므로,
    청크가 다 만들어진 뒤에야 제외 목록에서 뺄 수 있다.

    Args:
        root (str): 레포 루트 경로.
        llm (LLMClient): 요약에 사용할 LLM 클라이언트.
        verbose (bool): 진행 상황 출력 여부. 인덱싱은 파일 수에 비례해
            수 분이 걸릴 수 있으므로 기본값을 True로 두어 사용자가 멈춘
            것으로 오해하지 않게 한다.
        persist_dir (str): 캐시 장부를 저장할 디렉토리.
            벡터 인덱스와 짝을 이루므로 같은 위치를 지정해야 한다. 
        exclude_dirs (set[str] | None): 기본 제외 목록에 더할 디렉토리 이름.
            collect_source_files로 그대로 전달된다. 실험에서 테스트를 채점용
            정답지로 쓸 때 인덱스에서 빼는 용도이며, 평소에는 넘기지 않는다.

    Returns:
        list[Chunk]: 요약이 채워진 청크 목록.
            함수·클래스 단위 청크(L2)와 파일 단위 개요 청크(L1)가 섞여 있다.
            L1은 함수 단위로는 담기지 않는 import 정보와 심볼 목록을
            검색 대상으로 만들기 위한 것으로, LLM 호출 없이 조립된다.
    """
    collected = collect_source_files(root, exclude_dirs)
    files = collected.files
    if verbose:
        print(f"[1/3] 파일 {len(files)}개 수집")

    manifest = Manifest(persist_dir=persist_dir)

    all_chunks: list[Chunk] = []
    cache_hits = 0
    summarized = 0

    # 요약은 파일 수에 비례해 수 분이 걸리는데 그동안 아무것도 찍지 않으면 멈춘 것으로
    # 보인다. 청크 수백 개인 레포에서 실제로 그렇게 보였다. 한 줄을 덮어쓰며 진행을
    # 보여준다. 터미널이 아니면(파이프, 로그) 덮어쓰기가 줄마다 쌓이므로 끈다.
    show_progress = verbose and sys.stdout.isatty()

    # 호출 해석에 쓸 재료를 모아둔다. 파일 하나를 보는 동안에는
    # "이 이름의 정의가 레포에 하나뿐인가"를 답할 수 없어 여기서 정하지 못한다.
    # 이미 파싱한 트리에서 꺼내므로 파일을 다시 읽지 않는다.
    symbols_by_file: dict[str, list[Symbol]] = {}
    calls_by_file: dict[str, list[tuple[CallSite, Symbol]]] = {}
    imports_by_file: dict[str, list[str]] = {}

    for i, path in enumerate(files, start=1):
        if show_progress:
            print(
                f"\r\033[K      파일 {i}/{len(files)} · 새로 요약 {summarized}개",
                end="",
                flush=True,
            )

        # 수집기가 지원 확장자만 넘기므로 여기서 None이 나오지 않는다.
        spec = spec_for(path)
        tree, source = parse_file(str(path), spec.language)
        symbols = walk(
            tree.root_node,
            source,
            class_types=spec.class_types,
            function_types=spec.function_types,
            doc_comment=spec.doc_comment,
        )
        docstring = spec.extract_docstring(tree.root_node, source)
        imports = spec.extract_imports(tree.root_node, source)

        rel = to_relative(path, root)
        text = source.decode()
        chunks = to_chunks(symbols, source, rel, imports)

        symbols_by_file[rel] = symbols
        imports_by_file[rel] = imports
        # 어느 심볼에도 속하지 않는 호출은 붙일 자리가 없다. 청크가 심볼 단위다.
        calls_by_file[rel] = [
            (call, holder)
            for call in (
                spec.collect_calls(tree.root_node, source) if spec.collect_calls else []
            )
            if (holder := enclosing(symbols, call.line)) is not None
        ]

        # 심볼이 없는 파일도 L1까지는 내려보낸다.
        # 여기서 continue하면 __init__.py처럼 정의가 없는 파일이
        # 예외 한 줄 없이 인덱스에서 통째로 사라진다.
        if chunks:
            # 캐시를 먼저 채운다. summarize()는 summary가 있으면 건너뛰므로
            # 이 한 줄로 변경되지 않은 청크의 LLM 호출이 사라진다.
            hits = manifest.apply(chunks, str(path))
            cache_hits += hits

            summarize_all(chunks, llm)
            manifest.update(chunks, str(path))

            # 새로 요약한 것이 있으면 바로 저장한다. 끝에 한 번만 저장하던 때는
            # 중간에 끊으면 이미 요금을 낸 요약까지 전부 사라졌다. update는
            # pending에만 적으므로 이 저장이 인덱스 기록을 바꾸지는 않는다.
            new = len(chunks) - hits
            if new:
                summarized += new
                manifest.save()

            all_chunks.extend(chunks)

        # L1은 L2 요약을 조립하므로 summarize_all 이후에 만든다.
        # manifest에는 넣지 않는다. 캐시의 단위는 LLM 호출인데
        # L1은 호출 없이 조립되므로 캐싱할 대상이 아니다.
        file_chunk = to_file_chunk(
            chunks,
            rel,
            len(text.splitlines()),
            imports,
            source_text=text,
            docstring=docstring,
        )
        if file_chunk:
            all_chunks.append(file_chunk)

    # 파이썬 파일이 아니라 루프 밖에서 한 번만 만든다.
    # 설치하면 생기는 명령과 그 진입 함수는 이 파일에만 있어,
    # 없으면 진입점을 정확히 말한 답변도 근거를 댈 수 없다.
    pyproject = to_pyproject_chunk(root)
    if pyproject:
        all_chunks.append(pyproject)

    # 프로젝트가 무엇을 위한 것인지는 코드에 없다. 목적을 정확히 말한
    # 답변도 근거를 댈 수 없어 확인불가가 된다.
    all_chunks.extend(to_readme_chunks(root))

    # 호출 해석은 모든 파일을 훑은 뒤에야 가능하다.
    # 요약 재료에는 넣지 않는다. 재료가 바뀌면 캐시가 통째로 무효가 되어
    # 레포 전체를 다시 요약하게 되는데, calls의 용도는 유사도 검색이 아니라
    # "이 함수는 어디서 쓰이는가"를 정확 조회로 답하는 것이다.
    call_map, call_stats = build_call_map(
        symbols_by_file, calls_by_file, imports_by_file
    )
    for chunk in all_chunks:
        chunk.calls = call_map.get(chunk.id, [])

    if show_progress:
        # 덮어쓰던 진행 줄을 지워, 아래 요약 줄이 그 자리에서 시작하게 한다.
        print("\r\033[K", end="", flush=True)

    # 여기까지 왔으면 모든 파일을 끝까지 처리했다. 새로 요약한 것을 인덱스 기록으로
    # 옮긴다. 도중에 끊기면 이 줄에 닿지 않아 기록은 옛 인덱스 그대로 남는다.
    manifest.commit()

    # 제외 대상이 된 파일의 캐시가 장부에 영구히 남는 것을 막는다.
    # update는 처리한 파일만 덮어쓰므로 지우는 자리가 여기밖에 없다.
    # README·pyproject 청크는 update를 타지 않아 장부에 항목이 없다.
    manifest.prune({to_relative(p, root) for p in files})

    # 리포트·면접 질문이 같은 조건으로 계산되려면 조건이 남아 있어야 한다.
    # 끝에서 기록하는 이유는 commit과 같다. 도중의 저장에 새 조건이 실리면,
    # 끊긴 뒤 옛 인덱스를 새 조건으로 읽게 된다.
    manifest.set_index_meta(exclude_dirs, len(files))

    manifest.save()

    if verbose:
        total = len(all_chunks)
        l1 = sum(1 for c in all_chunks if c.kind == "file")
        docs = sum(1 for c in all_chunks if c.kind == "doc")
        configs = sum(1 for c in all_chunks if c.kind == "config")
        l2 = total - l1 - docs - configs
        parts = f"L2 {l2}개 + L1 {l1}개"
        if docs:
            parts += f" + 문서 {docs}개"
        if configs:
            parts += f" + 설정 {configs}개"
        print(f"[2/3] 청크 {total}개 생성 ({parts})")
        print(f"[3/3] 요약 완료 (캐시 재사용 {cache_hits}개 / 신규 {l2 - cache_hits}개)")

        linked = sum(len(c.calls) for c in all_chunks)
        unresolved = call_stats.get("모호", 0)
        note = f"호출 {linked}건 연결"
        if unresolved:
            # 이름이 겹쳐 끝내 좁히지 못한 수다. 찍지 않고 버린 것이므로
            # 틀린 화살표는 아니지만, 늘어나면 규칙을 손볼 자리가 된다.
            note += f" (모호해서 버린 것 {unresolved}건)"
        print(note)

        # 청크가 생긴 파일을 그대로 쓴다. README나 pyproject의 이름을
        # 직접 적으면 README.rst처럼 관례를 벗어난 레포에서 바로 틀린다.
        indexed = {c.file for c in all_chunks}

        skipped = group_by_extension(collected.skipped_other, root, indexed)
        line = format_skipped(skipped)
        if line:
            print(line)

        # 크기 초과는 종류가 다른 누락이다. 확장자가 대상이 아닌 파일과 달리
        # 사용자가 분석되리라 믿는 파이썬 파일이 빠진 것이라 이름까지 밝힌다.
        for path in collected.skipped_by_size:
            print(f"크기 초과 제외: {to_relative(path, root)}")

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
