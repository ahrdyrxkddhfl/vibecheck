"""파이썬 파일에서 독스트링과 주석만 제거한 사본을 만든다.

대조 실험용 스크립트다. 현재 인덱싱 품질은 자기 코드로 검증했는데 독스트링이 충실해 결과가 부풀려졌을 가능성이 있다.
실제 타겟인 바이브코드 코딩도 그렇다는 보장이 없으므로, 설명만 제거한 사본으로 같은 질문을 던져 성능 차이를 격리 측정한다.

정규식을 쓰지 않는 이유는 정규식이 글자 모양만 보기 때문이다.
문자열 안의 #이나 독스트링이 아닌 여러 줄 문자열을 구분하지 못해 코드를 손상시킨다.
대신 파이썬 자체 도구로 정체를 판별한다.
"""

import ast
import io
import shutil
import tokenize
from pathlib import Path

def find_docstring_lines(source: str) -> set[int]:
    """제거 대상 문자열이 차지하는 줄 번호를 찾는다.

    ast를 쓰는 이유는 문자열의 정체가 위치에 의존하기 때문이다.
    같은 따옴표 세 개라도 변수에 대입된 문자열은 데이터이므로
    제거하면 코드가 망가진다. ast는 구문 구조를 알기에 구분할 수 있다.

    제거 대상은 '식으로 홀로 놓인 문자열' 전부다. 이 형태는 값이
    어디에도 쓰이지 않아 실행에 영향이 없고, 오직 사람에게 설명하려는
    목적으로만 존재한다. 함수·클래스·모듈의 독스트링뿐 아니라
    변수 아래 관례적으로 붙이는 설명 문자열도 여기 포함된다.
    실험에서는 설명이 한 파일에만 남으면 변수 통제가 깨지므로
    이들을 함께 제거한다.

    Args:
        source (str): 파이썬 소스 코드 전문.

    Returns:
        set[int]: 제거 대상이 위치한 1-based 줄 번호 집합.
    """
    tree = ast.parse(source)
    lines: set[int] = set()

    for node in ast.walk(tree):
        # Expr은 '값을 계산하고 버리는 문장'이다.
        # 그 값이 문자열이면 아무 효과도 없으므로 설명용으로 본다.
        if not isinstance(node, ast.Expr):
            continue

        if not (isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            continue

        # 여러 줄 문자열을 위해 시작~끝 줄을 모두 담는다.
        lines.update(range(node.lineno, node.end_lineno + 1))

    return lines

def remove_comments(source: str) -> str:
    """소스에서 주석만 제거한다.

    tokenize를 쓰는 이유는 ast가 주석을 보존하지 않기 때문이다.
    주석은 실행에 영향이 없어 구문 트리에 담기지 않는다.
    tokenize는 코드를 토큰으로 쪼개며 각 토큰에 종류를 붙여주므로,
    COMMENT 종류만 골라 제거하면 문자열 안의 '#'는 건드리지 않는다.

    untokenize로 복원하지 않고 줄 단위로 잘라내는 이유는
    untokenize가 공백과 들여쓰기를 원본과 다르게 재구성할 수 있기 때문이다.
    실험에서는 주석 외의 변화를 만들지 않아야 한다.

    Args:
        source (str): 파이썬 소스 코드 전문.

    Returns:
        str: 주석이 제거된 소스 코드.
    """
    lines = source.splitlines()
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)

    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue

        row, col = token.start # 1-based 줄, 0-based 칸
        line = lines[row -1 ]
        # 주석 앞부분만 남긴다. 코드 뒤 주석(x = 1 #메모)도 처리된다.
        lines[row -1] = line[:col].rstrip()

    return "\n".join(lines)

def strip_source(source: str) -> str:
    """소스에서 독스트링과 주석을 모두 제거한다.

    주석을 먼저 제거하면 줄 내용이 바뀌어 ast가 계산한 줄 번호와 어긋날 수 있다.
    따라서 독스트링 줄 번호를 먼저 확정한 뒤 제거하고, 주석은 그 후에 처리한다.

    빈 줄을 남기지 않고 삭제하는 이유는 독스트링이 사라진 자리에 빈 줄이 남으면 함수 본문이 비어
    SyntaxError가 나기 때문이다.

    Args:
        source (str): 원본 파이썬 소스 코드.

    Returns:
        str: 독스트링과 주석이 제거된 소스 코드.
    """
    doc_lines = find_docstring_lines(source)

    kept = [
        line
        for i, line in enumerate(source.splitlines(), start=1)
        if i not in doc_lines
    ]

    return remove_comments("\n".join(kept))

def strip_repo(src_dir: Path, dst_dir: Path) -> None:
    """디렉토리의 모든 파이썬 파일을 제거 처리해 복사한다.

    출력 디렉토리를 매번 지우고 새로 만드는 이유는 이전 실행의 잔여 파일이 남으면 실험 대상이 오염되기 때문이다.

    파이썬이 아닌 파일은 복사하지 않는다.
    인덱싱 대상이 .py뿐이라 나머지는 실험에 영향을 주지 않는다.

    Args:
        src_dir (Path): 원본 디렉토리.
        dst_dir (Path): 사본을 저장할 디렉토리.
    """
    if dst_dir.exists():
        shutil.rmtree(dst_dir)

    count = 0

    for src_file in src_dir.rglob("*.py"):
        # 캐시와 가상환경은 원본 코드가 아니므로 건너뛴다.
        if any(part in {"__pycache__", "/venv"} for part in src_file.parts):
            continue

        source = src_file.read_text(encoding="utf-8")
        stripped = strip_source(source)

        # 원본의 디렉토리 구조를 그대로 유지한다.
        dst_file = dst_dir / src_file.relative_to(src_dir)
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        dst_file.write_text(stripped, encoding="utf-8")

        count += 1
        print(f"    {src_file} -> {dst_file}")

    print(f"\n총 {count}개 파일 처리 완료")

if __name__ == "__main__":
    strip_repo(Path("vibecheck"), Path("experiments/stripped/vibecheck"))
