"""패키지를 빌드하면 파이썬이 아닌 파일도 함께 들어가는지 지킨다.

setuptools는 package-data에 적은 파일만 패키지에 넣는다. 적지 않으면 편집
모드(pip install -e .)에서는 레포를 직접 읽어 티가 나지 않다가, pip install .이나
PyPI로 설치하면 빠진다. 2026-09-23에 휠을 빌드해 보니 프롬프트 다섯 개와 웹 화면이
모두 빠져, 설치한 곳에서 모든 LLM 호출과 whyd serve가 깨지는 상태였다.

빌드를 돌리지 않고 설정과 파일 목록을 대조한다. 새 프롬프트나 화면 파일을 더하고
설정을 잊으면 여기서 걸린다.
"""

import fnmatch
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "vibecheck"


def is_data_file(path: Path) -> bool:
    """패키지에 함께 들어가야 할 데이터 파일인지 가른다.

    파이썬 소스와 컴파일 캐시, 숨김 파일(.DS_Store 등)은 뺀다.

    Args:
        path (Path): vibecheck 아래의 파일.

    Returns:
        bool: 데이터 파일이면 True.
    """
    if not path.is_file():
        return False
    if path.suffix in {".py", ".pyc"} or "__pycache__" in path.parts:
        return False
    return not any(part.startswith(".") for part in path.relative_to(PACKAGE).parts)


def is_covered(path: Path, rules: dict[str, list[str]]) -> bool:
    """package-data 규칙 중 하나가 이 파일을 담는지 본다.

    Args:
        path (Path): 데이터 파일.
        rules (dict[str, list[str]]): 패키지 이름 -> 그 패키지 기준 파일 무늬 목록.

    Returns:
        bool: 담는 규칙이 있으면 True.
    """
    for package, patterns in rules.items():
        base = ROOT / Path(*package.split("."))
        try:
            relative = path.relative_to(base).as_posix()
        except ValueError:
            continue
        if any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
            return True
    return False


def test_every_data_file_is_packaged():
    """vibecheck 아래의 데이터 파일이 전부 package-data 규칙에 걸린다."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    rules = config["tool"]["setuptools"]["package-data"]

    data_files = [p for p in PACKAGE.rglob("*") if is_data_file(p)]
    missing = [p.relative_to(ROOT).as_posix() for p in data_files if not is_covered(p, rules)]

    assert data_files, "데이터 파일을 하나도 찾지 못했습니다. 경로가 바뀌었는지 확인하세요."
    assert missing == []
