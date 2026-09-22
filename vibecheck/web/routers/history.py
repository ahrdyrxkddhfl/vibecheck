"""연습 기록 화면이 쓰는 엔드포인트.

인덱스를 열지 않는다. 기록은 records.db에 따로 있고, 인덱스가 없거나 낡아도
지난 연습은 볼 수 있어야 한다. LLM도 부르지 않으므로 GET으로 둔다.
"""

from fastapi import APIRouter, Query

from vibecheck.services.history import load_history
from vibecheck.web.deps import RepoPath

router = APIRouter()


@router.get("/history")
def get_history(
    repo: RepoPath,
    limit: int = Query(20, ge=1, le=200, description="가져올 최근 답변 수"),
) -> dict:
    """연습 기록과 주장 판정 누적을 반환한다.

    Args:
        repo: 정규화된 레포 경로.
        limit: 가져올 최근 답변 수.

    Returns:
        dict: services.history.load_history의 결과.
    """
    return load_history(repo, limit)
