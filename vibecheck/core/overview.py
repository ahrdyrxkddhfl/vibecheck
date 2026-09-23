"""레포 전체를 조망하는 개요(L0)를 조립한다.

L2(함수·클래스)와 L1(파일)만으로는 답할 수 없는 질문이 있다.
"이 프로젝트는 무엇을 하는가"의 답은 어느 파일 하나에 있지 않고 전체에 흩어져 있다.
실험 A에서 이 질문이 세 조건 모두 정답 청크를 찾지 못한 것이 그 증거다.

이 모듈은 LLM을 호출하지 않고 조립만 한다.
통계, 의존성 목록, 파일 지도, 진입점은 모두 이미 인덱싱된 정보에서 계산되므로
LLM에 물을 이유가 없고, 조립은 실행할 때마다 같은 결과를 낸다.
문장으로 된 요약은 별도 모듈에서 LLM으로 생성한다.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from vibecheck.core.collector import (
    build_module_map,
    build_module_names,
    build_package_names,
    collect_source_files,
    format_skipped,
    group_by_extension,
    is_internal_import,
    to_relative,
)
from vibecheck.core.languages import spec_for
from vibecheck.prompts import load_prompt
from vibecheck.llm.base import LLMClient
from vibecheck.models import Chunk

ENTRY_FILENAMES = {"__main__.py", "main.py", "cli.py", "app.py", "manage.py"}
"""진입점일 가능성이 높은 파일 이름.

관례일 뿐 보장이 아니므로 추정 근거로만 쓰고, 확정된 근거와 구분해 표시한다.
"""

NON_ENTRY_HINTS = ("test", "dummy", "example", "sample", "bench", "demo")
"""진입점 후보에서 뒤로 밀 파일 이름 조각.

직접 실행할 수 있는 것은 맞지만 "이 프로젝트는 어디서 시작하나"의 답은 아니다.
실제로 dummy_test.py가 main.py와 같은 자리에 올라와 진짜 진입점을 흐렸고,
scripts/ 아래 실험 스크립트 11개가 확정 진입점 1개를 묻었다.

목록에서 지우지는 않는다. 직접 실행 가능한 것은 사실이므로
지우면 거짓이 되고, 순서만 바꾸면 사실을 유지한 채 우선순위를 표현할 수 있다.

디렉터리가 아니라 파일 이름을 보는 이유는 관례를 벗어난 배치 때문이다.
dummy_test.py는 tests/ 밖에 있어 경로만으로는 걸러지지 않는다.
"""

README_LIMIT = 3000
"""프롬프트에 넣을 README의 최대 글자 수.

README는 길이가 제각각이고 설치법이나 라이선스가 뒤쪽을 차지하는 경우가 많다.
프로젝트가 무엇인지는 대개 앞부분에 나오므로 앞에서 잘라 쓴다.
"""


@dataclass
class EntryPoint:
    """진입점 후보 하나.

    Attributes:
        target (str): 진입 지점 표기. 파일 경로 또는 "모듈:함수" 형태.
        evidence (str): 무엇을 보고 판단했는지.
        confirmed (bool): 확정 여부.
            pyproject.toml에 등록된 것만 확정으로 본다.
            나머지는 파일 이름이나 코드 관례에 기댄 추정이므로,
            리포트에서 둘을 섞으면 읽는 사람이 확신도를 오해한다.
    """

    target: str
    evidence: str
    confirmed: bool = False


@dataclass
class RepoOverview:
    """레포 전체 개요.

    Attributes:
        root (str): 레포 루트 경로.
        name (str): 레포 이름.
        file_count (int): 수집된 파일 수.
            청크가 생긴 파일이 아니라 collect_source_files가 수집한 파일 전부다.
            심볼도 import도 없는 빈 파일은 청크를 만들지 않지만
            레포의 파일인 것은 맞으므로 규모에서 빼지 않는다.
        total_lines (int): 총 줄 수.
        symbol_count (int): 함수·클래스 청크 수.
        documented_count (int): 원본에 독스트링이 있던 심볼 수.
        external_deps (list[str]): 서드파티 라이브러리 이름 목록.
        stdlib_deps (list[str]): 표준 라이브러리 이름 목록.
        internal_import_count (int): 내부 모듈을 가리키는 import 수.
        file_map (list[tuple[str, str]]): (파일 경로, 파일 개요) 목록.
            L1 청크의 code 필드를 쓴다. summary는 검색 임베딩용이라
            키워드만 담고 있어 심볼별 설명이 빠져 있다.
        entry_points (list[EntryPoint]): 진입점 후보 목록.
        readme (str): README 본문. 없으면 빈 문자열.
        skipped_note (str): 분석하지 못한 파일을 알리는 한 줄. 없으면 빈 문자열.
            개수 목록이 아니라 완성된 문장을 담는 이유는 CLI와 웹이
            같은 문장을 말하게 하기 위해서다. 양쪽이 각자 조립하면
            한쪽만 고쳤을 때 같은 레포가 화면마다 다른 숫자를 말한다.
        skipped_large (list[str]): 크기 상한을 넘겨 빠진 파일의 상대 경로.
            확장자가 대상이 아닌 파일과 종류가 다르다. 사용자가 분석되리라
            믿는 파이썬 파일이 빠진 것이라 개수가 아니라 이름을 밝힌다.
    """

    root: str
    name: str
    file_count: int = 0
    total_lines: int = 0
    symbol_count: int = 0
    documented_count: int = 0
    external_deps: list[str] = field(default_factory=list)
    stdlib_deps: list[str] = field(default_factory=list)
    internal_import_count: int = 0
    import_edges: list[tuple[str, str]] = field(default_factory=list)
    file_map: list[tuple[str, str]] = field(default_factory=list)
    entry_points: list[EntryPoint] = field(default_factory=list)
    readme: str = ""
    skipped_note: str = ""
    skipped_large: list[str] = field(default_factory=list)



def split_dependencies(
    chunks: list[Chunk], module_names: set[str]
) -> tuple[list[str], list[str], int]:
    """import 목록을 서드파티, 표준 라이브러리, 내부 모듈로 가른다.

    표준 라이브러리를 따로 빼는 이유는 리포트에서 답해야 할 질문이
    "왜 이 라이브러리를 골랐는가"이기 때문이다.
    os나 json을 왜 썼는지 묻는 사람은 없다. httpx와 pydantic을 골랐다는 것이 정보이고,
    표준 라이브러리 열 몇 개가 목록에 섞이면 그 정보가 묻힌다.

    외부 라이브러리는 라이브러리 이름으로 묶는다. httpx.AsyncClient와
    httpx.RequestError는 같은 라이브러리이므로 따로 세면 의존성이 실제보다
    많아 보인다. 라이브러리 이름이 import의 어디에 있는지와 무엇이 표준인지는
    언어마다 달라 청크 파일의 언어 설정(dependency_of)에 맡긴다. 파이썬처럼
    첫 조각만 떼면 Java의 org.springframework가 org로 줄어 뜻이 사라진다.

    내부인지 가를 때는 import 이름을 언어 설정(import_target)으로 줄여서
    대조한다. Java의 import static com.a.B.c는 B.java를 가리키지만, 원래 이름
    그대로는 파일 이름 B와 만나지 않아 자기 패키지가 외부 의존성으로 올라간다.
    외부로 판정된 뒤에는 원래 이름을 dependency_of에 넘긴다. 라이브러리 이름을
    고르는 규칙은 거기에 따로 있다.

    Args:
        chunks (list[Chunk]): 인덱싱된 청크 목록.
        module_names (set[str]): 내부 모듈 이름 집합.

    Returns:
        tuple[list[str], list[str], int]:
            (서드파티 이름 목록, 표준 라이브러리 이름 목록, 내부 import 수).
    """
    third_party: set[str] = set()
    stdlib: set[str] = set()
    internal_count = 0

    for chunk in chunks:
        spec = spec_for(chunk.file)
        for imp in chunk.imports:
            target = spec.import_target(imp) if spec else imp
            if is_internal_import(target, module_names):
                internal_count += 1
                continue

            # 코드 청크는 지원 언어 파일에서만 나오므로 spec이 있다.
            # 없다면 이름을 알 수 없으니 목록에 섞지 않는다.
            if spec is None:
                continue

            name, is_stdlib = spec.dependency_of(imp)
            if is_stdlib:
                stdlib.add(name)
            else:
                third_party.add(name)

    return sorted(third_party), sorted(stdlib), internal_count


def build_import_edges(
    l1: list[Chunk], module_map: dict[str, str]
) -> list[tuple[str, str]]:
    """파일이 파일을 가리키는 간선 목록을 만든다.

    지금까지 내부 참조는 개수만 셌다. 59건이라는 숫자는 얼마나 얽혀 있는지는
    알려주지만 어떻게 얽혀 있는지는 말해주지 않아, 관계도를 그릴 수 없었다.

    L1 청크만 훑는다. 파일 하나당 하나뿐이라 출발지가 곧 그 파일이고,
    imports에 그 파일의 import가 전부 들어 있다. L2를 쓰면 같은 import가
    그 파일의 함수 수만큼 중복돼 간선이 부풀려진다.

    상대 경로 import(from . import x)는 버린다. 점만으로는 어느 파일을
    가리키는지 알 수 없어 도착지를 정할 수 없다. is_internal_import는
    이것을 내부로 세지만 개수와 간선은 목적이 다르다.

    import 이름은 언어 설정(import_target)으로 줄인 뒤 대조한다. Java의
    import com.a.B.Inner는 B.java를 가리키는데, 원래 이름 그대로는 어떤
    파일과도 만나지 않아 간선이 빠진다. split_dependencies와 같은 이유다.

    자기 자신을 가리키는 간선도 버린다. 패키지 안에서 같은 이름이
    겹칠 때 생기는데, 관계도에서 자기 자신으로 도는 화살표는 정보가 아니다.

    Args:
        l1 (list[Chunk]): 파일 단위 청크 목록.
        module_map (dict[str, str]): 모듈 이름 -> 파일 경로 대응표.

    Returns:
        list[tuple[str, str]]: (가리키는 파일, 가리켜지는 파일) 목록.
            중복은 제거하고 경로순으로 정렬한다.
    """
    edges: set[tuple[str, str]] = set()

    for chunk in l1:
        spec = spec_for(chunk.file)
        for imp in chunk.imports:
            if imp.startswith("."):
                continue

            # 모듈 이름을 앞에서부터 잘라가며 대조한다. 수집 경로의 기준점이
            # 실행 위치에 따라 달라져 vibecheck.core.parser로 잡힐 수도
            # core.parser로 잡힐 수도 있다. is_internal_import와 같은 방식이다.
            name = spec.import_target(imp) if spec else imp
            parts = name.split(".")
            target = None
            for i in range(len(parts)):
                candidate = ".".join(parts[i:])
                if candidate in module_map:
                    target = module_map[candidate]
                    break

            if target and target != chunk.file:
                edges.add((chunk.file, target))

    return sorted(edges)


def find_script_entries(root: Path) -> list[EntryPoint]:
    """pyproject.toml에 등록된 콘솔 스크립트를 찾는다.

    등록된 스크립트는 추정이 아니라 확정된 진입점이다.
    패키지를 설치하면 실제로 그 이름의 명령이 만들어지기 때문이다.

    파일이 없거나 형식이 깨져 있어도 예외를 올리지 않는다.
    진입점은 개요의 한 항목일 뿐이라, 여기서 멈추면 나머지 정보까지 잃는다.

    Args:
        root (Path): 레포 루트.

    Returns:
        list[EntryPoint]: 확정된 진입점 목록.
    """
    path = root / "pyproject.toml"
    if not path.is_file():
        return []

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []

    scripts = data.get("project", {}).get("scripts", {})
    return [
        EntryPoint(
            target=f"{command} -> {target}",
            evidence="pyproject.toml [project.scripts]에 등록됨",
            confirmed=True,
        )
        for command, target in scripts.items()
    ]


def find_code_entries(chunks: list[Chunk], root: Path) -> list[EntryPoint]:
    """코드와 파일 이름에서 진입점 후보를 추정한다.

    무엇을 실행 가능한 근거로 볼지는 언어마다 달라 언어 설정(entry_evidence)에
    맡긴다. 파이썬은 __main__ 블록, Java는 main 메서드다. 둘 다 청크에 남지
    않는 자리라 파일 본문을 직접 확인한다.

    파일 이름 관례(ENTRY_FILENAMES)는 파이썬 이름들이라 Java 파일에는 걸리지
    않는다.

    Args:
        chunks (list[Chunk]): 인덱싱된 청크 목록.
        root (Path): 레포 루트.

    Returns:
        list[EntryPoint]: 추정된 진입점 목록.
    """
    found: dict[str, EntryPoint] = {}

    for file_path in sorted({c.file for c in chunks}):
        name = file_path.rsplit("/", 1)[-1]

        try:
            source = (root / file_path).read_text(encoding="utf-8")
        except OSError:
            source = ""

        spec = spec_for(file_path)
        evidence = spec.entry_evidence(source) if spec else None

        if evidence:
            found[file_path] = EntryPoint(target=file_path, evidence=evidence)
        elif name in ENTRY_FILENAMES:
            found[file_path] = EntryPoint(
                target=file_path,
                evidence=f"파일 이름이 {name}",
            )

    # main 함수가 있으면 근거를 보강한다. 이름만 맞은 경우보다 확실하다.
    for chunk in chunks:
        if chunk.symbol == "main" and chunk.file in found:
            found[chunk.file].evidence += ", main() 함수 정의됨"

    def rank(entry: EntryPoint) -> tuple:
        """진입점다운 정도로 정렬 키를 만든다.

        낮을수록 앞에 온다. 세 단계로 가른다:
        이름이 실험·테스트를 암시하는가, 루트에 있는가, 경로가 무엇인가.

        Args:
            entry (EntryPoint): 순위를 매길 진입점 후보.

        Returns:
            tuple: 정렬 키.
        """
        path = entry.target
        name = path.rsplit("/", 1)[-1].lower()

        weak = any(hint in name for hint in NON_ENTRY_HINTS)
        # 루트에 있는 파일이 패키지 안쪽보다 진입점일 가능성이 높다.
        nested = "/" in path

        return (weak, nested, path)

    return sorted(found.values(), key=rank)

def read_readme(root: Path) -> str:
    """레포 루트의 README 본문을 읽는다.

    glob("README*")로 찾지 않는다. 대소문자를 구분하지 않는 파일시스템에서도
    glob은 패턴 매칭이라 대소문자를 구분해 readme.md를 놓친다.
    소문자 README를 쓰는 레포에서 "이 프로젝트가 무엇인가"의 답이 담긴
    유일한 재료가 요약 프롬프트에서 통째로 빠지고, 화면은 README가 없다고 말한다.

    Args:
        root (Path): 레포 루트.

    Returns:
        str: README 본문. 없으면 빈 문자열.
    """
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return ""

    for path in entries:
        if not path.name.lower().startswith("readme") or not path.is_file():
            continue
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return ""

def build_file_map(l1: list[Chunk], l2: list[Chunk]) -> list[tuple[str, str]]:
    """파일별 개요를 조립한다.

    L1 청크의 code를 쓰지 않는 이유는, 인덱스에서 청크를 복원할 때
    줄 범위로 소스를 다시 읽기 때문이다.
    L1은 파일 전체를 범위로 가지므로 code에 소스 원문이 통째로 들어간다.
    요약 재료로는 소스가 아니라 심볼별 설명이 필요하다.

    L1의 summary(라이브러리와 심볼 이름)에 L2의 심볼별 요약을 덧붙인다.
    두 정보의 출처가 다르므로 여기서 합친다.

    Args:
        l1 (list[Chunk]): 파일 단위 청크 목록.
        l2 (list[Chunk]): 함수·클래스 단위 청크 목록.

    Returns:
        list[tuple[str, str]]: (파일 경로, 개요 텍스트) 목록. 경로순 정렬.
    """
    by_file: dict[str, list[Chunk]] = {}
    for chunk in l2:
        by_file.setdefault(chunk.file, []).append(chunk)

    result = []
    for chunk in sorted(l1, key=lambda c: c.file):
        lines = [chunk.summary or ""]

        symbols = by_file.get(chunk.file, [])
        if symbols:
            lines.append("  심볼별 요약:")
            lines += [
                f"    {s.symbol}: {s.summary}" for s in symbols if s.summary
            ]

        result.append((chunk.file, "\n".join(lines)))

    return result


def build_overview(
    root: str,
    chunks: list[Chunk],
    exclude_dirs: set[str] | None = None,
) -> RepoOverview:
    """인덱싱된 청크로부터 레포 개요를 조립한다.

    분석하지 못한 파일도 함께 담는다. 파이썬만 읽는 도구가 자바로 된 레포를
    받으면 소수의 파일만 보고도 개요가 완성된 것처럼 나오는데,
    화면에 그렇게 뜨면 사용자는 레포 전체가 분석된 줄 알고 결과를 신뢰한다.
    인덱싱 시점에 저장해두지 않고 여기서 다시 세는 이유는, 인덱싱 이후에
    파일이 늘어나도 화면이 현재 상태를 말하게 하기 위해서다.
    어차피 모듈 이름 집합을 만들려고 순회하므로 추가 비용도 없다.

    Args:
        root (str): 레포 루트 경로.
        chunks (list[Chunk]): 인덱싱된 청크 목록. L1과 L2가 섞여 있어도 된다.
        exclude_dirs (set[str] | None): 인덱싱 때와 같은 제외 목록.
            내부 모듈 이름 집합을 만들 때 같은 파일 목록을 써야
            내부/외부 판정이 인덱스와 어긋나지 않는다.

    Returns:
        RepoOverview: 조립된 개요.
    """
    root_path = Path(root).resolve()

    l1 = [c for c in chunks if c.kind == "file"]
    # 문서 청크는 코드 심볼이 아니다. != "file"로만 거르면 README 절이
    # 함수·클래스 수에 섞여 규모 통계가 틀어진다.
    l2 = [c for c in chunks if c.kind not in ("file", "doc", "config")]

    # 수집 결과를 세 곳에서 쓴다. 모듈 이름 집합, 파일 수, 제외 보고다.
    # 청크가 있는 파일만 세면 빈 __init__.py 같은 파일이 빠져,
    # whyd index가 말하는 수집 파일 수와 리포트의 규모가 어긋난다.
    collected = collect_source_files(root, exclude_dirs)
    files = collected.files
    module_map = build_module_map(files, root)
    # 판별용 이름 집합은 대응표의 키와 다르다. 대응표는 간선의 도착지를
    # 정해야 해서 이름이 겹치는 파일을 빼지만, 판별은 그 이름이 레포 안에
    # 있다는 것만 알면 된다. 패키지 이름도 파일 하나를 가리키지 않아
    # 판별에만 더한다.
    module_names = build_module_names(files, root) | build_package_names(files)
    external, stdlib, internal_count = split_dependencies(l1 or l2, module_names)

    # 청크가 생긴 파일을 그대로 쓴다. README나 pyproject는 수집 대상이 아니면서
    # 별도 경로로 인덱싱되므로, 이름을 직접 적으면 README.rst 같은 변형에서 틀린다.
    indexed = {c.file for c in chunks}
    skipped = group_by_extension(collected.skipped_other, root, indexed)

    return RepoOverview(
        root=str(root_path),
        name=root_path.name,
        file_count=len(files),
        total_lines=sum(c.end_line for c in l1),
        symbol_count=len(l2),
        documented_count=sum(1 for c in l2 if c.summary),
        external_deps=external,
        stdlib_deps=stdlib,
        internal_import_count=internal_count,
        import_edges=build_import_edges(l1, module_map),
        file_map=build_file_map(l1, l2),
        entry_points=find_script_entries(root_path) + find_code_entries(l2, root_path),
        readme=read_readme(root_path),
        skipped_note=format_skipped(skipped),
        skipped_large=[to_relative(p, root) for p in collected.skipped_by_size],
    )



def build_overview_prompt(overview: RepoOverview) -> str:
    """레포 요약 생성에 넘길 재료를 조립한다.

    파일 지도를 재료의 중심에 둔다.
    개별 함수 요약까지 넣으면 재료가 수십 배로 늘어나는데,
    "이 프로젝트가 무엇인가"에 답하는 데는 파일 단위 역할이면 충분하다.

    제외 내역은 넣지 않는다. 요약이 답해야 할 것은 "이 프로젝트가 무엇인가"이고,
    분석 범위는 그 답의 재료가 아니라 화면에서 따로 밝힐 사실이다.
    재료에 섞으면 모델이 "자바 부분은 알 수 없다" 같은 유보를 요약문에 끼워 넣어
    정작 물어본 것에 대한 답이 흐려진다.

    Args:
        overview (RepoOverview): 조립된 개요.

    Returns:
        str: 프롬프트에 넣을 재료 텍스트.
    """
    lines = [
        f"프로젝트 이름: {overview.name}",
        f"규모: 파일 {overview.file_count}개, 심볼 {overview.symbol_count}개, "
        f"{overview.total_lines}줄",
        "",
        f"서드파티 의존성: {', '.join(overview.external_deps) or '없음'}",
        "",
        "진입점:",
    ]

    for entry in overview.entry_points:
        mark = "확정" if entry.confirmed else "추정"
        lines.append(f"  [{mark}] {entry.target} — {entry.evidence}")
    if not overview.entry_points:
        lines.append("  찾지 못함")

    lines += ["", "파일별 역할:"]
    for file_path, summary in overview.file_map:
        lines.append(f"  {file_path}")
        lines.append(f"    {summary}")

    if overview.readme:
        lines += ["", "README (앞부분):", overview.readme[:README_LIMIT]]
    else:
        lines += ["", "README: 없음"]

    return "\n".join(lines)


def summarize_repo(overview: RepoOverview, llm: LLMClient) -> str:
    """레포 개요를 문장으로 요약한다.

    조립만으로는 만들 수 없는 유일한 항목이다.
    파일별 역할이 나열되어 있어도 "그래서 이게 무엇인가"는 종합해야 나온다.

    Args:
        overview (RepoOverview): 조립된 개요.
        llm (LLMClient): 요약에 사용할 LLM 클라이언트.

    Returns:
        str: [한 줄]과 [개요] 절이 담긴 요약 텍스트.
    """

    return llm.complete(
        load_prompt("summarize_repo"),
        build_overview_prompt(overview),
        max_tokens=1000,
    )
