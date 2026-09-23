"""인덱싱 대상 파일을 수집한다.

레포 경로를 받아 재귀 순회하며 파싱 가능한 소스 파일만 선별한다
필터링이 파이프라인 최전단에 있는 이유는 이후 모든 단계의 비용이 파일 수에 비례하기 때문이다.
가상환경이나 의존성 폴더가 걸러지지 않으면 수천 개의 무관한 파일이 파싱과 LLM 요약까지 흘러가 시간과 비용을 낭비한다.
"""

from dataclasses import dataclass, field
from pathlib import Path

from vibecheck.core.languages import spec_for, supported_extensions

EXTENSIONS = supported_extensions()
"""수집 대상 확장자.

지원 언어 목록(languages.py)에서 만든다. 파서가 읽을 수 있는 범위와
수집 범위가 따로 적혀 있으면, 언어를 더할 때 한쪽만 고쳐 조용히 어긋난다.
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


@dataclass
class CollectResult:
    """수집된 파일과 수집 과정에서 버려진 것을 함께 담는다.

    목록만 돌려주면 호출자는 무엇이 빠졌는지 알 방법이 없고,
    파이썬이 아닌 파일로 이루어진 레포에서도 인덱싱이 성공한 것처럼 끝난다.
    부분 결과를 완전한 결과로 보이게 하는 것은 사용자를 적극적으로 오도하므로,
    버린 것을 세어 함께 돌려준다.

    제외 디렉토리(.venv, node_modules 등)는 세지 않는다.
    진입 자체를 막아 비용을 아끼는 것이 목적이고,
    의존성 폴더의 수천 개를 보고하면 정작 봐야 할 소수의 항목이 묻힌다.
    사용자가 자기 코드라고 믿었는데 빠진 것만 보고 대상이다.

    Attributes:
        files (list[Path]): 인덱싱 대상으로 선별된 파일 경로.
        skipped_other (list[Path]): 확장자가 대상이 아니어서 제외된 파일.
            개수만 세면 뺄셈이 불가능하다. README나 pyproject처럼
            수집 대상이 아니면서 다른 경로로 인덱싱되는 파일이 있어,
            보고 단계에서 골라내려면 경로가 남아 있어야 한다.
        skipped_by_size (list[Path]): 크기 상한을 넘겨 제외된 파일.
            개수가 적고 사용자가 이름을 보면 납득하는 종류라 경로를 그대로 보관한다.
    """

    files: list[Path]
    skipped_other: list[Path] = field(default_factory=list)
    skipped_by_size: list[Path] = field(default_factory=list)


def collect_source_files(
    root: str, exclude_dirs: set[str] | None = None
) -> CollectResult:
    """레포에서 인덱싱 대상 파일을 수집하고 버린 것을 함께 보고한다.

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
        CollectResult: 수집 결과. files는 경로순으로 정렬되어
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

    results: list[Path] = []
    skipped_other: list[Path] = []
    skipped_size: list[Path] = []

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
                else:
                    skipped_size.append(entry)
            else:
                skipped_other.append(entry)

    scan(root_path)

    return CollectResult(
        files=sorted(results),
        skipped_other=sorted(skipped_other),
        skipped_by_size=sorted(skipped_size),
    )


def collect_files(root: str, exclude_dirs: set[str] | None = None) -> list[Path]:
    """레포에서 인덱싱 대상 파일 목록을 수집한다.

    수집 규칙은 collect_source_files에 있고 여기서는 목록만 꺼낸다.
    제외 내역이 필요 없는 호출자가 대부분이라 기존 형태를 유지하되,
    같은 순회를 두 벌로 두지는 않는다. 규칙이 갈라지면 한쪽만 고쳤을 때
    수집 결과와 보고 내용이 어긋나고, 그 차이는 조용히 진행된다.

    Args:
        root (str): 레포 루트 경로.
        exclude_dirs (set[str] | None): 기본 제외 목록에 더할 디렉토리 이름.

    Returns:
        list[Path]: 수집된 파일 경로 목록. 경로순으로 정렬되어 있다.

    Raises:
        ValueError: 경로가 존재하지 않거나 디렉토리가 아닐 때.
    """
    return collect_source_files(root, exclude_dirs).files


def to_relative(path: Path, root: str) -> str:
    """절대 경로를 레포 루트 기준 상대 경로 문자열로 변환한다.

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


def group_by_extension(
    paths: list[Path], root: str, indexed: set[str] | None = None
) -> dict[str, int]:
    """제외된 파일을 확장자별 개수로 묶는다.

    indexed를 받는 이유는 수집 대상이 아닌 것과 인덱스에 없는 것이 다르기 때문이다.
    README와 pyproject.toml은 확장자 필터에 걸려 여기까지 오지만
    별도 경로로 청크가 되어 실제로는 검색된다.
    이것을 제외됐다고 보고하면 조용한 누락을 고치려다 거짓 보고를 만드는 셈이 된다.

    Args:
        paths (list[Path]): 제외된 파일 경로 목록.
        root (str): 레포 루트 경로. 상대 경로 대조에 쓴다.
        indexed (set[str] | None): 다른 경로로 인덱싱된 파일의 상대 경로 집합.
            보고에서 빼되 수집 결과는 건드리지 않는다.

    Returns:
        dict[str, int]: 확장자 -> 개수. 개수 내림차순, 같으면 이름순으로
                        정렬되어 표시 계층이 그대로 앞에서부터 자를 수 있다.
                        확장자가 없는 파일은 빈 문자열 키로 묶인다.
    """
    handled = indexed or set()
    counts: dict[str, int] = {}

    for path in paths:
        if to_relative(path, root) in handled:
            continue
        counts[path.suffix] = counts.get(path.suffix, 0) + 1

    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def format_skipped(counts: dict[str, int], top: int = 5) -> str:
    """확장자별 제외 개수를 한 줄 문장으로 만든다.

    상위 몇 개만 보이고 나머지를 접는다.
    실제 레포에서 28종이 한 줄로 쏟아졌고, 사용자가 봐야 할 .java가
    빌드 산출물인 .class 뒤에 묻혔다.
    진입점과 모듈 지도에서 이미 같은 기준으로 접고 있다.

    CLI와 웹이 같은 문장을 쓰도록 여기에 둔다.
    양쪽이 따로 조립하면 한쪽만 고쳤을 때 같은 레포가 다른 숫자를 말하게 된다.

    Args:
        counts (dict[str, int]): group_by_extension의 결과. 정렬을 가정한다.
        top (int): 그대로 나열할 확장자 종류 수.

    Returns:
        str: 표시 문장. counts가 비었으면 빈 문자열.
    """
    if not counts:
        return ""

    items = list(counts.items())
    shown = items[:top]
    rest = items[top:]

    detail = ", ".join(f"{ext or '(확장자 없음)'} {n}" for ext, n in shown)
    # 한 종류만 남으면 접는 쪽이 더 길고 정보는 적다.
    if len(rest) == 1:
        ext, n = rest[0]
        detail += f", {ext or '(확장자 없음)'} {n}"
    elif rest:
        detail += f", 그 외 {len(rest)}종 {sum(n for _, n in rest)}개"

    return f"제외 {sum(counts.values())}개: {detail}"


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


def module_entries(files: list[Path], root: str) -> list[tuple[str, str]]:
    """파일마다 모듈 이름을 붙인다.

    대응표(build_module_map)와 이름 집합(build_module_names)이 이 한 계산을
    나눠 쓴다. 같은 계산을 두 벌로 두면 한쪽만 고쳤을 때 둘이 어긋나는데,
    그 차이는 예외 없이 조용히 진행된다.

    이름이 겹칠 수 있어 사전이 아니라 목록으로 돌려준다. Java 파일은 클래스
    이름만 받으므로 다른 패키지의 같은 이름 클래스가 같은 이름이 되고, 파이썬도
    __init__.py 없는 폴더의 같은 이름 파일은 같은 이름이 된다.

    Args:
        files (list[Path]): collect_files가 수집한 경로 목록.
        root (str): 레포 루트 경로. 기준점이 루트를 벗어날 때의 안전망.

    Returns:
        list[tuple[str, str]]: (모듈 이름, 레포 루트 기준 상대 경로) 목록.
    """
    entries: list[tuple[str, str]] = []
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

        entries.append((module, resolved.relative_to(root_path).as_posix()))

    return entries


def build_module_map(files: list[Path], root: str) -> dict[str, str]:
    """모듈 이름에서 파일 경로로 가는 대응표를 만든다.

    import 문에 적힌 것은 `vibecheck.core.parser` 같은 모듈 이름이지만,
    파일 간 관계를 그리려면 `vibecheck/core/parser.py`라는 경로가 필요하다.
    이름만으로는 어느 파일을 가리키는지 알 수 없어 화살표를 그을 수 없다.

    이름 하나에 파일이 하나인 것만 싣는다. a/Config.java와 b/Config.java가
    함께 있으면 Config가 어느 쪽인지 이름만으로 정할 수 없다. 예전에는 뒤의
    파일이 앞의 파일을 조용히 덮어써서, 수집 순서가 간선의 도착지를 정했다.
    관계도(relations.type_neighbors)와 채점 근거(practice)도 겹치는 이름은
    짐작하지 않고 뺀다.

    이 표의 키를 내부 판별용 이름 집합으로 쓰면 안 된다. 겹치는 이름이 빠져
    있어, 그 클래스를 가져다 쓰는 import가 외부로 판정된다. 판별에는
    build_module_names를 쓴다.

    Args:
        files (list[Path]): collect_files가 수집한 경로 목록.
        root (str): 레포 루트 경로. 기준점이 루트를 벗어날 때의 안전망.

    Returns:
        dict[str, str]: 모듈 이름 -> 레포 루트 기준 상대 경로.
            이름이 둘 이상의 파일에 붙으면 싣지 않는다.
    """
    paths: dict[str, list[str]] = {}
    for module, path in module_entries(files, root):
        paths.setdefault(module, []).append(path)

    return {module: ps[0] for module, ps in paths.items() if len(ps) == 1}


def build_module_names(files: list[Path], root: str) -> set[str]:
    """수집된 파일들의 모듈 이름 집합을 만든다.

    import 대상이 레포 내부인지 외부 라이브러리인지 가르려면
    "내부에 무엇이 있는지" 목록이 먼저 필요하다.

    대응표(build_module_map)와 달리 이름이 겹치는 것도 싣는다. 판별에는 어느
    파일인지가 필요 없고, 레포 안에 그 이름이 있다는 것만으로 충분하다.

    Args:
        files (list[Path]): collect_files가 수집한 경로 목록.
        root (str): 레포 루트 경로. 기준점이 루트를 벗어날 때의 안전망으로 쓴다.

    Returns:
        set[str]: 점으로 구분된 모듈 이름 집합.
    """
    return {module for module, _ in module_entries(files, root)}


def build_package_names(files: list[Path]) -> set[str]:
    """파일들이 선언한 패키지 이름을 모은다.

    모듈 이름 집합은 파일마다 이름 하나를 붙여 만든다. Java 파일은 클래스
    이름(B)만 받으므로 import com.a.*가 남기는 패키지 이름 com.a는 어떤 파일과도
    대조되지 않아, 자기 패키지를 통째로 가져다 쓰면 외부 의존성으로 올라간다.
    이 집합을 모듈 이름 집합에 더하면 그 이름이 내부로 판정된다.

    모듈 대응표(build_module_map)에는 넣지 않는다. 패키지는 파일 하나를
    가리키지 않아 import 간선의 도착지가 될 수 없다.

    패키지 선언이 따로 없는 언어(package_of가 None)의 파일은 읽지 않는다.

    Args:
        files (list[Path]): collect_files가 수집한 경로 목록.

    Returns:
        set[str]: 점으로 구분된 패키지 이름 집합.
    """
    names: set[str] = set()

    for path in files:
        spec = spec_for(path)
        if spec is None or spec.package_of is None:
            continue

        source = Path(path).read_text(encoding="utf-8", errors="replace")
        package = spec.package_of(source)
        if package:
            names.add(package)

    return names


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
    result = collect_source_files(target)

    for f in result.files:
        print(to_relative(f, target))
    print(f"\n총 {len(result.files)}개 파일")

    skipped = group_by_extension(result.skipped_other, target)
    if skipped:
        print(format_skipped(skipped))

    for path in result.skipped_by_size:
        print(f"크기 초과 제외: {to_relative(path, target)}")
