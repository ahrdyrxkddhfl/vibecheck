"""후보 레포가 실험 A에 적합한지 판정한다.

LLM API를 호출하지 않고 정적 분석만으로 레포를 평가하는 것이 목적이다.
인덱싱은 청크 수에 비례해 비용이 들기 때문에,
돈을 쓰기 전에 부적합한 후보를 걸러내는 관문이 필요하다.

파싱 성공률을 먼저 본다. 파싱에 실패한 파일은 청크가 생성되지 않아
검색 대상에서 통째로 빠지므로, 이 비율이 낮으면 나머지 지표는 무의미하다.

설명 밀도는 독스트링 커버리지와 주석 밀도로 나눠 측정한다.
하나로 합치면 '독스트링은 있는데 내용이 비어 있는' LLM 생성 코드와
'설명이 아예 없는' 수작업 코드가 구분되지 않는데,
두 유형은 검색 품질에 다르게 작용하므로 분리해야 한다.
"""

import io
import re
import tokenize
import ast
import sys

from vibecheck.core.collector import collect_files, to_relative

TOOL_DIRECTIVE = re.compile(r"^#\s*(noqa|type:|pylint:|mypy:|ruff:|fmt:|isort:)")
"""사람에게 하는 설명이 아닌 도구 지시문 패턴.

린터, 타입체커에 주는 명령이므로 코드 이해를 돕는 주석으로 세면 안 된다.
"""

def count_docstrings(tree: ast.AST) -> tuple[int, int]:
    """독스트링이 붙을 수 있는 대상과 실제로 붙은 개수를 센다.

    모듈 독스트링은 세지 않는다. 함수, 클래스와 달리 대상이 파일당 하나뿐이라
    비율에 미치는 영향이 크고, 인덱싱되는 청크 단위는 함수, 클래스이므로
    그쪽 커버리지가 검색 품질에 직결된다.

    Args:
        tree (ast.AST): 파싱된 구문 트리.
    
    Returns:
        tuple[int, int]: (대상 개수, 독스트링이 있는 개수).
    """
    targets = 0
    documented = 0

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        targets += 1
        # get_docstring은 본문 첫 문장이 문자열 표현식일 때만 값을 준다.
        # 위치로 판별하므로 변수에 대입된 문자열과 혼동하지 않는다.
        if ast.get_docstring(node):
            documented += 1

    return targets, documented

def count_comments(source: str) -> tuple[int, int]:
    """주석 줄 수와 실질 코드 줄 수를 센다.

    tokenize를 쓰는 이유는 ast가 주석을 버리기 때문이다.
    주석은 실행에 영향이 없어 구문 트리에 담기지 않으므로
    토큰 단위로 훑어야 문자열 안의 '#'와 구분할 수 있다.

    빈 줄을 분모에서 빼는 이유는 여백이 많은 파일의 밀도가
    실제보다 낮게 계산되기 때문이다.

    이 값이 낮다고 설명이 부실한 코드는 아니다.
    독스트링을 97% 붙인 이 프로젝트도 주석 밀도는 100줄당 2.7줄에 그친다.
    "왜"를 독스트링에 쓰면 주석으로 남길 내용이 줄어들기 때문이다.
    따라서 단독 판정 기준으로 쓰지 말고, 독스트링 커버리지와 함께
    설명 유형을 구분하는 보조 지표로만 본다.

    Args:
        source (str): 파이썬 소스 코드 전문.

    Returns:
        tuple[int, int]: (주석 줄 수, 코드 줄 수).
    """
    comments_rows: set[int] = set()

    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue

        text = token.string.strip()
        if text.startswith("#!") or "coding:" in text or "coding=" in text:
            continue
        if TOOL_DIRECTIVE.match(text):
            continue

        # 한 줄에 주석이 둘일 수 없으므로 줄 번호를 집합에 담아 중복을 막는다.
        comments_rows.add(token.start[0])

    code_lines = 0
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        # 줄 전체가 주석이면 코드가 아니다. 코드 뒤에 붙은 주석은 코드로 센다.
        if stripped.startswith("#") and i in comments_rows:
            continue
        code_lines += 1

    return len(comments_rows), code_lines

def screen(root: str) -> None:
    """레포를 스크리닝하고 결과를 출력한다.

    실제 인덱싱과 동일한 수집 규칙(collect_files)을 사용한다.
    스크리닝이 세는 파일과 인덱싱될 파일이 다르면
    예상 비용과 실제 비용이 어긋나 판정 자체가 쓸모없어지기 때문이다.

    Args:
        root (str): 검사할 레포 루트 경로.
    """
    files = collect_files(root)

    if not files:
        print(f"수집된 .py 파일이 없습니다: {root}")
        return

    total_lines = 0
    total_targets = 0
    total_documented = 0
    total_comments = 0
    total_code_lines = 0
    failures: list[tuple[str, str]] = []

    for path in files:
        rel = to_relative(path, root)

        # 인코딩이 깨진 파일은 파싱 이전에 읽기부터 실패한다.
        # SyntaxError와 원인이 다르므로 구분해서 기록한다.
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            failures.append((rel, f"인코딩 오류: {e.reason}"))
            continue

        total_lines += source.count("\n") + 1

        # tree-sitter가 아니라 ast를 쓰는 이유:
        # tree-sitter는 문법 오류가 있어도 ERROR 노드를 남기고 계속 파싱하므로 실패를 감지할 수 없다.
        # 여기서 알고 싶은 것은 "이 코드가 현재 파이썬 버전에서 온전히 읽히는가"이므로 엄격한 파서가 필요하다.
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            failures.append((rel, f"{e.msg} (line {e.lineno})"))
            continue

        t, d = count_docstrings(tree)
        total_targets += t
        total_documented += d

        c, cl = count_comments(source)
        total_comments += c
        total_code_lines += cl

    parsed = len(files) - len(failures)
    rate = parsed / len(files) * 100

    print(f"\n{'=' * 50}")
    print(f"대상: {root}")
    print(f"{'=' * 50}")
    print(f"파일 수      : {len(files)}개")
    print(f"총 라인 수   : {total_lines:,}줄")
    print(f"파싱 성공    : {parsed}/{len(files)} ({rate:.1f}%)")

    doc_rate = total_documented / total_targets * 100 if total_targets else 0
    density = total_comments / total_code_lines * 100 if total_code_lines else 0

    print(f"독스트링    : {total_documented}/{total_targets} ({doc_rate:.1f}%)")
    print(f"주석 밀도   : 100줄당 {density:.1f}줄")

    if failures:
        print(f"\n실패 {len(failures)}건:")
        for rel, reason in failures:
            print(f"    - {rel}: {reason}")

    print()
    if rate >= 95:
        print("판정: 통과 - 다음 지표 측정 가능")
    else:
        print("판정: 부적합 - 파싱 실패가 많아 인덱싱 결과를 신뢰할 수 없음")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    screen(target)