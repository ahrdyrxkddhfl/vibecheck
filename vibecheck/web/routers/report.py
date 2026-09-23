"""리포트 화면이 쓰는 엔드포인트.

개요와 요약을 나눈 것은 과금 때문이다. 개요 조립은 순수 계산이라
새로고침을 반복해도 공짜지만, 요약은 LLM을 부른다. 웹에서는 탭 두 개나
자동 재요청만으로도 GET이 여러 번 나가므로, 돈이 드는 일은 사용자가
명시적으로 누르는 POST에만 둔다.
"""

import logging
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from vibecheck.core.collector import collect_files
from vibecheck.core.languages import LANGUAGES
from vibecheck.core.overview import build_overview
from vibecheck.core.quirks import find_quirks, group_quirks
from vibecheck.llm.anthropic import ANSWER_MODEL, SUMMARY_MODEL, AnthropicClient
from vibecheck.services.interview import STAGE_ORDER, question_sets
from vibecheck.services.practice import grade
from vibecheck.services.relations import file_relations
from vibecheck.services.report import build_report, report_path
from vibecheck.store.records import (
    answered_questions,
    connect,
    db_path,
    get_repo_id,
    save_answer,
)
from vibecheck.store.vector import VectorStore
from vibecheck.web.deps import Index, RepoPath

router = APIRouter()

logger = logging.getLogger(__name__)


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
        dict: 개요 필드와 `stale_count`, `languages`, `index_meta`.
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

    # 제외 문구 뒤에 "무엇만 분석하는지"를 붙이는 재료다. 화면에 언어 이름을
    # 적어두면 언어를 더할 때 화면만 옛말을 하게 된다.
    data["languages"] = [spec.label for spec in LANGUAGES]

    # 언제 어떤 조건으로 인덱싱됐는지를 화면에서 보여줄 수 있어야 한다.
    # 숫자가 이상할 때 "인덱스가 오래됐나"를 먼저 의심할 근거가 된다.
    data["index_meta"] = meta

    return data

def answered_texts(repo: Path) -> set[str]:
    """레포에서 채점받은 적 있는 질문 문장을 꺼낸다.

    기록 파일이 없으면 만들지 않고 빈 집합을 돌려준다. 여는 것만으로 파일을
    만들면 경로만 친 폴더에 .vibecheck가 생긴다(services.history와 같은 이유).

    Args:
        repo (Path): 정규화된 레포 경로.

    Returns:
        set[str]: 질문 문장 집합.
    """
    if not db_path(repo).exists():
        return set()
    conn = connect(repo)
    try:
        return answered_questions(conn, get_repo_id(conn, repo))
    finally:
        conn.close()


@router.get("/interview")
def get_interview(
    repo: RepoPath,
    index: Index,
    set_no: int = Query(1, ge=1, alias="set", description="세트 번호. 1부터 센다."),
) -> dict:
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

    질문은 세트로 나뉜다(services.interview.question_sets). 첫 세트는 예전 질문
    그대로라 whyd practice의 번호와 맞는다. 번호는 세트를 넘어 이어 매겨, 어느
    세트의 질문이든 번호가 겹치지 않는다.

    채점받은 적 있는 질문에는 `answered`를 싣는다. 세트를 다 풀었는지 화면이
    알려주고 다음 세트로 넘어가게 하는 재료다.

    Args:
        repo: 정규화된 레포 경로.
        index: `open_index()`의 반환값.
        set_no: 보여줄 세트 번호. 주소에서는 `?set=`로 받는다.

    Returns:
        dict: `stages`(단계별 질문 묶음), `total`(이 세트의 질문 수), `set`,
            `set_count`, `answered_count`(이 세트에서 답한 질문 수), `stale_count`.

    Raises:
        HTTPException: 없는 세트 번호면 404.
    """
    chunks, _chroma_dir, stale, meta = index

    excludes = set(meta.get("exclude_dirs") or ()) or None
    overview = build_overview(str(repo), chunks, excludes)
    quirk_groups = group_quirks(find_quirks(str(repo), collect_files(str(repo), excludes)))

    sets = question_sets(overview, chunks, repo, quirk_groups)
    if set_no > len(sets):
        raise HTTPException(
            status_code=404, detail=f"세트는 1부터 {len(sets)}까지 있습니다."
        )
    questions = sets[set_no - 1]
    answered = answered_texts(repo)

    stages = []
    number = sum(len(s) for s in sets[: set_no - 1])

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
                    "answered": question.text in answered,
                }
            )

        stages.append({"stage": stage, "questions": items})

    return {
        "stages": stages,
        "total": len(questions),
        "set": set_no,
        "set_count": len(sets),
        "answered_count": sum(1 for q in questions if q.text in answered),
        "stale_count": stale,
    }

@router.get("/relations")
def get_relations(repo: RepoPath, index: Index, file: str) -> dict:
    """파일 하나를 가운데 둔 호출 관계를 반환한다. LLM을 부르지 않는다.

    관계도 화면이 파일을 누를 때마다 부른다. 레포 전체 관계를 한 번에
    내보내지 않는 이유는 크기다. 이 레포는 심볼 145개라 작지만 이 도구는
    남의 레포에 쓰는 것이고, 한 화면에 그리는 것은 어차피 한 파일의 이웃뿐이다.

    인덱싱 시점의 관계라는 것을 잊으면 안 된다. 인덱싱 뒤에 코드를 고치면
    새로 생긴 호출은 여기 없다. 그래서 개요처럼 `stale_count`를 싣는다.

    Java처럼 호출 대신 타입 참조로 잇는 언어는 파일을 읽어야 해서 레포 경로를
    함께 넘긴다. 그 연결은 인덱싱 시점이 아니라 지금 디스크의 코드 기준이다.

    Args:
        repo: 정규화된 레포 경로.
        index: `open_index()`의 반환값.
        file: 가운데 둘 파일의 레포 기준 상대 경로.

    Returns:
        dict: `file_relations`의 결과에 `stale_count`를 더한 것.

    Raises:
        HTTPException: 그 파일에 함수나 클래스가 없으면 404.
    """
    chunks, _chroma_dir, stale, _meta = index

    data = file_relations(chunks, file, repo)
    if data is None:
        # 경로 오타와 "정의가 없는 파일"(__init__.py 등)을 구분하지 않는다.
        # 어느 쪽이든 그릴 것이 없다는 점은 같고, 사용자가 할 일도 같다.
        # 다만 건너뛴 청크가 있으면 그쪽이 더 흔한 원인이다. 인덱싱 뒤 고친
        # 파일은 청크가 통째로 빠지므로, 그 파일을 누르면 여기로 온다.
        detail = f"{file}에서 함수나 클래스를 찾지 못했습니다."
        if stale:
            detail += (
                f" 인덱싱 뒤 바뀐 파일이라 건너뛰었을 수 있습니다"
                f"(건너뛴 청크 {stale}개). whyd index로 다시 인덱싱하세요."
            )
        else:
            detail += " 경로가 맞는지, 정의가 없는 파일은 아닌지 확인하세요."
        raise HTTPException(status_code=404, detail=detail)

    data["stale_count"] = stale
    return data

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

    저장이 실패해도 채점 결과는 보낸다. 응답은 이 함수가 끝나야 나가므로,
    저장에서 난 예외를 그대로 두면 이미 요금을 낸 채점까지 500으로 버려진다.
    예전에는 "화면에 뿌릴 것을 먼저 만들고 저장은 그 뒤에" 두는 것으로 이것을
    지킨다고 적었지만, 순서만으로는 응답이 나가지 않는다. 대신 `saved`를 거짓으로
    실어 화면이 기록에 남지 않았다고 밝히게 한다. 질문 저장(ask.post_ask)과 같다.

    Args:
        repo: 정규화된 레포 경로.
        index: `open_index()`의 반환값.
        req: 질문과 답변.

    Returns:
        dict: 점수 세 축과 합계, 주장별 판정, 총평, 채점 근거,
            `saved`(기록에 남았는지).
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

    data["saved"] = False
    try:
        conn = connect(repo)
        try:
            save_answer(conn, get_repo_id(conn, repo), feedback)
            data["saved"] = True
        finally:
            conn.close()
    except sqlite3.Error:
        logger.exception("채점 기록을 저장하지 못했습니다: %s", repo)

    return data


@router.get("/report")
def get_report(repo: RepoPath) -> dict:
    """저장된 리포트를 돌려준다. LLM을 부르지 않는다.

    리포트 탭을 열 때마다 부른다. 만들지는 않는다. 만드는 일은 요금이 나가므로
    사용자가 버튼을 눌러야만 나가는 POST에 둔다.

    인덱스를 열지 않는다. 파일만 읽으므로, 인덱스가 낡거나 없어도 전에 만든
    리포트는 볼 수 있다.

    Args:
        repo: 정규화된 레포 경로.

    Returns:
        dict: `markdown`(리포트 원문, 없으면 None), `path`(파일 경로),
            `generated_at`(파일을 쓴 시각, 없으면 None).
    """
    path = report_path(repo)
    if not path.is_file():
        return {"markdown": None, "path": str(path), "generated_at": None}

    written = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return {
        "markdown": path.read_text(encoding="utf-8"),
        "path": str(path),
        "generated_at": written.isoformat(),
    }


@router.post("/report")
def post_report(repo: RepoPath, index: Index) -> dict:
    """리포트를 새로 만들어 파일에 저장하고 돌려준다. LLM을 부른다.

    whyd report와 같은 재료(개요, 특이 지점)로 같은 함수(build_report)를 불러,
    CLI와 웹의 리포트가 같은 모양이 되게 한다. 저장도 같은 파일에 한다.

    레포 요약 한 번에 요약 모델을 부른다. CLI와 같은 모델이다.

    저장이 실패해도 만든 리포트는 보낸다. 요금은 이미 나갔다. `saved`를 거짓으로
    실어 화면이 내려받아 보관하라고 알리게 한다. 채점, 질문 저장과 같은 방식이다.

    Args:
        repo: 정규화된 레포 경로.
        index: `open_index()`의 반환값.

    Returns:
        dict: `markdown`, `path`, `generated_at`, `saved`(파일에 저장했는지).
    """
    chunks, _chroma_dir, _stale, meta = index

    excludes = set(meta.get("exclude_dirs") or ()) or None
    overview = build_overview(str(repo), chunks, excludes)
    quirk_groups = group_quirks(find_quirks(str(repo), collect_files(str(repo), excludes)))
    text = build_report(overview, chunks, AnthropicClient(model=SUMMARY_MODEL), quirk_groups)

    path = report_path(repo)
    saved = False
    try:
        path.write_text(text, encoding="utf-8")
        saved = True
    except OSError:
        logger.exception("리포트를 저장하지 못했습니다: %s", path)

    return {
        "markdown": text,
        "path": str(path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "saved": saved,
    }
