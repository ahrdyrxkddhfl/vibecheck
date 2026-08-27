"""whyd 명령줄 인터페이스.

인덱싱과 질문을 별도 명령으로 나눈다.
인덱싱은 LLM 호출로 비용과 시간이 드는 작업이므로,
질문 한 번 던지려다 모르는 사이에 요금이 나가는 일이 없어야 한다.
인덱스가 없으면 안내만 하고 멈춘다.

인덱스는 대상 레포 안의 .vibecheck에 저장한다.
레포마다 자기 인덱스를 갖게 되어 경로를 잘못 지정해 다른 레포의 청크가
섞이는 사고가 구조적으로 차단된다. collect_files의 EXCLUDE_DIRS에
.vibecheck가 있어 자기 인덱스를 자기가 인덱싱하는 일도 막힌다.

인덱스를 여는 절차 자체는 services/index_access.py에 있다.
이 모듈은 그 결과를 화면에 옮기는 일만 한다. 웹으로 옮길 때
버려지는 것은 이 파일이고 services는 그대로 살아남는다.
"""

from pathlib import Path

import typer

from vibecheck.core.collector import collect_files
from vibecheck.core.overview import build_overview
from vibecheck.core.quirks import find_quirks, group_quirks
from vibecheck.llm.anthropic import AnthropicClient
from vibecheck.services.index_access import (
    IndexEmpty,
    IndexNotFound,
    index_paths,
    open_index,
)
from vibecheck.services.indexer import index_repo
from vibecheck.services.interview import build_questions, format_questions
from vibecheck.services.practice import grade
from vibecheck.services.qa import answer
from vibecheck.services.report import build_report
from vibecheck.store.records import (
    connect,
    count_questions,
    get_question,
    get_repo_id,
    list_answers,
    repeated_assertions,
    save_answer,
    save_questions,
    verdict_summary,
)
from vibecheck.store.vector import VectorStore

app = typer.Typer(
    help="독스트링 없는 코드베이스를 인덱싱해 자연어로 질문한다.",
    no_args_is_help=True,
)

SUMMARY_MODEL = "claude-haiku-4-5-20251001"
ANSWER_MODEL = "claude-sonnet-4-6"

VERDICT_LABEL = {
    "confirmed": ("확인됨", typer.colors.GREEN),
    "contradicted": ("모순됨", typer.colors.RED),
    "unverifiable": ("확인불가", typer.colors.YELLOW),
}


def open_or_exit(repo: Path) -> tuple[list, str, dict]:
    """인덱스를 열고, 실패하면 안내 후 종료한다.

    open_index가 던지는 예외를 CLI 화면 출력으로 옮기는 자리다.
    services 계층이 typer를 모르게 하기 위해 이 변환을 CLI에 둔다.
    웹에서는 같은 예외를 HTTP 응답으로 옮기게 된다.

    Args:
        repo (Path): 대상 레포 루트. resolve된 상태여야 한다.

    Returns:
        tuple[list, str, dict]: (청크 목록, 벡터 저장소 경로, 인덱싱 조건).
            조건은 report와 interview가 제외 목록을 복원하는 데 쓴다.
    """
    try:
        chunks, chroma_dir, stale, meta = open_index(repo)
    except IndexNotFound:
        typer.secho(f"인덱스가 없습니다: {repo}", fg=typer.colors.RED)
        typer.echo(f"먼저 인덱싱하세요:  whyd index {repo}")
        raise typer.Exit(1)
    except IndexEmpty:
        typer.secho("인덱스가 비어 있습니다. 다시 인덱싱하세요.", fg=typer.colors.RED)
        raise typer.Exit(1)

    if stale:
        typer.secho(
            f"경고: 인덱싱 이후 변경된 청크 {stale}개를 건너뜁니다. "
            f"whyd index로 다시 인덱싱하세요.",
            fg=typer.colors.YELLOW,
        )

    return chunks, chroma_dir, meta


def resolve_excludes(exclude: list[str] | None, meta: dict) -> set[str] | None:
    """개요 계산에 쓸 제외 목록을 정한다.

    명시한 값이 이긴다. 없으면 인덱싱 때 쓴 값을 장부에서 복원한다.
    매번 --exclude를 다시 치게 하면 빼먹었을 때 인덱스와 어긋난 숫자가
    조용히 나온다. report와 interview가 같은 규칙을 써야 두 산출물의
    숫자가 서로 어긋나지 않는다.

    Args:
        exclude (list[str] | None): 명령줄로 받은 제외 목록.
        meta (dict): 장부에 기록된 인덱싱 조건.

    Returns:
        set[str] | None: 제외할 디렉토리 이름. 없으면 None.
    """
    if exclude:
        return set(exclude)

    stored = meta.get("exclude_dirs") or ()
    return set(stored) or None


def print_feedback(fb) -> None:
    """채점 결과를 화면에 출력한다.

    근거 없이 단정한 주장을 점수보다 먼저 보여준다.
    면접에서 무너지는 지점이 정확히 거기이고, 주장 목록 안에 섞어두면
    사용자가 지나칠 수 있다.

    같은 '확인불가'라도 유보한 경우는 초록으로 표시한다.
    verdict와 hedged를 분리해 저장한 이유가 화면에서 드러나는 지점이다.
    코드에 근거가 없다는 것을 알고 그렇게 말한 것은 감점 사유가 아니다.

    Args:
        fb (AnswerFeedback): 채점 결과.
    """
    typer.echo(f"\n질문: {fb.question}")

    typer.secho(
        f"\n구체성 {fb.specificity}  판단보정 {fb.calibration}  "
        f"근거밀착 {fb.groundedness}   합계 {fb.total}/6",
        fg=typer.colors.CYAN,
        bold=True,
    )

    risky = fb.risky_claims
    if risky:
        typer.secho(
            f"\n근거 없이 단정한 지점 {len(risky)}개", fg=typer.colors.RED, bold=True
        )
        for c in risky:
            typer.echo(f"  - {c.claim}")
            if c.note:
                typer.echo(f"    {c.note}")

    if fb.claims:
        typer.secho("\n주장별 판정", fg=typer.colors.CYAN)
        for c in fb.claims:
            label, color = VERDICT_LABEL[c.verdict]
            # 확인불가여도 유보했으면 문제가 아니다. 색으로 구분해준다.
            if c.verdict == "unverifiable" and c.hedged:
                color = typer.colors.GREEN
                label = "확인불가(유보함)"

            typer.secho(f"  [{label}]", fg=color, nl=False)
            typer.echo(f" {c.claim}")
            if c.evidence:
                typer.echo(f"           └ {c.evidence}")

    if fb.verdict_line:
        typer.secho(f"\n총평: {fb.verdict_line}", bold=True)
    if fb.revision:
        typer.echo(f"다시 쓴다면: {fb.revision}")

    if fb.evidence_chunks:
        typer.secho("\n채점에 사용한 근거:", fg=typer.colors.CYAN)
        for loc in fb.evidence_chunks:
            typer.echo(f"  {loc}")


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
            장부에 함께 기록되므로 report와 interview에서는 다시 칠 필요가 없다.
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

    store = VectorStore(persist_dir=chroma_dir)
    store.add(chunks)

    # 수집 대상에서 빠진 파일의 청크를 지운다. add는 upsert만 하므로
    # 이 호출이 없으면 삭제된 파일이 인덱스에 남아 검색에 계속 잡힌다.
    removed = store.prune([c.id for c in chunks])

    if removed:
        typer.secho(f"오래된 청크 {removed}개 삭제", fg=typer.colors.YELLOW)
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
    chunks, chroma_dir, _ = open_or_exit(repo)

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
        exclude (list[str]): 제외할 디렉토리 이름.
            넘기지 않으면 인덱싱 때 쓴 값을 장부에서 복원하므로
            평소에는 지정할 필요가 없다.
    """
    repo = repo.expanduser().resolve()
    chunks, _, meta = open_or_exit(repo)
    excludes = resolve_excludes(exclude, meta)

    typer.echo("개요를 조립하는 중...")
    overview = build_overview(str(repo), chunks, excludes)

    typer.echo("특이 지점을 찾는 중...")
    quirk_groups = group_quirks(
        find_quirks(str(repo), collect_files(str(repo), excludes))
    )

    typer.echo("요약을 생성하는 중...")
    text = build_report(
        overview, chunks, AnthropicClient(model=SUMMARY_MODEL), quirk_groups
    )

    target = output or (repo / "WHYD_REPORT.md")
    target.write_text(text, encoding="utf-8")

    typer.secho(f"\n리포트 생성 완료: {target}", fg=typer.colors.GREEN)


@app.command()
def interview(
    repo: Path = typer.Argument(..., help="예상질문을 만들 레포 경로"),
    output: Path = typer.Option(
        None, "--output", "-o", help="저장할 파일 경로 (기본: 화면 출력)"
    ),
    exclude: list[str] = typer.Option(
        None, "--exclude", "-e", help="제외할 디렉토리 이름"
    ),
) -> None:
    """인덱싱된 레포로 면접 예상질문을 만든다.

    Args:
        repo (Path): 대상 레포 루트.
        output (Path): 저장할 파일 경로. 없으면 화면에 출력한다.
        exclude (list[str]): 제외할 디렉토리 이름.
            넘기지 않으면 인덱싱 때 쓴 값을 장부에서 복원한다.
            report와 같은 규칙이라 두 산출물의 숫자가 어긋나지 않는다.
    """
    repo = repo.expanduser().resolve()
    chunks, _, meta = open_or_exit(repo)
    excludes = resolve_excludes(exclude, meta)

    overview = build_overview(str(repo), chunks, excludes)
    quirk_groups = group_quirks(
        find_quirks(str(repo), collect_files(str(repo), excludes))
    )

    # LLM을 부르지 않는다. 질문은 전부 조립이므로 비용도 대기도 없다.
    questions = build_questions(overview, quirk_groups)
    text = format_questions(questions, str(repo))

    # 질문을 저장해야 practice가 번호로 참조할 수 있다.
    # 화면 출력과 무관하게 항상 저장한다.
    conn = connect(repo)
    save_questions(conn, get_repo_id(conn, repo), questions)
    conn.close()

    if output:
        output.write_text(text, encoding="utf-8")
        typer.secho(f"예상질문 생성 완료: {output}", fg=typer.colors.GREEN)
    else:
        typer.echo(text)


@app.command()
def practice(
    repo: Path = typer.Argument(..., help="답변을 채점할 레포 경로"),
    question: str = typer.Option(None, "--question", "-q", help="답변한 질문 (직접 입력)"),
    question_no: int = typer.Option(
        None, "--question-no", "-n", help="interview 질문 번호로 고르기"
    ),
    answer_file: Path = typer.Option(
        None, "--answer-file", "-f", help="답변이 담긴 파일 경로"
    ),
    answer_text: str = typer.Option(
        None, "--answer", "-a", help="답변을 직접 입력 (짧은 답변용)"
    ),
    top_k: int = typer.Option(8, "--top-k", "-k", help="근거로 사용할 청크 수"),
) -> None:
    """작성한 면접 답변을 코드 근거와 대조해 채점한다.

    답변을 파일로 받는 것이 기본이다. 여러 줄 입력을 터미널에서 받는 UX는
    웹으로 옮기면 버려질 코드이고, 파일로 두면 같은 답변을 조건을 바꿔가며
    반복 채점할 수 있어 채점기 자체를 검증하기에도 낫다.

    답변을 먼저 읽고 인덱스를 나중에 여는 순서인 이유는, 답변 경로가 틀렸을 때
    임베딩 모델을 올리는 몇 초를 기다린 뒤에 오류를 보게 하지 않기 위해서다.

    Args:
        repo (Path): 대상 레포 루트.
        question (str): 답변한 질문. 검색 쿼리로도 사용된다.
        question_no (int): interview 질문 번호. question과 둘 중 하나가 필요하다.
        answer_file (Path): 답변이 담긴 파일.
        answer_text (str): 답변 직접 입력. answer_file이 우선한다.
        top_k (int): 근거로 사용할 청크 수.
    """
    repo = repo.expanduser().resolve()
    question_id = None

    # 질문을 먼저 정한다. 번호로 고르면 저장된 질문에서 문장을 꺼내온다.
    if question_no is not None:
        conn = connect(repo)
        repo_id = get_repo_id(conn, repo)
        row = get_question(conn, repo_id, question_no)
        total = count_questions(conn, repo_id)
        conn.close()

        if row is None:
            if total == 0:
                typer.secho("저장된 질문이 없습니다.", fg=typer.colors.RED)
                typer.echo(f"먼저 질문을 만드세요:  whyd interview {repo}")
            else:
                typer.secho(
                    f"{question_no}번 질문이 없습니다. 1에서 {total} 사이로 지정하세요.",
                    fg=typer.colors.RED,
                )
            raise typer.Exit(1)

        question = row["text"]
        question_id = row["id"]
        typer.echo(f"Q{question_no}. {question}")

    elif question is None:
        typer.secho(
            "--question 또는 --question-no 중 하나가 필요합니다.", fg=typer.colors.RED
        )
        raise typer.Exit(1)

    if answer_file:
        try:
            user_answer = answer_file.expanduser().read_text(encoding="utf-8")
        except OSError as e:
            typer.secho(f"답변 파일을 읽을 수 없습니다: {e}", fg=typer.colors.RED)
            raise typer.Exit(1)
    elif answer_text:
        user_answer = answer_text
    else:
        typer.secho(
            "--answer-file 또는 --answer 중 하나가 필요합니다.", fg=typer.colors.RED
        )
        raise typer.Exit(1)

    if not user_answer.strip():
        typer.secho("답변이 비어 있습니다.", fg=typer.colors.RED)
        raise typer.Exit(1)

    chunks, chroma_dir, _ = open_or_exit(repo)

    typer.echo("채점하는 중...")
    fb = grade(
        question,
        user_answer,
        chunks,
        VectorStore(persist_dir=chroma_dir),
        AnthropicClient(model=ANSWER_MODEL),
        top_k=top_k,
    )

    print_feedback(fb)

    # 화면에 뿌린 뒤 저장한다. 저장이 실패해도 사용자는 피드백을 이미 받았다.
    conn = connect(repo)
    save_answer(conn, get_repo_id(conn, repo), fb, question_id)
    conn.close()


@app.command()
def history(
    repo: Path = typer.Argument(..., help="기록을 볼 레포 경로"),
    limit: int = typer.Option(10, "--limit", "-l", help="표시할 답변 수"),
) -> None:
    """지금까지의 연습 기록과 누적 경향을 본다.

    개별 점수보다 누적 비율을 위에 둔다.
    한 번 단정한 것은 실수지만 계속 단정하는 것은 습관이고,
    이 도구가 알려주려는 것은 후자다.

    Args:
        repo (Path): 대상 레포 루트.
        limit (int): 표시할 답변 수.
    """
    repo = repo.expanduser().resolve()

    conn = connect(repo)
    repo_id = get_repo_id(conn, repo)

    answers = list_answers(conn, repo_id, limit)
    summary = verdict_summary(conn, repo_id)
    risky = repeated_assertions(conn, repo_id)

    conn.close()

    if not answers:
        typer.secho("아직 연습 기록이 없습니다.", fg=typer.colors.YELLOW)
        typer.echo(f"연습을 시작하세요:  whyd interview {repo}")
        raise typer.Exit(0)

    typer.secho(f"\n연습 기록 ({len(answers)}건)", fg=typer.colors.CYAN, bold=True)
    for a in answers:
        date = a["created_at"][:10]
        total = a["specificity"] + a["calibration"] + a["groundedness"]
        typer.echo(f"  {date}  {total}/6  {a['question_text'][:45]}")

    confirmed = summary.get("confirmed:0", 0) + summary.get("confirmed:1", 0)
    asserted = summary.get("unverifiable:0", 0) + summary.get("contradicted:0", 0)
    hedged = summary.get("unverifiable:1", 0) + summary.get("contradicted:1", 0)

    typer.secho("\n주장 판정 누적", fg=typer.colors.CYAN, bold=True)
    typer.secho(f"  코드로 확인됨       {confirmed}회", fg=typer.colors.GREEN)
    typer.secho(f"  근거 없이 단정      {asserted}회", fg=typer.colors.RED)
    typer.secho(f"  근거 없음을 밝힘    {hedged}회", fg=typer.colors.GREEN)

    # 비율로 한 줄 짚어준다. 숫자만 보면 자기 경향을 알아채지 못한다.
    unverified = asserted + hedged
    if unverified >= 3:
        rate = asserted / unverified
        if rate >= 0.7:
            typer.secho(
                "\n코드에 근거가 없는 내용을 대부분 단정하고 있습니다. "
                "면접에서 되물으면 무너지는 지점입니다.",
                fg=typer.colors.RED,
            )
        elif rate <= 0.3:
            typer.secho(
                "\n확인할 수 없는 것을 밝히는 습관이 자리잡았습니다.",
                fg=typer.colors.GREEN,
            )

    if risky:
        typer.secho("\n근거 없이 단정한 주장", fg=typer.colors.CYAN, bold=True)
        for r in risky:
            typer.echo(f"  - {r['claim'][:70]}")


def main() -> None:
    """콘솔 스크립트 진입점."""
    app()


if __name__ == "__main__":
    main()