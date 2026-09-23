"""리포트 재료로 면접 예상질문을 만든다.

답은 주지 않는다. 답을 함께 주면 외우게 되는데,
이 도구의 목표는 사용자가 자기 코드를 설명할 수 있게 만드는 것이다.
답이 궁금하면 whyd ask로 물어보게 한다.

대신 답변 전략을 붙인다.
어디까지가 코드로 답할 수 있는 부분이고 어디부터가 추측인지를 구분해준다.
실험에서 확인했듯 "왜"의 상당 부분은 코드에서 복원할 수 없으므로,
사용자에게도 복원 불가능한 것을 아는 척하지 않는 법을 알려야 한다.
면접에서 "확장성 때문입니다"라고 단정했다가 근거를 요구받으면 무너지지만,
사실을 먼저 말하고 이유는 추측임을 밝히면 코드를 제대로 읽었다는 증거가 된다.

질문 생성은 대부분 조립이다.
특이 지점은 이미 질문 형태이고, 의존성과 진입점은 템플릿으로 만들 수 있다.
조립으로 되는 것을 LLM에 맡기면 실행마다 달라지고 지어낼 여지만 생긴다.
"""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from vibecheck.core.languages import spec_for
from vibecheck.core.overview import RepoOverview
from vibecheck.core.quirks import QuirkGroup
from vibecheck.services.relations import type_neighbors

STAGE_OVERVIEW = "개요"
STAGE_STRUCTURE = "구조"
STAGE_DECISION = "설계 결정"

STAGE_ORDER = [STAGE_OVERVIEW, STAGE_STRUCTURE, STAGE_DECISION]
"""면접이 흘러가는 순서.

개요를 답하지 못하면 구조를 물을 이유가 없고, 구조를 모르면 결정을 논할 수 없다.
실제 면접의 진행 순서와 같으므로 연습도 이 순서로 한다.
"""


@dataclass
class Question:
    """면접 예상질문 하나.

    Attributes:
        stage (str): 면접 단계. STAGE_ORDER 중 하나.
        text (str): 질문 문장.
        answerable (bool): 코드만으로 답할 수 있는지 여부.
            False면 추측이 필요한 영역이며, 답변 전략이 달라진다.
        can_say (list[str]): 코드를 근거로 말할 수 있는 것.
        risky (list[str]): 단정하면 위험한 것. 근거가 코드에 없는 내용이다.
    """

    stage: str
    text: str
    answerable: bool
    can_say: list[str]
    risky: list[str]


def overview_questions(overview: RepoOverview) -> list[Question]:
    """개요 단계 질문을 만든다.

    Args:
        overview (RepoOverview): 조립된 개요.

    Returns:
        list[Question]: 개요 질문 목록.
    """
    questions = [
        Question(
            stage=STAGE_OVERVIEW,
            text="이 프로젝트가 무엇을 하는 도구인지 설명해보세요.",
            answerable=True,
            can_say=[
                f"파일 {overview.file_count}개, 함수·클래스 {overview.symbol_count}개 규모",
                "핵심 기능과 그것이 어느 파일에 있는지",
            ],
            risky=[],
        )
    ]

    confirmed = [e for e in overview.entry_points if e.confirmed]
    guessed = [e for e in overview.entry_points if not e.confirmed]

    if confirmed:
        questions.append(
            Question(
                stage=STAGE_OVERVIEW,
                text="이 프로젝트는 어디서부터 실행되나요?",
                answerable=True,
                can_say=[f"`{e.target}` — {e.evidence}" for e in confirmed],
                risky=[],
            )
        )
    elif guessed:
        # 추정만 있으면 확신도가 다르므로 질문의 성격도 달라진다.
        questions.append(
            Question(
                stage=STAGE_OVERVIEW,
                text="이 프로젝트는 어디서부터 실행되나요?",
                answerable=False,
                can_say=[f"`{e.target}` — {e.evidence}" for e in guessed],
                risky=[
                    "등록된 진입점이 없어 파일 이름과 코드 관례로 추정한 것입니다. "
                    "단정하지 말고 근거를 함께 밝히세요."
                ],
            )
        )

    return questions


TEST_DIRS = {"test", "tests"}
"""테스트 코드를 담는 폴더 이름."""


def is_test_path(path: str) -> bool:
    """테스트 코드 파일인지 경로로 가른다.

    면접관은 테스트 클래스가 무엇을 쓰는지 묻지 않는다. 그런데 테스트는 여러 클래스를
    한꺼번에 써서, 많이 엮인 순으로 고르면 맨 앞에 온다. 테스트까지 인덱싱한 Java
    레포에서 첫 세트의 파일 역할 질문과 둘째 세트의 첫 질문이 모두 테스트 클래스였다.

    폴더 이름(test, tests)과 파일 이름 관례(test_로 시작, Test·Tests·_test로 끝남)로 가른다.

    Args:
        path (str): 레포 기준 파일 경로.

    Returns:
        bool: 테스트 파일이면 True.
    """
    parts = PurePosixPath(path)
    if any(part in TEST_DIRS for part in parts.parts[:-1]):
        return True
    return parts.stem.startswith("test_") or parts.stem.endswith(("Test", "Tests", "_test"))


def main_file(overview: RepoOverview) -> str | None:
    """첫 세트가 역할을 묻는 파일을 고른다.

    파일 개요 글이 가장 긴 파일이다. 파일 개요에는 그 파일의 심볼마다 요약이 한 줄씩
    붙어, 대개 심볼이 가장 많은 파일이 된다. 테스트 파일은 뺀다.

    둘째 세트의 파일 역할 질문도 이 함수로 같은 파일을 가려낸다. 고르는 기준이
    둘로 갈라져 있을 때 첫 세트의 질문이 둘째 세트에 다시 나왔다.

    Args:
        overview (RepoOverview): 조립된 개요.

    Returns:
        str | None: 파일 경로. 테스트가 아닌 파일이 없으면 None.
    """
    files = [item for item in overview.file_map if not is_test_path(item[0])]
    if not files:
        return None
    return max(files, key=lambda item: len(item[1]))[0]


def structure_questions(overview: RepoOverview) -> list[Question]:
    """구조 단계 질문을 만든다.

    Args:
        overview (RepoOverview): 조립된 개요.

    Returns:
        list[Question]: 구조 질문 목록.
    """
    questions = []

    if overview.external_deps:
        deps = ", ".join(f"`{d}`" for d in overview.external_deps)
        questions.append(
            Question(
                stage=STAGE_STRUCTURE,
                text=f"외부 라이브러리로 {deps}를 씁니다. 각각 어디에 쓰이나요?",
                answerable=True,
                can_say=["각 라이브러리를 import하는 파일과 실제로 호출하는 함수"],
                risky=[
                    "왜 그 라이브러리를 골랐는지는 코드에 없습니다. "
                    "대안을 검토한 흔적이 없으므로 선택 이유를 단정하지 마세요."
                ],
            )
        )

    if overview.internal_import_count:
        questions.append(
            Question(
                stage=STAGE_STRUCTURE,
                text="파일들이 서로 어떻게 얽혀 있나요? 의존 방향을 설명해보세요.",
                answerable=True,
                can_say=[
                    f"파일 간 참조 {overview.internal_import_count}건",
                    "어느 파일이 어느 파일을 import하는지",
                ],
                risky=[],
            )
        )

    # 파일이 많으면 특정 파일을 짚어 묻는 질문이 나온다.
    # 개요 글이 가장 긴 파일, 곧 대개 심볼이 가장 많은 파일이 핵심이거나 정리가 덜 된 곳이다.
    target = main_file(overview)
    if target:
        questions.append(
            Question(
                stage=STAGE_STRUCTURE,
                text=f"`{target}`는 이 프로젝트에서 어떤 역할인가요?",
                answerable=True,
                can_say=["그 파일이 정의하는 심볼과 각각의 역할"],
                risky=[],
            )
        )

    return questions


def decision_questions(quirk_groups: list[QuirkGroup]) -> list[Question]:
    """설계 결정 단계 질문을 만든다.

    특이 지점은 이미 질문 형태이므로 그대로 쓴다.
    다만 이 단계가 가장 위험하다. 발견된 사실은 코드에 실재하지만
    그것이 왜 그런지는 코드에 남지 않기 때문이다.
    버려진 대안은 흔적을 남기지 않으므로 이유는 원리적으로 복원 불가능하다.

    Args:
        quirk_groups (list[QuirkGroup]): 특이 지점 그룹 목록.

    Returns:
        list[Question]: 설계 결정 질문 목록.
    """
    questions = []

    for group in quirk_groups:
        places = ", ".join(f"`{q.symbol}` ({q.file}:{q.line})" for q in group.quirks)

        questions.append(
            Question(
                stage=STAGE_DECISION,
                text=group.question,
                answerable=False,
                can_say=[
                    f"해당 위치: {places}",
                    "그 인자가 실제로 어떻게 처리되는지 (버려지는지, 무시되는지)",
                    "그 값 없이도 동작이 성립하는 이유",
                ],
                risky=[
                    "\"확장성을 위해\", \"나중에 쓰려고\" 같은 이유는 코드에 근거가 없습니다.",
                    "사실을 먼저 말하고 이유는 추측임을 밝히세요. "
                    "근거를 요구받았을 때 무너지지 않는 유일한 방법입니다.",
                ],
            )
        )

    return questions


def build_questions(
    overview: RepoOverview,
    quirk_groups: list[QuirkGroup] | None = None,
) -> list[Question]:
    """면접 예상질문 전체를 만든다.

    Args:
        overview (RepoOverview): 조립된 개요.
        quirk_groups (list[QuirkGroup] | None): 특이 지점 그룹 목록.

    Returns:
        list[Question]: 면접 진행 순서대로 정렬된 질문 목록.
    """
    return (
        overview_questions(overview)
        + structure_questions(overview)
        + decision_questions(quirk_groups or [])
    )


def format_questions(questions: list[Question], repo_root: str) -> str:
    """질문 목록을 마크다운으로 조립한다.

    Args:
        questions (list[Question]): 질문 목록.
        repo_root (str): 레포 루트 경로. 안내 문구에 넣는다.

    Returns:
        str: 마크다운 전문.
    """
    lines = [
        "# 면접 예상질문",
        "",
        "> 답은 적혀 있지 않습니다. 먼저 스스로 답해본 뒤,",
        "> 막히는 지점만 `whyd ask`로 확인하세요.",
        "",
        "---",
        "",
    ]

    numbering = 0

    for stage in STAGE_ORDER:
        staged = [q for q in questions if q.stage == stage]
        if not staged:
            continue

        lines += [f"## {stage}", ""]

        for question in staged:
            numbering += 1
            lines += [f"### Q{numbering}. {question.text}", ""]

            if question.answerable:
                lines.append("**코드로 답할 수 있는 질문입니다.**")
            else:
                lines.append("**주의: 코드에 근거가 없는 부분이 있습니다.**")
            lines.append("")

            if question.can_say:
                lines.append("말할 수 있는 것:")
                lines += [f"- {item}" for item in question.can_say]
                lines.append("")

            if question.risky:
                lines.append("단정하면 위험한 것:")
                lines += [f"- {item}" for item in question.risky]
                lines.append("")

            # 질문 문장에 백틱이 들어 있어 그대로 두면 셸에서 명령 치환으로 해석된다.
            # 복사해 붙여 쓰라고 내놓는 명령줄이므로 실행 가능한 형태여야 한다.
            plain = question.text.replace("`", "")
            lines += [
                f'> 막히면: `whyd ask {repo_root} "{plain}"`',
                "",
            ]

        lines += ["---", ""]

    return "\n".join(lines)


# ---------- 다음 세트 ----------

SET_SIZE = 5
"""세트 하나에 담는 질문 수. 첫 세트(build_questions)와 비슷한 분량이다."""

FLOW_MIN_CALLS = 2
"""흐름 질문으로 물을 함수가 적어도 불러야 하는 다른 함수 수.

하나만 부르는 함수는 "무엇을 거쳐 흘러가나요"라고 물을 흐름이 없다.
"""

LIST_LIMIT = 6
"""말할 수 있는 것에 늘어놓는 이름의 최대 개수. 넘으면 몇 개 더 있다고만 적는다."""


def names_line(label: str, names: list[str]) -> str:
    """이름 목록을 "말할 수 있는 것" 한 줄로 적는다.

    Args:
        label (str): 줄 앞에 붙일 말.
        names (list[str]): 이름 목록. 이미 정렬되어 있다.

    Returns:
        str: 한 줄. 너무 길면 앞의 몇 개만 적고 나머지 개수를 붙인다.
    """
    shown = ", ".join(f"`{n}`" for n in names[:LIST_LIMIT])
    rest = len(names) - LIST_LIMIT
    return f"{label}: {shown}" + (f" 외 {rest}개" if rest > 0 else "")


def flow_questions(chunks: list) -> list[Question]:
    """호출 관계로 "이 함수를 부르면 무엇을 거쳐 흘러가나요"를 묻는다.

    실제 면접은 파일의 역할보다 흐름을 묻는다. 인덱싱 때 풀어 둔 호출 관계(calls)가
    있어 무엇을 부르는지는 코드로 확인되는 사실이고, 채점도 그 목록과 대조할 수 있다.
    호출 관계를 수집하는 언어(지금은 파이썬)에서만 나온다.

    다른 함수를 많이 부르고 많이 불리는 함수부터 묻는다. 흐름의 중심이다.
    __init__ 같은 특수 메서드는 뺀다. 흐름을 묻기에 어색하다.

    Args:
        chunks (list): 인덱싱된 전체 청크.

    Returns:
        list[Question]: 흐름 질문. 중요한 것부터.
    """
    code = [c for c in chunks if c.kind in ("function", "method") and not is_test_path(c.file)]
    by_id = {c.id: c for c in chunks}
    callers: dict[str, list[str]] = defaultdict(list)
    for c in code:
        for target in c.calls:
            callers[target].append(c.symbol)

    picked = [
        c for c in code
        if len(set(c.calls)) >= FLOW_MIN_CALLS
        and not c.symbol.rsplit(".", 1)[-1].startswith("__")
    ]
    picked.sort(key=lambda c: (-(len(set(c.calls)) + len(callers[c.id])), c.id))

    questions = []
    for c in picked:
        callees = sorted({by_id[t].symbol for t in c.calls if t in by_id})
        can_say = [names_line("부르는 함수", callees)]
        if callers[c.id]:
            can_say.append(names_line("이 함수를 부르는 곳", sorted(set(callers[c.id]))))
        questions.append(
            Question(
                stage=STAGE_STRUCTURE,
                text=f"`{c.symbol}` ({c.file}) — 이 함수를 부르면 무엇을 거쳐 결과가 나오나요?",
                answerable=True,
                can_say=can_say,
                risky=["코드에서 확인한 호출만 말하세요. 호출 순서나 조건을 지어내면 근거를 대지 못합니다."],
            )
        )
    return questions


def type_questions(chunks: list, repo: Path) -> list[Question]:
    """타입 참조로 "이 클래스는 무엇을 쓰고 어디서 쓰이나요"를 묻는다.

    호출 관계를 수집하지 않는 언어(지금은 Java)의 흐름 질문 대신이다. 관계도와 같은
    재료(services.relations.type_neighbors)를 써서, 화면에 보이는 연결과 질문이
    말하는 연결이 같다. 이름이 겹치는 클래스는 관계도처럼 짐작하지 않고 뺀다.

    Args:
        chunks (list): 인덱싱된 전체 청크.
        repo (Path): 레포 루트. 타입 참조를 세려면 파일을 읽어야 한다.

    Returns:
        list[Question]: 타입 관계 질문. 많이 엮인 것부터.
    """
    rows = []
    for c in chunks:
        if c.kind != "file" or is_test_path(c.file):
            continue
        spec = spec_for(c.file)
        if not (spec and spec.collect_type_refs and spec.type_named_files):
            continue
        used_by, uses = type_neighbors(repo, chunks, c.file, spec)
        # 테스트가 쓰는 것은 흐름을 설명하는 데 보탬이 되지 않아 목록에서도 뺀다.
        used_by = [f for f in used_by if not is_test_path(f)]
        uses = [f for f in uses if not is_test_path(f)]
        if not uses and not used_by:
            continue
        rows.append((c.file, used_by, uses))

    rows.sort(key=lambda r: (-(len(r[1]) + len(r[2])), r[0]))

    questions = []
    for file, used_by, uses in rows:
        name = Path(file).stem
        can_say = []
        if uses:
            can_say.append(names_line("쓰는 클래스", sorted(Path(f).stem for f in uses)))
        if used_by:
            can_say.append(names_line("이 클래스를 쓰는 곳", sorted(Path(f).stem for f in used_by)))
        questions.append(
            Question(
                stage=STAGE_STRUCTURE,
                text=f"`{name}` ({file}) — 이 클래스는 무엇을 쓰고, 어디서 쓰이나요?",
                answerable=True,
                can_say=can_say,
                risky=["메서드 단위 호출은 분석하지 않았습니다. 어느 메서드가 무엇을 부르는지는 코드를 열어 확인하고 말하세요."],
            )
        )
    return questions


def dependency_questions(overview: RepoOverview, chunks: list) -> list[Question]:
    """외부 라이브러리를 하나씩 "어디에, 무엇에 쓰이나요"로 묻는다.

    첫 세트는 라이브러리 전부를 한 질문으로 묻는다. 여덟 개를 한 답에 담으면 말하기도
    채점하기도 어렵다. 하나씩 나누고, 그 라이브러리를 import하는 파일을 말할 수 있는
    것으로 붙인다. 왜 골랐는지는 코드에 없으므로 단정하면 위험한 것에 둔다.

    Args:
        overview (RepoOverview): 조립된 개요.
        chunks (list): 인덱싱된 전체 청크.

    Returns:
        list[Question]: 라이브러리별 질문. 쓰는 파일이 많은 것부터.
    """
    users: dict[str, set[str]] = defaultdict(set)
    for c in chunks:
        # 테스트에서만 쓰는 라이브러리(junit 등)는 면접에서 물을 대상이 아니다.
        if c.kind != "file" or is_test_path(c.file):
            continue
        spec = spec_for(c.file)
        if spec is None:
            continue
        for imp in c.imports:
            name, is_stdlib = spec.dependency_of(imp)
            if not is_stdlib:
                users[name].add(c.file)

    deps = [d for d in overview.external_deps if users.get(d)]
    deps.sort(key=lambda d: (-len(users[d]), d))

    return [
        Question(
            stage=STAGE_STRUCTURE,
            text=f"`{dep}` — 이 라이브러리는 이 프로젝트에서 어디에, 무엇에 쓰이나요?",
            answerable=True,
            can_say=[names_line("import하는 파일", sorted(users[dep]))],
            risky=[
                "왜 이 라이브러리를 골랐는지는 코드에 없습니다. "
                "대안을 검토한 흔적이 없으므로 선택 이유를 단정하지 마세요."
            ],
        )
        for dep in deps
    ]


def file_questions(overview: RepoOverview, chunks: list) -> list[Question]:
    """재료가 모자랄 때 채우는 파일 역할 질문.

    파일의 역할은 개요 화면의 한 줄 요약을 읽으면 답이 나와 흐름 질문보다 얕다.
    그래서 다른 재료 뒤에 둔다. 첫 세트가 이미 물은 파일(main_file)과 테스트 파일은 뺀다.

    Args:
        overview (RepoOverview): 조립된 개요.
        chunks (list): 인덱싱된 전체 청크.

    Returns:
        list[Question]: 파일 역할 질문. 심볼이 많은 파일부터.
    """
    symbols: dict[str, list[str]] = defaultdict(list)
    for c in chunks:
        if c.kind in ("function", "method", "class"):
            symbols[c.file].append(c.symbol)

    first = main_file(overview)
    files = [
        f for f, _ in overview.file_map
        if symbols.get(f) and f != first and not is_test_path(f)
    ]
    files.sort(key=lambda f: (-len(symbols[f]), f))

    return [
        Question(
            stage=STAGE_STRUCTURE,
            text=f"`{f}` — 이 파일은 이 프로젝트에서 어떤 역할인가요?",
            answerable=True,
            can_say=[names_line("이 파일이 정의하는 것", sorted(symbols[f]))],
            risky=[],
        )
        for f in files
    ]


def question_sets(
    overview: RepoOverview,
    chunks: list,
    repo: Path,
    quirk_groups: list[QuirkGroup] | None = None,
) -> list[list[Question]]:
    """면접 질문을 세트로 나눈다. 첫 세트는 build_questions 그대로다.

    첫 세트를 바꾸지 않는 이유는 whyd practice --question-no가 그 번호로 질문을
    가리키기 때문이다.

    둘째 세트부터는 흐름(파이썬은 호출, Java는 타입 참조), 라이브러리, 흐름, 파일
    역할 순으로 번갈아 담는다. 흐름을 앞에 자주 두는 것은 실제 면접이 그것을 가장
    많이 묻기 때문이고, 파일 역할은 얕아서 채우는 용도로만 쓴다. 한 종류가 떨어지면
    남은 종류로 채운다. 모두 LLM 없이 인덱스에서 조립하므로 요금이 없다.

    Args:
        overview (RepoOverview): 조립된 개요.
        chunks (list): 인덱싱된 전체 청크.
        repo (Path): 레포 루트.
        quirk_groups (list[QuirkGroup] | None): 특이 지점 그룹. 첫 세트에 쓴다.

    Returns:
        list[list[Question]]: 세트 목록. 첫 세트는 늘 있다.
    """
    flows = flow_questions(chunks) + type_questions(chunks, repo)
    queues = {
        "flow": flows,
        "dep": dependency_questions(overview, chunks),
        "file": file_questions(overview, chunks),
    }
    pattern = ["flow", "dep", "flow", "file"]

    ordered: list[Question] = []
    while any(queues.values()):
        for key in pattern:
            if queues[key]:
                ordered.append(queues[key].pop(0))

    rest = [ordered[i:i + SET_SIZE] for i in range(0, len(ordered), SET_SIZE)]
    return [build_questions(overview, quirk_groups)] + rest
