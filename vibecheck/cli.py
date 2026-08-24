"""whyd 명령줄 인터페이스.

인덱싱과 질문을 별도 명령으로 나눈다.
인덱싱은 LLM 호출로 비용과 시간이 드는 작업이므로,
질문 한 번 던지려다 모르는 사이에 요금이 나가는 일이 없어야 한다.
인덱스가 없으면 안내만 하고 멈춘다.

인덱스는 대상 레포 안의 .vibecheck에 저장한다.
레포마다 자기 인덱스를 갖게 되어 경로를 잘못 지정해 다른 레포의 청크가
섞이는 사고가 구조적으로 차단된다. collect_files의 EXCLUDE_DIRS에
.vibecheck가 있어 자기 인덱스를 자기가 인덱싱하는 일도 막힌다.
"""

from pathlib import Path

import typer

from vibecheck.core.collector import collect_files
from vibecheck.core.quirks import find_quirks, group_quirks
from vibecheck.core.overview import build_overview
from vibecheck.services.report import build_report
from vibecheck.llm.anthropic import AnthropicClient
from vibecheck.models import Chunk
from vibecheck.services.indexer import index_repo
from vibecheck.services.qa import answer
from vibecheck.store.vector import VectorStore

app = typer.Typer(
    help="독스트링 없는 코드베이스를 인덱싱해 자연어로 질문한다.",
    no_args_is_help=True,
)

INDEX_DIRNAME = ".vibecheck"
SUMMARY_MODEL = "claude-haiku-4-5-20251001"
ANSWER_MODEL = "claude-sonnet-4-6"


def index_paths(repo: Path) -> tuple[str, str]:
    """레포 경로로부터 캐시 장부와 벡터 저장소 경로를 만든다.

    두 경로를 한곳에서 계산하는 이유는 요약 캐시와 벡터 인덱스가 짝을 이루기 때문이다.
    한쪽만 남으면 캐시는 있는데 검색이 안 되거나 그 반대가 되어,
    실패가 조용히 진행된다.

    Args:
        repo (Path): 대상 레포 루트.

    Returns:
        tuple[str, str]: (캐시 장부 디렉토리, 벡터 저장소 디렉토리).
    """
    base = repo / INDEX_DIRNAME
    return str(base), str(base / "chroma")


def load_indexed_chunks(repo: Path, persist_dir: str) -> list[Chunk]:
    """저장된 인덱스로부터 코드 본문이 채워진 청크 목록을 복원한다.

    벡터 저장소에는 임베딩 텍스트와 메타데이터만 있고 코드 원문이 없다.
    answer()는 원문을 컨텍스트로 넘겨야 하므로 소스 파일에서 줄 범위를 다시 읽는다.

    파일이 사라졌거나 줄 수가 줄었으면 그 청크를 건너뛴다.
    인덱싱 이후 코드가 바뀌면 발생할 수 있는데, 여기서 멈추면
    질문 자체가 불가능해지므로 남은 청크로 답하고 경고만 남긴다.

    Args:
        repo (Path): 대상 레포 루트.
        persist_dir (str): 벡터 저장소 경로.

    Returns:
        list[Chunk]: 코드 본문이 채워진 청크 목록.
    """
    import chromadb

    col = chromadb.PersistentClient(path=persist_dir).get_collection("chunks")
    got = col.get()

    chunks = []
    stale = 0

    for meta in got["metadatas"]:
        path = repo / meta["file"]
        try:
            src_lines = path.read_text(encoding="utf-8").split("\n")
        except OSError:
            stale += 1
            continue

        if meta["end_line"] > len(src_lines):
            stale += 1
            continue

        chunks.append(
            Chunk(
                file=meta["file"],
                symbol=meta["symbol"],
                kind=meta["kind"],
                start_line=meta["start_line"],
                end_line=meta["end_line"],
                code="\n".join(src_lines[meta["start_line"] - 1 : meta["end_line"]]),
                summary=meta["summary"],
                imports=meta.get("imports", "").split(",") if meta.get("imports") else [],
            )
        )

    if stale:
        typer.secho(
            f"경고: 인덱싱 이후 변경된 청크 {stale}개를 건너뜁니다. "
            f"whyd index로 다시 인덱싱하세요.",
            fg=typer.colors.YELLOW,
        )

    return chunks


@app.command()
def index(
    repo: Path = typer.Argument(..., help="인덱싱할 레포 경로"),
    exclude: list[str] = typer.Option(
        None, "--exclude", "-e", help="추가로 제외할 디렉토리 이름 (여러 번 지정 가능)"
    ),
) -> None:
    """레포를 인덱싱한다.

    Args:
        repo (Path): 인덱싱할 레포 루트.
        exclude (list[str]): 기본 제외 목록에 더할 디렉토리 이름.
    """
    repo = repo.expanduser().resolve()
    if not repo.is_dir():
        typer.secho(f"디렉토리가 아닙니다: {repo}", fg=typer.colors.RED)
        raise typer.Exit(1)

    persist_base, chroma_dir = index_paths(repo)

    chunks = index_repo(
        str(repo),
        AnthropicClient(model=SUMMARY_MODEL),
        verbose=True,
        persist_dir=persist_base,
        exclude_dirs=set(exclude) if exclude else None,
    )

    if not chunks:
        typer.secho("인덱싱할 코드를 찾지 못했습니다.", fg=typer.colors.RED)
        raise typer.Exit(1)

    VectorStore(persist_dir=chroma_dir).add(chunks)

    typer.secho(f"\n완료: 청크 {len(chunks)}개 -> {persist_base}", fg=typer.colors.GREEN)
    typer.echo(f'이제 질문할 수 있습니다:  whyd ask {repo} "질문 내용"')


@app.command()
def ask(
    repo: Path = typer.Argument(..., help="질문할 레포 경로"),
    question: str = typer.Argument(..., help="질문 내용"),
    top_k: int = typer.Option(8, "--top-k", "-k", help="컨텍스트에 포함할 청크 수"),
    show_sources: bool = typer.Option(
        True, "--sources/--no-sources", help="근거 청크 목록 출력 여부"
    ),
) -> None:
    """인덱싱된 레포에 질문한다.

    Args:
        repo (Path): 질문할 레포 루트.
        question (str): 질문 내용.
        top_k (int): 컨텍스트에 포함할 청크 수.
        show_sources (bool): 근거 청크 목록 출력 여부.
    """
    repo = repo.expanduser().resolve()
    persist_base, chroma_dir = index_paths(repo)

    # 자동 인덱싱하지 않는다. 질문 한 번에 요금과 수 분이 나가는 것을
    # 사용자가 모르는 채로 겪게 해서는 안 된다.
    if not Path(chroma_dir).exists():
        typer.secho(f"인덱스가 없습니다: {repo}", fg=typer.colors.RED)
        typer.echo(f"먼저 인덱싱하세요:  whyd index {repo}")
        raise typer.Exit(1)

    chunks = load_indexed_chunks(repo, chroma_dir)
    if not chunks:
        typer.secho("인덱스가 비어 있습니다. 다시 인덱싱하세요.", fg=typer.colors.RED)
        raise typer.Exit(1)

    text, sources = answer(
        question,
        chunks,
        VectorStore(persist_dir=chroma_dir),
        AnthropicClient(model=ANSWER_MODEL),
        top_k=top_k,
    )

    typer.echo(f"\n{text}\n")

    if show_sources:
        typer.secho("근거:", fg=typer.colors.CYAN)
        for c in sources:
            typer.echo(f"  {c.file}:{c.start_line}-{c.end_line}  {c.symbol}")

@app.command()
def report(
    repo: Path = typer.Argument(..., help="리포트를 만들 레포 경로"),
    output: Path = typer.Option(
        None, "--output", "-o", help="저장할 파일 경로 (기본: <레포>/WHYD_REPORT.md)"
    ),
    exclude: list[str] = typer.Option(
        None, "--exclude", "-e", help="개요 계산에서 제외할 디렉토리 이름"
    ),
) -> None:
    """인덱싱된 레포의 개요 리포트를 만든다.

    Args:
        repo (Path): 대상 레포 루트.
        output (Path): 저장할 파일 경로.
        exclude (list[str]): 인덱싱 때와 같은 제외 목록.
            다른 값을 넘기면 내부/외부 판정이 인덱스와 어긋난다.
    """
    repo = repo.expanduser().resolve()
    _, chroma_dir = index_paths(repo)

    if not Path(chroma_dir).exists():
        typer.secho(f"인덱스가 없습니다: {repo}", fg=typer.colors.RED)
        typer.echo(f"먼저 인덱싱하세요:  whyd index {repo}")
        raise typer.Exit(1)

    chunks = load_indexed_chunks(repo, chroma_dir)
    if not chunks:
        typer.secho("인덱스가 비어 있습니다. 다시 인덱싱하세요.", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.echo("개요를 조립하는 중...")
    overview = build_overview(str(repo), chunks, set(exclude) if exclude else None)

    typer.echo("특이 지점을 찾는 중...")
    quirk_groups = group_quirks(
        find_quirks(str(repo), collect_files(str(repo), set(exclude) if exclude else None))
    )

    typer.echo("요약을 생성하는 중...")
    text = build_report(
        overview, chunks, AnthropicClient(model=SUMMARY_MODEL), quirk_groups
    )

    target = output or (repo / "WHYD_REPORT.md")
    target.write_text(text, encoding="utf-8")

    typer.secho(f"\n리포트 생성 완료: {target}", fg=typer.colors.GREEN)

def main() -> None:
    """콘솔 스크립트 진입점."""
    app()


if __name__ == "__main__":
    main()