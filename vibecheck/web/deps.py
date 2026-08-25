"""웹 라우터가 공유하는 진입 관문.

경로 정규화와 예외 번역을 한 곳에 모은 이유는 두 가지다. 라우터마다
흩어지면 새 화면을 붙일 때 누락이 생기고, services 층이 HTTP 상태 코드를
알게 된다. services는 계속 HTTP를 모르는 상태로 두고 번역은 web 안에서만
일어나게 한다. CLI가 같은 예외를 화면 출력으로 바꾸던 자리의 대응물이다.
"""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Query

from vibecheck.services.index_access import (
    IndexEmpty,
    IndexNotFound,
    open_index,
)


def resolve_repo_path(
    path: Annotated[str, Query(description="대상 레포 경로")],
) -> Path:
    """입력 경로를 DB에 저장된 것과 같은 실체 경로로 맞춘다.

    CLI에서는 셸이 `~`를 풀고 심볼릭 링크도 해소된 경로가 넘어왔지만,
    웹에서는 폼에 친 문자열이 그대로 들어온다. macOS의 `/tmp`는 실제로
    `/private/tmp`라서 정규화하지 않으면 `records.db`의 `repos.path`와
    어긋나 인덱스가 있는데도 못 찾는다.

    Args:
        path: 질의 문자열로 받은 레포 경로. `~` 포함 가능.

    Returns:
        존재가 확인된 절대 경로.

    Raises:
        HTTPException: 경로가 없거나 디렉터리가 아니면 400.
    """
    resolved = Path(path).expanduser().resolve()

    if not resolved.exists():
        raise HTTPException(status_code=400, detail=f"경로가 없습니다: {resolved}")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"디렉터리가 아닙니다: {resolved}")

    return resolved


RepoPath = Annotated[Path, Depends(resolve_repo_path)]


def get_index(repo: RepoPath) -> tuple:
    """인덱스를 열고 실패를 HTTP 상태 코드로 번역한다.

    반환값을 해석하지 않고 그대로 넘기는 것은 의도적이다. `open_index()`의
    튜플 구성이 바뀌어도 이 함수는 고칠 필요가 없어야 한다. 여기의 책임은
    "여는 데 실패했을 때 무엇을 응답할지"뿐이다.

    인덱스 없음과 인덱스 빈 상태를 다른 코드로 나눈 이유는 사용자가 할 일이
    다르기 때문이다. 전자는 `whyd index`를 돌려야 하고, 후자는 인덱싱은
    됐으나 수집된 청크가 없는 상태라 대상·제외 설정을 의심해야 한다.

    Args:
        repo: `resolve_repo_path`가 정규화한 레포 경로.

    Returns:
        `open_index()`의 반환값을 그대로.

    Raises:
        HTTPException: 인덱스가 없으면 404, 비어 있으면 409.
    """
    try:
        return open_index(repo)
    except IndexNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IndexEmpty as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


Index = Annotated[tuple, Depends(get_index)]