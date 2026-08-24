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

from pathlib import Path
from vibecheck.core.collector import collect_files, to_relative

TOOL_DIRECTIVE = re.compile(r"^#\s*(noqa|type:|pylint:|mypy:|ruff:|fmt:|isort:)")
"""사람에게 하는 설명이 아닌 도구 지시문 패턴.

린터, 타입체커에 주는 명령이므로 코드 이해를 돕는 주석으로 세면 안 된다.
"""

INPUT_PER_MTOK = 1.00
OUTPUT_PER_MTOK = 5.00
"""요약 모델(Claude Haiku)의 100만 토큰당 단가(USD).

단가는 바뀔 수 있으므로 상수로 분리한다.
"""

PROMPT_TOKENS = 300
"""요약 프롬프트의 대략적 토큰 수.

청크마다 프롬프트 전체가 다시 전송되므로, 짧은 함수가 많은 레포에서는
이 고정 비용이 전체 입력의 절반을 넘기도 한다.
"""

CHARS_PER_TOKEN = 4
"""영문 코드 기준 토큰 하나에 해당하는 글자 수.

정확히 세려면 tokenizer가 필요하지만 후보를 거르는 용도에는 과하다.
한글이 섞이면 실제 토큰이 더 많아 과소 추정이 된다.
"""

SUMMARY_TOKENS = 50
"""요약 한 건의 출력 토큰 수. 프롬프트가 60자 이내를 요구해 상한이 좁다."""

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
    독스트링을 97% 붙인 이 프로젝트의 패키지(vibecheck/)도 주석 밀도는 100줄당 2.7줄에 그친다.
    (루트 전체로 재면 scripts, experiments가 섞여 58%로 떨어진다. 
    범위에 따라 값이 크게 달라지므로 다른 레포와 비교할 때는 같은 범위끼리 대조해야 한다.)
    "왜"를 독스트링에 쓰면 주석으로 남길 내용이 줄어들기 때문이다.
    따라서 단독 판정 기준으로 쓰지 말고, 독스트링 커버리지와 함께 설명 유형을 구분하는 보조 지표로만 본다.

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

def find_readme(root: str) -> tuple[str, int]:
    """레포 루트의 README를 찾아 이름과 글자 수를 돌려준다.

    README는 코드 밖에 있는 정답지 후보다. 실험 A는 남의 코드를 다루므로
    답변이 맞는지 판단할 근거가 코드 밖에 있어야 채점이 가능하다.

    길이가 내용을 보장하지는 않는다. 설치법만 긴 README는 설계 의도에 답하지 못한다.
    다만 README가 없으면 정답지가 없는 것은 확실하다.

    Args:
        root (str): 레포 루트 경로.

    Returns:
        tuple[str, int]: (파일명, 글자 수). 없으면 ("", 0).
    """
    for path in sorted(Path(root).glob("README*")):
        if path.is_file():
            try:
                return path.name, len(path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                continue

    return "", 0

def is_test_file(rel: str) -> bool:
    """상대 경로가 테스트 파일인지 판별한다.

    테스트는 제외 대상이 아니라 가점 요소다. 함수 이름 자체가 의도를 서술하므로
    ("test_parser_handles_nested_class") 독스트링이 없는 레포에서도
    정답지 역할을 할 수 있다.

    Args:
        rel (str): 레포 루트 기준 상대 경로.

    Returns:
        bool: 테스트 파일이면 True.
    """
    name = rel.rsplit("/", 1)[-1]
    return(
        "tests/" in rel
        or rel.startswith("test/")
        or name.startswith("test_")
        or name.endswith("_test.py")
    )

def find_package_anchor(path: Path) -> Path:
    """모듈 이름의 기준점이 되는 디렉터리를 찾는다.

    __init__.py가 이어지는 가장 바깥 패키지를 찾아, 그 부모를 기준점으로 삼는다.
    src/ctxd/client.py는 파일 경로상 세 칸 깊이지만 import는 ctxd.client로 하는데,
    src가 패키지가 아니라 소스를 담아두는 폴더일 뿐이기 때문이다.
    경로를 그대로 모듈 이름으로 바꾸면 src.ctxd.client가 되어 어떤 import와도 대조되지 않는다.

    __init__.py의 유무로 판별하는 이유는 그것이 파이썬이 패키지를 인식하는 기준 그 자체이기 때문이다.
    디렉터리 이름 목록(src, lib 등)을 하드코딩하면 관례를 벗어난 레포에서 바로 틀린다.

    Args:
        path (Path): 소스 파일 경로.

    Returns:
        Path: 모듈 이름을 상대 계산할 기준 디렉터리.
    """
    anchor = path.parent

    # 패키지가 아닌 디렉터리를 만나면 거기가 경계다.
    while (anchor / "__init__.py").exists():
        anchor = anchor.parent

    return anchor


def build_module_names(files: list, root: str) -> set[str]:
    """수집된 파일들의 모듈 이름 집합을 만든다.

    import 대상이 레포 내부인지 외부 라이브러리인지 가르려면
    "내부에 무엇이 있는지" 목록이 먼저 필요하다.

    경로를 그대로 점 표기로 바꾸지 않고 패키지 기준점을 찾아 상대 계산한다.
    src 레이아웃에서 실제 import 문과 이름이 어긋나기 때문이다.

    기준점이 서로 다른 파일이 섞여도 문제되지 않는다.
    집합에 담아두면 count_internal_imports가 뒤에서부터 좁혀가며 대조하므로,
    어느 한쪽만 맞아도 내부로 판정된다.

    Args:
        files (list): collect_files가 수집한 경로 목록.
        root (str): 레포 루트 경로. 기준점이 루트를 벗어날 때의 안전망으로 쓴다.

    Returns:
        set[str]: 점으로 구분된 모듈 이름 집합.
    """
    names = set()
    root_path = Path(root).resolve()

    for path in files:
        path = Path(path).resolve()
        anchor = find_package_anchor(path)

        # 기준점이 레포 밖으로 나가면(루트 자체가 패키지인 경우) 루트로 되돌린다.
        try:
            rel = path.relative_to(anchor)
        except ValueError:
            rel = path.relative_to(root_path)

        module = str(rel.with_suffix("")).replace("/", ".")

        # __init__.py는 파일이 아니라 패키지 자체를 가리킨다.
        # ctxd/__init__.py는 ctxd로 import된다.
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        elif module == "__init__":
            continue

        names.add(module)

    return names

def count_internal_imports(tree: ast.AST, module_names: set[str]) -> int:
    """레포 내부 모듈을 가리키는 import 개수를 센다.

    외부 라이브러리 import는 제외한다.
    알고 싶은 것은 '이 레포의 파일들이 서로 얽혀 있는가'이고,
    그래야 관계형 질문('A는 어디서 만들어져?')을 만들 수 있기 때문이다.

    모듈 이름을 뒤에서부터 잘라가며 대조하는 이유는 실행 위치에 따라
    수집된 경로의 기준점이 달라지기 때문이다.
    레포 루트에서 실행하면 vibecheck.models로, 패키지 안에서 실행하면 models로 잡힌다.

    부분 일치를 허용하므로 외부 모듈이 내부와 같은 이름을 가지면 잘못 셀 수 있다.
    후보를 거르는 용도이므로 이 정도 오차는 감수한다.

    Args:
        tree (ast.AST): 파싱된 구문 트리.
        module_names (set[str]): 내부 모듈 이름 집합.

    Returns:
        int: 내부를 가리키는 import 개수.
    """
    def is_internal(dotted: str) -> bool:
        parts = dotted.split(".")
        # vibecheck.models -> models 순으로 좁혀가며 대조한다.
        for i in range(len(parts)):
            if ".".join(parts[i:]) in module_names:
                return True
        return False

    count = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            count += sum(1 for a in node.names if is_internal(a.name))

        elif isinstance(node, ast.ImportFrom):
            # level > 0 은 상대 경로 import(from . import x)로 항상 내부다.
            if node.level > 0:
                count += 1
            elif node.module and is_internal(node.module):
                count += 1

    return count

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
    module_names = build_module_names(files, root)

    total_lines = 0
    total_targets = 0
    total_documented = 0
    total_comments = 0
    total_code_lines = 0
    total_internal_imports = 0
    total_test_files = 0
    total_chars = 0
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
        total_chars += len(source)
        if is_test_file(rel):
            total_test_files += 1

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
        total_internal_imports += count_internal_imports(tree, module_names)

    parsed = len(files) - len(failures)
    rate = parsed / len(files) * 100

    print(f"\n{'=' * 50}")
    print(f"대상: {root}")
    print(f"{'=' * 50}")
    print(f"파일 수      : {len(files)}개")
    print(f"총 라인 수   : {total_lines:,}줄")
    print(f"파싱 성공    : {parsed}/{len(files)} ({rate:.1f}%)")
    print(f"내부 import : {total_internal_imports}건")

    doc_rate = total_documented / total_targets * 100 if total_targets else 0
    density = total_comments / total_code_lines * 100 if total_code_lines else 0

    print(f"독스트링    : {total_documented}/{total_targets} ({doc_rate:.1f}%)")
    print(f"주석 밀도   : 100줄당 {density:.1f}줄")

    # 청크는 함수, 클래스 단위로 만들어지므로 독스트링 대상 개수와 거의 같다.
    chunks = total_targets
    input_tokens = chunks * PROMPT_TOKENS + total_chars / CHARS_PER_TOKEN
    output_tokens = chunks * SUMMARY_TOKENS
    cost = (
        input_tokens / 1_000_000 * INPUT_PER_MTOK
        + output_tokens / 1_000_000 * OUTPUT_PER_MTOK
    )

    readme_name, readme_chars = find_readme(root)
    readme_label = f"{readme_name} ({readme_chars:,}자)" if readme_name else "없음"

    print(f"테스트 파일: {total_test_files}개")
    print(f"README  : {readme_label}")
    print(f"예상 청크   : 약 {chunks}개")
    print(f"예상 비용   : 약 ${cost:.3f}")

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