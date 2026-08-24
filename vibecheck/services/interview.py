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

from dataclasses import dataclass

from vibecheck.core.overview import RepoOverview
from vibecheck.core.quirks import QuirkGroup

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
    # 심볼이 가장 많은 파일이 대개 핵심이거나 정리가 덜 된 곳이다.
    if overview.file_map:
        biggest = max(overview.file_map, key=lambda item: len(item[1]))
        questions.append(
            Question(
                stage=STAGE_STRUCTURE,
                text=f"`{biggest[0]}`는 이 프로젝트에서 어떤 역할인가요?",
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