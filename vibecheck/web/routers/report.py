"""리포트 화면이 쓰는 엔드포인트.

개요와 요약을 나눈 것은 과금 때문이다. 개요 조립은 순수 계산이라
새로고침을 반복해도 공짜지만, 요약은 LLM을 부른다. 웹에서는 탭 두 개나
자동 재요청만으로도 GET이 여러 번 나가므로, 돈이 드는 일은 사용자가
명시적으로 누르는 POST에만 둔다.
"""

from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel, Field

from vibecheck.core.collector import collect_files
from vibecheck.core.overview import build_overview
from vibecheck.core.quirks import find_quirks, group_quirks
from vibecheck.llm.anthropic import AnthropicClient
from vibecheck.services.interview import STAGE_ORDER, build_questions
from vibecheck.services.practice import grade
from vibecheck.store.records import connect, get_repo_id, save_answer
from vibecheck.store.vector import VectorStore
from vibecheck.web.deps import Index, RepoPath

ANSWER_MODEL = "claude-sonnet-4-6"
"""채점에 쓰는 모델.

요약과 달리 답변을 코드와 대조하는 판단이 필요해 상위 모델을 쓴다.
CLI와 같은 값이어야 두 경로의 채점 결과가 비교 가능하다.
"""

router = APIRouter()



class PracticeRequest(BaseModel):
    """답변 채점 요청.

    빈 답변을 스키마에서 거르는 이유는 채점이 LLM 호출이기 때문이다.
    실수로 빈 폼을 보냈을 때 요금이 나가지 않아야 한다.

    Attributes:
        question: 답변한 질문. 검색 쿼리로도 쓰인다.
        answer: 사용자가 작성한 답변 원문.
    """

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


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


    # 튜플을 이름 있는 객체로 펴는 이유는 file_map과 같다.
    # 배열의 배열로 내보내면 프론트가 위치로 접근하게 되고,
    # 나중에 항목이 하나 늘면 조용히 어긋난다.
    data["import_edges"] = [
        {"from": src, "to": dst}
        for src, dst in data.get("import_edges", [])
    ]

    data["stale_count"] = stale

    # 언제 어떤 조건으로 인덱싱됐는지를 화면에서 보여줄 수 있어야 한다.
    # 숫자가 이상할 때 "인덱스가 오래됐나"를 먼저 의심할 근거가 된다.
    data["index_meta"] = meta

    return data

@router.get("/interview")
def get_interview(repo: RepoPath, index: Index) -> dict:
    """면접 예상질문을 JSON으로 반환한다. LLM을 부르지 않는다.

    질문 생성은 전부 조립이라 과금이 없다. 개요와 달리 GET으로 두어도
    새로고침이 요금으로 이어지지 않으므로, 이 화면은 POST로 나눌 이유가 없다.

    단계별로 묶어서 내보낸다. 면접은 개요에서 구조로, 구조에서 결정으로
    흘러가고 연습도 그 순서를 따라야 한다. 프론트가 stage 문자열로
    다시 묶게 하면 순서를 프론트가 정하게 되어 CLI 출력과 어긋난다.

    번호는 서버에서 매긴다. 나중에 답변을 저장할 때 이 번호로 질문을
    참조하는데, 프론트가 매기면 화면마다 다른 번호가 붙을 수 있다.
    CLI의 `whyd practice --question-no`와 같은 번호여야 한다.

    특이 지점은 디스크를 다시 읽어 계산한다. 인덱스에 담기지 않는
    정보이고, 레포 31개 파일 기준 0.02초라 캐싱할 만한 비용이 아니다.

    Args:
        repo: 정규화된 레포 경로.
        index: `open_index()`의 반환값.

    Returns:
        dict: `stages`(단계별 질문 묶음)와 `total`, `stale_count`.
    """
    chunks, _chroma_dir, stale, meta = index

    excludes = set(meta.get("exclude_dirs") or ()) or None
    overview = build_overview(str(repo), chunks, excludes)
    quirk_groups = group_quirks(find_quirks(str(repo), collect_files(str(repo), excludes)))

    questions = build_questions(overview, quirk_groups)

    stages = []
    number = 0

    for stage in STAGE_ORDER:
        staged = [q for q in questions if q.stage == stage]
        if not staged:
            continue

        items = []
        for question in staged:
            number += 1
            items.append(
                {
                    "no": number,
                    "text": question.text,
                    "answerable": question.answerable,
                    "can_say": question.can_say,
                    "risky": question.risky,
                }
            )

        stages.append({"stage": stage, "questions": items})

    return {
        "stages": stages,
        "total": number,
        "stale_count": stale,
    }

@router.post("/practice")
def post_practice(repo: RepoPath, index: Index, req: PracticeRequest) -> dict:
    """답변을 코드 근거와 대조해 채점한다. LLM을 부른다.

    이 라우터에서 유일하게 과금되는 자리라 POST로 둔다. 개요와 면접 질문은
    조립이라 새로고침이 공짜지만, 채점은 사용자가 버튼을 눌러야만 나가야 한다.

    채점 결과를 기록에 남긴다. 이 도구가 보여주려는 것은 개별 점수가 아니라
    "계속 단정하는 습관"이고, 그건 기록이 쌓여야 보인다. 웹 연습이 기록에
    빠지면 `whyd history`의 숫자가 실제 연습량과 어긋난다.

    `question_id` 없이 질문 문장만 저장한다. 번호로 연결하려면 웹이
    질문을 저장해야 하는데, `save_questions`는 기존 행을 지우고 다시 넣어
    id가 매번 바뀐다. 화면을 새로고침했을 뿐인데 과거 기록의 참조가
    끊기는 것보다, 연결을 포기하고 문장만 남기는 편이 안전하다.

    화면에 뿌릴 것을 먼저 만들고 저장은 그 뒤에 한다. 저장이 실패해도
    사용자는 이미 채점 결과를 받은 상태여야 한다.

    Args:
        repo: 정규화된 레포 경로.
        index: `open_index()`의 반환값.
        req: 질문과 답변.

    Returns:
        dict: 점수 세 축과 합계, 주장별 판정, 총평, 채점 근거.
    """
    chunks, chroma_dir, _stale, _meta = index

    feedback = grade(
        req.question,
        req.answer,
        chunks,
        VectorStore(persist_dir=chroma_dir),
        AnthropicClient(model=ANSWER_MODEL),
    )

    # 같은 '확인불가'라도 유보한 것은 감점 사유가 아니다.
    # verdict와 hedged를 나눠 저장한 이유가 여기서 드러난다.
    claims = [
        {
            "claim": c.claim,
            "verdict": c.verdict,
            "hedged": c.hedged,
            "evidence": c.evidence,
            "note": c.note,
        }
        for c in feedback.claims
    ]

    data = {
        "question": feedback.question,
        "specificity": feedback.specificity,
        "calibration": feedback.calibration,
        "groundedness": feedback.groundedness,
        "total": feedback.total,
        "claims": claims,
        "risky_count": len(feedback.risky_claims),
        "verdict_line": feedback.verdict_line,
        "revision": feedback.revision,
        "evidence_chunks": feedback.evidence_chunks,
    }

    conn = connect(repo)
    save_answer(conn, get_repo_id(conn, repo), feedback)
    conn.close()

    return data