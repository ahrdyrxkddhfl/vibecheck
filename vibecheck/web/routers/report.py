"""리포트 화면이 쓰는 엔드포인트.

개요와 요약을 나눈 것은 과금 때문이다. 개요 조립은 순수 계산이라
새로고침을 반복해도 공짜지만, 요약은 LLM을 부른다. 웹에서는 탭 두 개나
자동 재요청만으로도 GET이 여러 번 나가므로, 돈이 드는 일은 사용자가
명시적으로 누르는 POST에만 둔다.
"""

from dataclasses import asdict

from fastapi import APIRouter

from vibecheck.core.overview import build_overview
from vibecheck.web.deps import Index, RepoPath

router = APIRouter()


@router.get("/overview")
def get_overview(repo: RepoPath, index: Index) -> dict:
    """레포 개요를 JSON으로 반환한다. LLM을 부르지 않는다.

    `readme` 본문을 응답에서 빼는 이유는 크기다. README 전체가 실리면
    개요 응답이 수십 KB가 되는데, 화면에서 둘을 같이 보여줄 이유가 없다.
    있는지 여부만 알면 "README가 있는데 반영 안 됐나"는 판단할 수 있다.

    `file_map`의 튜플을 이름 있는 객체로 펴는 것도 의도적이다. 배열의
    배열로 내보내면 프론트가 위치로 접근하게 되고, 나중에 항목이 하나
    늘면 조용히 어긋난다.

    `stale`을 응답에 싣는 이유는 CLI와 웹의 차이 때문이다. 터미널에서는
    경고 한 줄이 스크롤로 사라져도 방금 본 것이지만, 웹 화면은 계속
    남는다. 못 읽은 청크가 있다는 사실은 개요의 일부여야 한다.

    인덱싱 조건(`meta`)을 `build_overview`에 넘기는 이유는 CLI와 같은
    숫자를 내기 위해서다. 제외 목록 없이 계산하면 인덱싱에서 뺀 디렉터리가
    파일 수와 내부 참조 수에 섞여 들어와 리포트와 화면이 어긋난다.
    웹은 사용자에게 제외 목록을 물을 방법이 없으므로 장부 값이 유일한 근거다.

    Args:
        repo: 정규화된 레포 경로.
        index: `open_index()`의 반환값
            (청크, 벡터 저장소 경로, 건너뛴 수, 인덱싱 조건).

    Returns:
        dict: 개요 필드와 `stale_count`, `index_meta`.
    """
    chunks, _chroma_dir, stale, meta = index

    excludes = set(meta.get("exclude_dirs") or ()) or None
    overview = build_overview(str(repo), chunks, excludes)
    data = asdict(overview)

    readme = data.pop("readme", "")
    data["has_readme"] = bool(readme)

    data["file_map"] = [
        {"path": path, "overview": text}
        for path, text in data.get("file_map", [])
    ]

    data["stale_count"] = stale

    # 언제 어떤 조건으로 인덱싱됐는지를 화면에서 보여줄 수 있어야 한다.
    # 숫자가 이상할 때 "인덱스가 오래됐나"를 먼저 의심할 근거가 된다.
    data["index_meta"] = meta

    return data