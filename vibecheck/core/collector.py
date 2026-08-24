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
}

"""순회에서 제외할 디렉토리 이름

의존성, 빌드 산출물, 캐시는 작성자가 짠 코드가 아니므로 제외한다.
사용자가 설명을 듣고 싶어 하는 대상은 자신이 작성한 코드이며,
라이브러리 코드가 섞이면 검색 결과가 오염된다.
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

if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "."
    files = collect_files(target)

    for f in files:
        print(to_relative(f, target))
    print(f"\n총 {len(files)}개 파일")