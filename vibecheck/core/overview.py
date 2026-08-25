"""레포 전체를 조망하는 개요(L0)를 조립한다.

L2(함수·클래스)와 L1(파일)만으로는 답할 수 없는 질문이 있다.
"이 프로젝트는 무엇을 하는가"의 답은 어느 파일 하나에 있지 않고 전체에 흩어져 있다.
실험 A에서 이 질문이 세 조건 모두 정답 청크를 찾지 못한 것이 그 증거다.

이 모듈은 LLM을 호출하지 않고 조립만 한다.
통계, 의존성 목록, 파일 지도, 진입점은 모두 이미 인덱싱된 정보에서 계산되므로
LLM에 물을 이유가 없고, 조립은 실행할 때마다 같은 결과를 낸다.
문장으로 된 요약은 별도 모듈에서 LLM으로 생성한다.
"""

import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from vibecheck.core.collector import build_module_names, collect_files, is_internal_import
from vibecheck.prompts import load_prompt
from vibecheck.llm.base import LLMClient
from vibecheck.models import Chunk

ENTRY_FILENAMES = {"__main__.py", "main.py", "cli.py", "app.py", "manage.py"}
"""진입점일 가능성이 높은 파일 이름.

관례일 뿐 보장이 아니므로 추정 근거로만 쓰고, 확정된 근거와 구분해 표시한다.
"""

STDLIB_NAMES = sys.stdlib_module_names
"""표준 라이브러리 모듈 이름 집합.

하드코딩하지 않고 실행 중인 파이썬에서 가져온다.
버전마다 목록이 달라지므로 직접 관리하면 반드시 어긋난다.
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
            청크가 생긴 파일이 아니라 collect_files가 수집한 파일 전부다.
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
    file_map: list[tuple[str, str]] = field(default_factory=list)
    entry_points: list[EntryPoint] = field(default_factory=list)
    readme: str = ""



def split_dependencies(
    chunks: list[Chunk], module_names: set[str]
) -> tuple[list[str], list[str], int]:
    """import 목록을 서드파티, 표준 라이브러리, 내부 모듈로 가른다.

    표준 라이브러리를 따로 빼는 이유는 리포트에서 답해야 할 질문이
    "왜 이 라이브러리를 골랐는가"이기 때문이다.
    os나 json을 왜 썼는지 묻는 사람은 없다. httpx와 pydantic을 골랐다는 것이 정보이고,
    표준 라이브러리 열 몇 개가 목록에 섞이면 그 정보가 묻힌다.

    외부 라이브러리는 최상위 이름만 남긴다.
    httpx.AsyncClient와 httpx.RequestError는 같은 라이브러리이므로
    따로 세면 의존성이 실제보다 많아 보인다.

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
        for imp in chunk.imports:
            if is_internal_import(imp, module_names):
                internal_count += 1
                continue

            top = imp.split(".")[0]
            if top in STDLIB_NAMES:
                stdlib.add(top)
            else:
                third_party.add(top)

    return sorted(third_party), sorted(stdlib), internal_count


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

    __main__ 블록은 tree-sitter 청킹 대상이 아니라 청크에 남지 않으므로
    파일 본문을 직접 확인한다.

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

        if '__name__ == "__main__"' in source or "__name__ == '__main__'" in source:
            found[file_path] = EntryPoint(
                target=file_path,
                evidence="__main__ 블록이 있어 직접 실행 가능",
            )
        elif name in ENTRY_FILENAMES:
            found[file_path] = EntryPoint(
                target=file_path,
                evidence=f"파일 이름이 {name}",
            )

    # main 함수가 있으면 근거를 보강한다. 이름만 맞은 경우보다 확실하다.
    for chunk in chunks:
        if chunk.symbol == "main" and chunk.file in found:
            found[chunk.file].evidence += ", main() 함수 정의됨"

    return list(found.values())


def read_readme(root: Path) -> str:
    """레포 루트의 README 본문을 읽는다.

    Args:
        root (Path): 레포 루트.

    Returns:
        str: README 본문. 없으면 빈 문자열.
    """
    for path in sorted(root.glob("README*")):
        if path.is_file():
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
    l2 = [c for c in chunks if c.kind != "file"]

    # 수집 결과를 두 곳에서 쓴다. 모듈 이름 집합과 파일 수 계산이다.
    # 청크가 있는 파일만 세면 빈 __init__.py 같은 파일이 빠져,
    # whyd index가 말하는 수집 파일 수와 리포트의 규모가 어긋난다.
    files = collect_files(root, exclude_dirs)
    module_names = build_module_names(files, root)
    external, stdlib, internal_count = split_dependencies(l1 or l2, module_names)
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
        file_map=build_file_map(l1, l2),
        entry_points=find_script_entries(root_path) + find_code_entries(l2, root_path),
        readme=read_readme(root_path),
    )



def build_overview_prompt(overview: RepoOverview) -> str:
    """레포 요약 생성에 넘길 재료를 조립한다.

    파일 지도를 재료의 중심에 둔다.
    개별 함수 요약까지 넣으면 재료가 수십 배로 늘어나는데,
    "이 프로젝트가 무엇인가"에 답하는 데는 파일 단위 역할이면 충분하다.

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