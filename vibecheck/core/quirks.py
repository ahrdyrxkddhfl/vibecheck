"""코드에 남아 있는 설계 흔적 중 "왜?"가 나올 만한 지점을 찾는다.

리포트의 다른 절이 tree나 README로도 어느 정도 재현되는 반면,
이 절은 코드를 읽어야만 나온다. 이 도구의 존재 이유에 해당하는 부분이다.

LLM에게 "이상한 데를 찾아봐"라고 묻지 않고 규칙으로 탐지한다.
열린 질문은 없는 것을 지어낼 여지를 만드는데, 면접 대비용 리포트에서
존재하지 않는 특징을 읽고 가면 그 자리에서 그대로 무너진다.
규칙 기반은 놓치는 것이 있어도 찾은 것은 반드시 코드에 실재한다.

발견 자체는 사실이지만 그것이 왜 그런지는 코드에 없다.
따라서 이 모듈은 "무엇이 있는가"까지만 말하고 이유를 단정하지 않는다.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

SELF_NAMES = {"self", "cls"}
"""메서드의 첫 인자 이름.

호출자가 넘기는 값이 아니라 언어가 채우는 자리이므로 미사용이어도 의미가 없다.
"""

IGNORED_PREFIX = "_"
"""무시할 인자 이름 접두사.

_나 _unused처럼 밑줄로 시작하는 이름은 "쓰지 않는다"를 이미 밝힌 것이다.
작성자가 의도를 표시한 경우까지 지적하면 잡음만 늘어난다.
"""

DUNDER_FIXED_PARAMS = {
    "__exit__": {"exc_type", "exc_val", "exc_tb", "exc", "tb", "traceback"},
    "__aexit__": {"exc_type", "exc_val", "exc_tb", "exc", "tb", "traceback"},
    "__set_name__": {"owner", "name"},
    "__init_subclass__": {"cls"},
}
"""시그니처가 언어 규약으로 고정된 던더 메서드와 그 인자 이름.

컨텍스트 매니저를 만들려면 __exit__이 예외 정보 세 개를 받아야 한다.
받고도 쓰지 않는 것은 작성자의 선택이 아니라 규약을 따른 결과이므로,
"왜 이 인자를 받나요"라고 물어도 답은 이 레포가 아니라 파이썬에 있다.

인자 이름이 여러 벌인 이유는 관례가 하나로 굳지 않았기 때문이다.
exc_val로 쓰는 코드와 exc로 쓰는 코드가 모두 흔하다.
"""


@dataclass
class Quirk:
    """면접에서 "왜?"가 나올 만한 코드 지점 하나.

    Attributes:
        kind (str): 유형 식별자.
        file (str): 레포 루트 기준 상대 경로.
        symbol (str): 소속을 포함한 심볼 이름.
        line (int): 시작 행 번호 (1-based).
        finding (str): 코드에서 확인된 사실.
            추정이 아니라 관찰된 내용만 담는다.
        question (str): 이 지점에 대해 나올 법한 질문.
    """

    kind: str
    file: str
    symbol: str
    line: int
    finding: str
    question: str


def collect_used_names(node: ast.AST) -> set[str]:
    """함수 본문에서 값으로 읽히는 이름을 모은다.

    del과 대입은 사용으로 세지 않는다.
    del base_url은 "이 값을 쓰지 않겠다"는 선언이고,
    base_url = something은 인자를 버리고 새 값을 담는 것이므로,
    둘 다 넘겨받은 값이 쓰였다는 근거가 되지 않는다.

    ast.Name의 ctx가 Load일 때만 세면 이 구분이 자연스럽게 이루어진다.
    Load는 값을 읽는 자리, Store는 값을 넣는 자리, Del은 지우는 자리를 뜻한다.

    Args:
        node (ast.AST): 검사할 함수 노드.

    Returns:
        set[str]: 값으로 읽힌 이름 집합.
    """
    used = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            used.add(child.id)
        # f-string이나 문자열 안의 이름은 Name 노드가 아니지만,
        # 포맷 표현식은 파싱되어 Name으로 남으므로 위 조건에 포함된다.

    return used


def function_params(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """함수가 선언한 인자 이름을 모두 모은다.

    위치 인자, 키워드 전용 인자, 가변 인자를 모두 포함한다.
    ctxd의 save_secret_bundle처럼 키워드 전용으로만 받는 경우가 있어
    args만 보면 놓친다.

    Args:
        node: 검사할 함수 노드.

    Returns:
        list[str]: 인자 이름 목록. 선언 순서를 유지한다.
    """
    a = node.args
    names = [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]

    if a.vararg:
        names.append(a.vararg.arg)
    if a.kwarg:
        names.append(a.kwarg.arg)

    return names


def find_unused_params(tree: ast.AST, file_path: str) -> list[Quirk]:
    """받아놓고 본문에서 쓰지 않는 인자를 찾는다.

    인자를 받는다는 것은 호출자에게 그 값을 요구한다는 뜻인데,
    쓰지 않는다면 그 요구가 왜 남아 있는지가 질문거리가 된다.
    인터페이스를 맞추려는 것일 수도, 나중에 쓰려고 자리를 잡아둔 것일 수도,
    기능을 걷어내고 시그니처만 남긴 것일 수도 있다.
    어느 쪽인지는 코드에 없으므로 여기서 단정하지 않는다.

    독스트링만 있는 함수(추상 메서드나 프로토콜 정의)는 건너뛴다.
    본문이 없으니 인자를 쓰지 않는 것이 당연하다.

    시그니처가 언어 규약으로 고정된 던더 메서드도 건너뛴다.
    받고도 쓰지 않는 것이 작성자의 선택이 아니기 때문이다.

    Args:
        tree (ast.AST): 파싱된 구문 트리.
        file_path (str): 레포 루트 기준 상대 경로.

    Returns:
        list[Quirk]: 발견된 지점 목록.
    """
    quirks = []
    parents: dict[ast.AST, str] = {}

    # 메서드 이름에 소속 클래스를 붙이려면 부모를 알아야 하는데
    # ast 노드는 부모를 가리키지 않으므로 미리 훑어 기록한다.
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                parents[child] = node.name

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # 본문이 독스트링 하나뿐이거나 ...뿐이면 선언만 있는 함수다.
        body = [
            stmt
            for stmt in node.body
            if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
        ]
        if not body:
            continue

        used = collect_used_names(node)
        fixed = DUNDER_FIXED_PARAMS.get(node.name, set())
        unused = [
            name
            for name in function_params(node)
            if name not in used
            and name not in SELF_NAMES
            and name not in fixed
            and not name.startswith(IGNORED_PREFIX)
        ]

        if not unused:
            continue

        owner = parents.get(node)
        symbol = f"{owner}.{node.name}" if owner else node.name
        names = ", ".join(f"`{n}`" for n in unused)

        quirks.append(
            Quirk(
                kind="unused_param",
                file=file_path,
                symbol=symbol,
                line=node.lineno,
                finding=f"{names} 인자를 받지만 본문에서 사용하지 않습니다.",
                question=f"{symbol}은 왜 쓰지 않는 인자를 받나요?",
            )
        )

    return quirks


def find_quirks(root: str, files: list[Path]) -> list[Quirk]:
    """수집된 파일 전체에서 특이 지점을 찾는다.

    ast.parse가 실패한 파일은 건너뛴다.
    특이 지점은 리포트의 한 절일 뿐이라, 파일 하나 때문에 전체가 멈추면 안 된다.

    Args:
        root (str): 레포 루트 경로.
        files (list[Path]): 검사할 파일 목록.

    Returns:
        list[Quirk]: 발견된 지점 목록. 파일 경로와 행 번호 순으로 정렬한다.
    """
    from vibecheck.core.collector import to_relative

    quirks: list[Quirk] = []

    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue

        quirks += find_unused_params(tree, to_relative(path, root))

    return sorted(quirks, key=lambda q: (q.file, q.line))

@dataclass
class QuirkGroup:
    """같은 패턴으로 묶인 발견들.

    Attributes:
        kind (str): 유형 식별자.
        key (str): 묶은 기준. 같은 인자 이름 조합 등.
        quirks (list[Quirk]): 묶인 발견 목록.
        question (str): 이 패턴에 대해 나올 법한 질문.
    """

    kind: str
    key: str
    quirks: list[Quirk]
    question: str


def group_quirks(quirks: list[Quirk]) -> list[QuirkGroup]:
    """같은 인자 이름으로 반복되는 발견을 하나로 묶는다.

    한 번 나오면 실수일 수 있지만 여러 번 반복되면 의도된 패턴이다.
    그리고 패턴으로 볼 때 질문의 질이 달라진다.
    _handle_login 하나만 보면 "인자를 안 쓴다"에 그치지만,
    _handle_* 셋이 같은 args를 받고 있으면 "왜 핸들러 모양을 통일했는가"가 된다.

    묶는 기준을 파일이 아니라 인자 이름으로 잡는다.
    같은 규약을 따르는 함수들은 파일이 갈려 있어도 같은 이유로 그렇게 생겼고,
    파일 기준으로 묶으면 그 연결이 끊어진다.

    묶인 개수와 무관하게 질문에 파일과 줄 번호를 넣는다. 같은 이름의 함수가
    한 파일 안에 여러 번 지역 정의되는 경우(테스트의 mock_post 등)가 있어,
    이름만 적으면 서로 다른 그룹의 질문이 같은 문장으로 보인다.

    Args:
        quirks (list[Quirk]): 묶을 발견 목록.

    Returns:
        list[QuirkGroup]: 묶인 그룹 목록. 규모가 큰 것부터 정렬한다.
    """
    buckets: dict[tuple[str, str], list[Quirk]] = {}

    for quirk in quirks:
        # finding 문자열에서 인자 이름 부분만 떼어 묶음 열쇠로 쓴다.
        params = quirk.finding.split(" 인자를")[0]
        buckets.setdefault((quirk.kind, params), []).append(quirk)

    groups = []
    for (kind, params), items in buckets.items():
        if len(items) == 1:
            one = items[0]
            question = (
                f"`{one.symbol}` ({one.file}:{one.line})은 "
                f"왜 쓰지 않는 인자를 받나요?"
            )
        else:
            places = ", ".join(
                f"`{q.symbol}` ({q.file}:{q.line})" for q in items
            )
            question = (
                f"{places} 이 {len(items)}개 함수가 모두 {params} 인자를 받고 "
                f"쓰지 않습니다. 왜 이런 형태로 통일했나요?"
            )

        groups.append(
            QuirkGroup(kind=kind, key=params, quirks=items, question=question)
        )

    return sorted(groups, key=lambda g: -len(g.quirks))