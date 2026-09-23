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

import shlex
import sqlite3
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote

import typer

from vibecheck.core.collector import collect_files
from vibecheck.core.overview import build_overview
from vibecheck.core.quirks import find_quirks, group_quirks
from vibecheck.llm.anthropic import ANSWER_MODEL, SUMMARY_MODEL, AnthropicClient
from vibecheck.llm.errors import LLM_ERRORS, describe_llm_error
from vibecheck.services.index_access import (
    IndexEmpty,
    IndexNotFound,
    index_paths,
    load_index_meta,
    open_index,
)
from vibecheck.services.history import tally
from vibecheck.services.indexer import index_repo
from vibecheck.services.interview import build_questions, format_questions
from vibecheck.services.practice import grade
from vibecheck.services.qa import answer, source_refs
from vibecheck.services.report import build_report, report_path
from vibecheck.store.records import (
    connect,
    count_asks,
    count_questions,
    get_question,
    get_repo_id,
    list_answers,
    repeated_assertions,
    save_answer,
    save_ask,
    save_questions,
    verdict_summary,
)
from vibecheck.store.vector import VectorStore

app = typer.Typer(
    help="독스트링 없는 코드베이스를 인덱싱해 자연어로 질문한다.",
    no_args_is_help=True,
)


VERDICT_LABEL = {
    "confirmed": ("확인됨", typer.colors.GREEN),
    "contradicted": ("모순됨", typer.colors.RED),
    "unverifiable": ("확인불가", typer.colors.YELLOW),
}


def open_or_exit(repo: Path) -> tuple[list, str, dict, int]:
    """인덱스를 열고, 실패하면 안내 후 종료한다.

    open_index가 던지는 예외를 CLI 화면 출력으로 옮기는 자리다.
    services 계층이 typer를 모르게 하기 위해 이 변환을 CLI에 둔다.
    웹에서는 같은 예외를 HTTP 응답으로 옮기게 된다.

    Args:
        repo (Path): 대상 레포 루트. resolve된 상태여야 한다.

    Returns:
        tuple[list, str, dict, int]: (청크 목록, 벡터 저장소 경로, 인덱싱 조건,
            건너뛴 청크 수). 조건은 report와 interview가 제외 목록을 복원하는 데
            쓴다. 건너뛴 수는 경고로 찍는 데서 끝나지 않고 report가 리포트 파일에
            적는다. 파일만 보는 사람은 이 경고를 보지 못한다.
    """
    try:
        chunks, chroma_dir, stale, meta = open_index(repo)
    except IndexNotFound:
        typer.secho(f"인덱스가 없습니다: {repo}", fg=typer.colors.RED)
        typer.echo(f"먼저 인덱싱하세요:  whyd index {shlex.quote(str(repo))}")
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

    return chunks, chroma_dir, meta, stale


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

    # 재인덱싱할 때 --exclude를 다시 치지 않아도 되게 한다.
    # 빠뜨리면 조건이 조용히 바뀌어 인덱스가 통째로 덮어써지고,
    # 그 뒤의 리포트와 채점이 이전 결과와 비교 불가능해진다.
    excludes = resolve_excludes(exclude, load_index_meta(persist_base))

    if excludes and not exclude:
        typer.echo(f"이전 제외 목록을 이어씁니다: {', '.join(sorted(excludes))}")

    chunks = index_repo(
        str(repo),
        AnthropicClient(model=SUMMARY_MODEL),
        verbose=True,
        persist_dir=persist_base,
        exclude_dirs=excludes,
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
    # 복사해 붙여 쓰라고 내놓는 명령줄이므로 실행 가능한 형태여야 한다.
    # 경로에 공백이 있으면 셸이 두 인자로 쪼개, 안내대로 했는데 실패한다.
    typer.echo(
        f'이제 질문할 수 있습니다:  whyd ask {shlex.quote(str(repo))} "질문 내용"'
    )


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
    chunks, chroma_dir, _, _ = open_or_exit(repo)

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

    # 화면에 뿌린 뒤 저장한다. 저장이 실패해도 사용자는 답을 이미 받았고,
    # 요금도 이미 나갔다. 실패는 알리되 오류로 끝내지 않는다.
    # 근거를 못 찾은 답은 남기지 않는다. 다시 볼 내용이 없다.
    if sources:
        try:
            conn = connect(repo)
            try:
                save_ask(conn, get_repo_id(conn, repo), question, text, source_refs(sources))
            finally:
                conn.close()
        except sqlite3.Error as exc:
            typer.secho(f"기록에 남기지 못했습니다: {exc}", fg=typer.colors.YELLOW)


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
        exclude (list[str]): 기본 제외 목록에 더할 디렉토리 이름.
            장부에 함께 기록되므로 report와 interview에서는 다시 칠 필요가 없고,
            재인덱싱 때도 생략하면 장부에 남은 값을 그대로 쓴다.
            제외 목록을 바꾸려면 새 값을 명시해야 한다.
    """
    repo = repo.expanduser().resolve()
    chunks, _, meta, stale = open_or_exit(repo)
    excludes = resolve_excludes(exclude, meta)

    typer.echo("개요를 조립하는 중...")
    overview = build_overview(str(repo), chunks, excludes)

    typer.echo("특이 지점을 찾는 중...")
    quirk_groups = group_quirks(
        find_quirks(str(repo), collect_files(str(repo), excludes))
    )

    typer.echo("요약을 생성하는 중...")
    text = build_report(
        overview, chunks, AnthropicClient(model=SUMMARY_MODEL), quirk_groups,
        stale=stale,
    )

    target = output or report_path(repo)
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
    chunks, _, meta, _ = open_or_exit(repo)
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
                typer.echo(
                    f"먼저 질문을 만드세요:  whyd interview {shlex.quote(str(repo))}"
                )
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

    chunks, chroma_dir, _, _ = open_or_exit(repo)

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

    # 화면에 뿌린 뒤 저장한다. 저장이 실패해도 사용자는 피드백을 이미 받았고,
    # 요금도 이미 나갔다. 실패는 알리되 오류로 끝내지 않는다. whyd ask와 같다.
    try:
        conn = connect(repo)
        try:
            save_answer(conn, get_repo_id(conn, repo), fb, question_id)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        typer.secho(f"기록에 남기지 못했습니다: {exc}", fg=typer.colors.YELLOW)


@app.command()
def history(
    repo: Path = typer.Argument(..., help="기록을 볼 레포 경로"),
    limit: int = typer.Option(10, "--limit", "-l", help="표시할 답변 수"),
) -> None:
    """지금까지의 연습 기록과 누적 경향을 본다.

    개별 점수보다 누적 비율을 위에 둔다.
    한 번 단정한 것은 실수지만 계속 단정하는 것은 습관이고,
    이 도구가 알려주려는 것은 후자다.

    질문 기록은 건수만 한 줄로 적는다. 답이 마크다운이라 터미널에 여러 건을
    늘어놓으면 채점 기록이 묻힌다. 답과 근거는 웹 기록 탭에서 본다.

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
    ask_count = count_asks(conn, repo_id)

    conn.close()

    if not answers:
        typer.secho("아직 채점 기록이 없습니다.", fg=typer.colors.YELLOW)
        typer.echo(f"연습을 시작하세요:  whyd interview {shlex.quote(str(repo))}")
        print_ask_count(ask_count, repo)
        raise typer.Exit(0)

    typer.secho(f"\n채점 기록 ({len(answers)}건)", fg=typer.colors.CYAN, bold=True)
    for a in answers:
        date = a["created_at"][:10]
        total = a["specificity"] + a["calibration"] + a["groundedness"]
        typer.echo(f"  {date}  {total}/6  {a['question_text'][:45]}")

    # 세 숫자와 경향 한 줄은 웹 기록 화면과 같은 계산을 쓴다(services.history).
    t = tally(summary)

    typer.secho("\n주장 판정 누적", fg=typer.colors.CYAN, bold=True)
    typer.secho(f"  코드로 확인됨       {t.confirmed}회", fg=typer.colors.GREEN)
    typer.secho(f"  근거 없이 단정      {t.asserted}회", fg=typer.colors.RED)
    typer.secho(f"  근거 없음을 밝힘    {t.hedged}회", fg=typer.colors.GREEN)

    if t.note:
        color = typer.colors.RED if t.tone == "warn" else typer.colors.GREEN
        typer.secho("\n" + t.note, fg=color)

    if risky:
        typer.secho("\n근거 없이 단정한 주장", fg=typer.colors.CYAN, bold=True)
        for r in risky:
            typer.echo(f"  - {r['claim'][:70]}")

    print_ask_count(ask_count, repo)


def print_ask_count(count: int, repo: Path) -> None:
    """질문 기록이 있으면 건수와 볼 곳을 한 줄로 알린다.

    Args:
        count (int): 저장된 질문 수.
        repo (Path): 대상 레포 루트. 웹을 여는 명령에 넣는다.
    """
    if not count:
        return
    typer.secho(f"\n질문 기록 {count}건", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  답과 근거는 웹 기록 탭에서 봅니다:  whyd serve {shlex.quote(str(repo))}")


@app.command(help="웹 화면을 띄운다. 레포 경로를 주면 그 레포를 연 채로 시작한다.")
def serve(
    repo: Path = typer.Argument(None, help="열면서 바로 분석할 레포 경로 (선택)"),
    port: int = typer.Option(8000, "--port", "-p", help="사용할 포트"),
    host: str = typer.Option("127.0.0.1", "--host", help="바인딩할 주소"),
    reload: bool = typer.Option(
        False, "--reload", help="코드 변경 시 자동 재시작 (개발용)"
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="브라우저를 자동으로 열지 않는다"
    ),
) -> None:
    """웹 화면을 띄운다.

    uvicorn 명령을 직접 치지 않아도 되게 하는 것이 이 명령의 전부다.
    처음 쓰는 사람이 모듈 경로를 알아야 화면에 닿는 상태를 없앤다.

    uvicorn을 함수 안에서 import하는 이유는 시작 시간이다. whyd는 대부분
    ask와 practice로 쓰이는데, 그때마다 웹 서버 의존성을 읽어들일 이유가 없다.

    자동 재시작을 기본으로 두지 않는 이유는 쓰는 사람이 코드를 고치지 않기
    때문이다. 감시 프로세스가 하나 더 뜨고 재시작이 얽히는 값을 치를 이유가
    없다. 개발 중에는 플래그로 켠다.

    재시작 모드에서 브라우저를 열지 않는 것은 탭이 쌓이기 때문이다.
    uvicorn은 코드가 바뀔 때마다 워커를 새로 띄우는데, 그 자리에서 열면
    파일을 저장할 때마다 창이 하나씩 생긴다.

    브라우저를 지연 후 여는 이유는 순서다. uvicorn.run()은 돌아오지 않으므로
    그 뒤에 열 수 없고, 먼저 열면 서버가 아직 없어 연결 거부를 보게 된다.

    Args:
        repo (Path): 화면을 열면서 바로 분석할 레포 경로. 생략하면 빈 화면.
        port (int): 사용할 포트.
        host (str): 바인딩할 주소. 기본은 로컬 전용이다.
        reload (bool): 코드 변경 시 자동 재시작 여부.
        no_browser (bool): 브라우저 자동 열기를 끄는지 여부.
    """
    import uvicorn

    url = f"http://{host}:{port}"

    # 경로를 받았으면 화면이 그 레포를 연 상태로 시작한다.
    # 쿼리스트링 복원은 화면이 이미 갖고 있으므로 주소만 만들면 된다.
    if repo is not None:
        url += "?path=" + quote(str(repo.expanduser().resolve()))

    typer.echo(f"VibeCheck 웹 화면: {url}")
    typer.echo("종료하려면 Ctrl+C\n")

    timer = None
    if not no_browser and not reload:
        timer = threading.Timer(1.0, webbrowser.open, args=[url])
        timer.start()

    # 재시작 모드에서는 앱 객체를 넘길 수 없다.
    # uvicorn이 워커를 새로 띄울 때 모듈을 다시 읽어야 하므로 경로 문자열이어야 한다.
    # 포트를 못 잡으면 uvicorn은 곧바로 종료하는데, 그때 타이머가 살아 있으면
    # 그 포트를 쥐고 있는 다른 서버를 열어버린다. 서버가 끝나면 타이머도 거둔다.
    try:
        uvicorn.run("vibecheck.web.app:app", host=host, port=port, reload=reload)
    finally:
        if timer is not None:
            timer.cancel()


def main() -> None:
    """콘솔 스크립트 진입점.

    LLM 호출이 실패하면 트레이스백 대신 사용자가 할 일을 한 줄로 알리고 끝낸다.
    사용 한도, 키 오류, 네트워크 문제는 할 일이 서로 다른데, 트레이스백 맨 아래
    줄만으로는 그 구분이 잘 보이지 않는다. 명령마다 잡지 않고 여기서 한 번에
    잡아, index, ask, practice, report가 모두 같은 안내를 쓴다.

    안내로 바꿀 수 없는 예외는 그대로 올린다.

    Raises:
        SystemExit: LLM 호출이 실패하면 1로 끝낸다.
    """
    try:
        app()
    except LLM_ERRORS as exc:
        message = describe_llm_error(exc)
        if message is None:
            raise
        typer.secho(message, fg=typer.colors.RED, err=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()