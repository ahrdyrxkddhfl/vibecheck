"""인덱싱 대상 파일을 수집한다.

레포 경로를 받아 재귀 순회하며 파싱 가능한 소스 파일만 선별한다
필터링이 파이프라인 최전단에 있는 이유는 이후 모든 단계의 비용이 파일 수에 비례하기 때문이다.
가상환경이나 의존성 폴더가 걸러지지 않으면 수천 개의 무관한 파일이 파싱과 LLM 요약까지 흘러가 시간과 비용을 낭비한다.
"""

from pathlib import Path

EXTENSIONS = {".py"}
"""수집 대상 확장자.

현재는 파이썬만 지원한다. 다른 언어는 tree-sitter 문법 모듈이 추가로 필요하므로,
파서가 처리할 수 있는 범위와 일치시킨다.
"""

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    ".vibecheck",
    "experiments",
}

"""순회에서 제외할 디렉토리 이름

의존성, 빌드 산출물, 캐시는 작성자가 짠 코드가 아니므로 제외한다.
사용자가 설명을 듣고 싶어 하는 대상은 자신이 작성한 코드이며,
라이브러리 코드가 섞이면 검색 결과가 오염된다.

experiments는 본체가 아니라 습작이나 가공된 사본이 들어가는 곳이다.
실제로 독스트링을 벗겨낸 자기 복사본이 인덱싱되어 같은 코드가 두 벌씩
검색에 잡히고, 답변에 어느 쪽이 원본인지 알 수 없는 근거가 섞여 나왔다.
사본은 원본과 내용이 거의 같아 임베딩상 구분되지 않으므로
검색 단계에서 걸러낼 방법이 없고, 수집 단계에서 막아야 한다.
"""

MAX_FILE_SIZE = 500 * 1024
"""파일 크기 상한(바이트).

이 크기를 넘는 파이썬 파일은 대부분 자동 생성 코드나 데이터가 포함된 파일이다.
사람이 작성한 로직일 가능성이 낮은 데 비해
파싱과 요약 비용은 크므로 제외한다.
"""

def collect_files(root: str, exclude_dirs: set[str] | None = None) -> list[Path]:
    """레포에서 인덱싱 대상 파일 목록을 수집한다.

    디렉토리를 재귀 순회하되, 제외 대상 디렉토리는 하위까지 통째로 건너뛴다.
    순회 후 필터링하지 않고 진입 자체를 막는 이유는 node_modules처럼
    파일 수가 수만 개인 디렉토리에서 순회 비용 자체가 문제가 되기 때문이다.

    exclude_dirs는 EXCLUDE_DIRS를 대체하지 않고 합친다.
    대체를 허용하면 호출자가 tests 하나를 빼려다 .venv까지 풀어버리는 사고가 나는데,
    이 사고는 예외 없이 조용히 진행되어 수천 개의 무관한 파일이 LLM 요약까지 흘러간다.
    추가는 안전하고 해제는 위험하므로 방향을 한쪽으로만 연다.

    Args:
        root (str): 레포 루트 경로.
        exclude_dirs (set[str] | None): 기본 제외 목록에 더할 디렉토리 이름.
            실험 A에서 테스트를 채점용 정답지로 쓸 때 인덱스에서 빼는 용도다.
            평소에는 넘기지 않는다. 테스트는 사용 예시를 담고 있어
            독스트링이 없는 레포일수록 검색에 도움이 되기 때문이다.

    Returns:
        list[Path]: 수집된 파일 경로 목록. 경로순으로 정렬되어
                    실행할 때마다 동일한 순서를 보장한다.
    Raises:
        ValueError: 경로가 존재하지 않거나 디렉토리가 아닐 때.
    """

    root_path = Path(root)
    if not root_path.is_dir():
        raise ValueError(f"디렉토리가 아닙니다: {root}")

    # 디렉토리 이름만 보고 거르므로 tests 폴더 밖에 흩어진 test_*.py는 남는다.
    # 대상 레포가 테스트를 한곳에 모아두는 관례를 따를 때만 완전히 걸러진다.
    excluded = EXCLUDE_DIRS | set(exclude_dirs or ())

    results = []

    def scan(directory: Path) -> None:
        """디렉토리를 재귀 순회하며 조건에 맞는 파일을 수집한다.

        Args:
            directory (Path): 순회할 디렉토리.
        """
        for entry in directory.iterdir():
            if entry.is_dir():
                # 제외 대상이거나 숨김 디렉토리면 진입하지 않는다.
                if entry.name in excluded or entry.name.startswith("."):
                    continue
                scan(entry)
            elif entry.suffix in EXTENSIONS:
                if entry.stat().st_size <= MAX_FILE_SIZE:
                    results.append(entry)

    scan(root_path)
    return sorted(results)

def to_relative(path: Path, root: str) -> str:
    """절대 경로를 레포 루트 기준 상대 경로 문자여롤 변환한다.

    Chunk에 저장되는 경로는 상대 경로여야 한다.
    절대 경로를 저장하면 사용자의 홈 디렉토리 이름 같은 개인 정보가 인덱스에 포함되고,
    다른 환경에서 인덱스를 재사용할 수 없게 된다.

    Args:
        path (Path): 변환할 절대 경로.
        root (str): 기준이 되는 레포 루트 경로.

    Returns:
        str: 슬래시로 구분된 상대 경로 문자열.
    """
    return path.relative_to(Path(root)).as_posix()

def find_package_anchor(path: Path) -> Path:
    """모듈 이름의 기준점이 되는 디렉토리를 찾는다.

    __init__.py가 이어지는 가장 바깥 패키지를 찾아 그 부모를 기준점으로 삼는다.
    src/ctxd/client.py는 경로상 세 칸 깊이지만 import는 ctxd.client로 하는데,
    src가 패키지가 아니라 소스를 담아두는 폴더일 뿐이기 때문이다.
    경로를 그대로 모듈 이름으로 바꾸면 src.ctxd.client가 되어 어떤 import와도 대조되지 않는다.

    __init__.py의 유무로 판별하는 이유는 그것이 파이썬이 패키지를 인식하는 기준 그 자체이기 때문이다.
    디렉토리 이름 목록(src, lib 등)을 하드코딩하면 관례를 벗어난 레포에서 바로 틀린다.

    Args:
        path (Path): 소스 파일 경로.

    Returns:
        Path: 모듈 이름을 상대 계산할 기준 디렉토리.
    """
    anchor = path.parent

    # 패키지가 아닌 디렉토리를 만나면 거기가 경계다.
    while (anchor / "__init__.py").exists():
        anchor = anchor.parent

    return anchor

def build_module_map(files: list[Path], root: str) -> dict[str, str]:
    """모듈 이름에서 파일 경로로 가는 대응표를 만든다.

    import 문에 적힌 것은 `vibecheck.core.parser` 같은 모듈 이름이지만,
    파일 간 관계를 그리려면 `vibecheck/core/parser.py`라는 경로가 필요하다.
    이름만으로는 어느 파일을 가리키는지 알 수 없어 화살표를 그을 수 없다.

    build_module_names와 같은 계산을 하되 이름만 남기지 않고 출처를 함께
    보관한다. 이름 집합이 필요한 쪽은 이 표의 키만 쓰면 되므로
    계산이 두 벌로 갈라지지 않는다.

    Args:
        files (list[Path]): collect_files가 수집한 경로 목록.
        root (str): 레포 루트 경로. 기준점이 루트를 벗어날 때의 안전망.

    Returns:
        dict[str, str]: 모듈 이름 -> 레포 루트 기준 상대 경로.
    """
    mapping: dict[str, str] = {}
    root_path = Path(root).resolve()

    for path in files:
        resolved = Path(path).resolve()
        anchor = find_package_anchor(resolved)

        # 기준점이 레포 밖으로 나가면(루트 자체가 패키지인 경우) 루트로 되돌린다.
        try:
            rel = resolved.relative_to(anchor)
        except ValueError:
            rel = resolved.relative_to(root_path)

        module = str(rel.with_suffix("")).replace("/", ".")

        # __init__.py는 파일이 아니라 패키지 자체를 가리킨다.
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        elif module == "__init__":
            continue

        mapping[module] = resolved.relative_to(root_path).as_posix()

    return mapping


def build_module_names(files: list[Path], root: str) -> set[str]:
    """수집된 파일들의 모듈 이름 집합을 만든다.

    import 대상이 레포 내부인지 외부 라이브러리인지 가르려면
    "내부에 무엇이 있는지" 목록이 먼저 필요하다.

    Args:
        files (list[Path]): collect_files가 수집한 경로 목록.
        root (str): 레포 루트 경로. 기준점이 루트를 벗어날 때의 안전망으로 쓴다.
        계산은 build_module_map에 맡기고 키만 꺼낸다.
        같은 계산을 두 벌로 두면 한쪽만 고쳤을 때 이름 집합과 대응표가
        어긋나는데, 그 차이는 예외 없이 조용히 진행된다.

    Returns:
        set[str]: 점으로 구분된 모듈 이름 집합.
    """
    return set(build_module_map(files, root))


def is_internal_import(dotted: str, module_names: set[str]) -> bool:
    """import 대상이 레포 내부 모듈인지 판별한다.

    모듈 이름을 앞에서부터 잘라가며 대조하는 이유는 수집 경로의 기준점이
    실행 위치에 따라 달라지기 때문이다.
    ctxd.client로 잡힐 수도 client로 잡힐 수도 있다.

    부분 일치를 허용하므로 외부 모듈이 내부와 같은 이름이면 잘못 판정할 수 있다.
    의존성 목록을 만드는 용도이므로 이 정도 오차는 감수한다.

    Args:
        dotted (str): 점으로 구분된 import 대상 이름.
        module_names (set[str]): 내부 모듈 이름 집합.

    Returns:
        bool: 내부 모듈이면 True.
    """
    # 상대 경로 import(from . import x)는 항상 내부다.
    if dotted.startswith("."):
        return True

    parts = dotted.split(".")
    for i in range(len(parts)):
        if ".".join(parts[i:]) in module_names:
            return True
    return False

if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    files = collect_files(target)

    for f in files:
        print(to_relative(f, target))
    print(f"\n총 {len(files)}개 파일")