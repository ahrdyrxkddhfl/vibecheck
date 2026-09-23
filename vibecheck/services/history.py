"""연습 기록을 CLI와 웹이 같은 말로 보여주게 조립한다.

기록을 꺼내는 쿼리는 store/records.py에 있고, 여기서는 그것을 사람이 읽을 모양으로
묶는다. 특히 주장 판정 누적을 세 숫자로 합치고 경향을 한 줄로 짚는 계산은 CLI
(whyd history) 안에 있었는데, 웹 화면을 붙이면서 이리로 옮겼다. 두 곳에 따로 두면
한쪽 문장만 고쳤을 때 같은 기록을 CLI와 웹이 다르게 말한다.

기록은 두 가지다. 채점 기록은 주장 판정이 붙어 누적과 경향을 계산하고,
질문 기록은 질문과 그때 받은 답을 남길 뿐 누적에 들어가지 않는다.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from vibecheck.store.records import (
    claims_for,
    connect,
    count_asks,
    db_path,
    get_repo_id,
    list_answers,
    list_asks,
    repeated_assertions,
    verdict_summary,
)

TENDENCY_MIN = 3
"""경향을 짚기 시작할 확인불가·모순 주장 수. 두어 개로 습관을 말하면 성급하다."""

ASSERT_WARN = 0.7
"""근거 없는 주장 중 단정한 비율이 이 이상이면 경고한다."""

ASSERT_GOOD = 0.3
"""근거 없는 주장 중 단정한 비율이 이 이하이면 습관이 자리잡았다고 말한다."""

RISKY_VERDICTS = ("unverifiable", "contradicted")
"""근거가 없거나 어긋난 판정. 유보하지 않았으면 면접에서 무너지는 주장이다."""


@dataclass
class Tally:
    """주장 판정 누적.

    Attributes:
        confirmed (int): 코드로 확인된 주장 수. 유보 여부와 상관없다.
        asserted (int): 근거가 없거나 어긋나는데 단정한 주장 수.
        hedged (int): 근거가 없거나 어긋나는데 그렇다고 밝힌 주장 수.
        note (str | None): 경향을 짚는 한 줄. 짚을 만큼 쌓이지 않았으면 None.
        tone (str | None): note의 성격. "warn"이면 고칠 습관, "good"이면 자리잡은 습관.
    """

    confirmed: int
    asserted: int
    hedged: int
    note: str | None = None
    tone: str | None = None


def tally(summary: dict) -> Tally:
    """판정별 개수를 세 숫자와 경향 한 줄로 묶는다.

    숫자만 보면 자기 경향을 알아채지 못한다. 근거 없는 주장 중 단정한 비율로 한 줄
    짚는다. 확인된 주장은 비율에서 뺀다. 이 도구가 보려는 것은 모르는 것을 어떻게
    말하느냐이지, 아는 것을 얼마나 많이 말하느냐가 아니다.

    Args:
        summary (dict): records.verdict_summary의 결과. 키는 "verdict:hedged".

    Returns:
        Tally: 세 숫자와 경향 한 줄.
    """
    confirmed = summary.get("confirmed:0", 0) + summary.get("confirmed:1", 0)
    asserted = summary.get("unverifiable:0", 0) + summary.get("contradicted:0", 0)
    hedged = summary.get("unverifiable:1", 0) + summary.get("contradicted:1", 0)

    result = Tally(confirmed=confirmed, asserted=asserted, hedged=hedged)

    unverified = asserted + hedged
    if unverified >= TENDENCY_MIN:
        rate = asserted / unverified
        if rate >= ASSERT_WARN:
            result.note = (
                "코드에 근거가 없는 내용을 대부분 단정하고 있습니다. "
                "면접에서 되물으면 무너지는 지점입니다."
            )
            result.tone = "warn"
        elif rate <= ASSERT_GOOD:
            result.note = "확인할 수 없는 것을 밝히는 습관이 자리잡았습니다."
            result.tone = "good"

    return result


def load_history(repo: Path, limit: int = 20) -> dict:
    """레포의 연습 기록을 화면에 보여줄 모양으로 꺼낸다.

    답변마다 그때의 주장별 판정을 붙인다. 채점 직후 화면과 같은 모양이라,
    웹은 채점 결과를 그리던 코드로 지난 기록도 그린다.

    질문 기록도 질문 직후 화면(/api/ask)과 같은 모양으로 꺼낸다. 근거는
    저장할 때 JSON으로 넣었으므로 여기서 푼다.

    기록 파일이 없으면 만들지 않고 빈 결과를 돌려준다. 여는 것만으로 파일을
    만들면(records.connect) 경로만 친 폴더에 .vibecheck가 생긴다.

    Args:
        repo (Path): 대상 레포 루트.
        limit (int): 가져올 최근 답변 수. 질문 기록도 같은 수만큼 가져온다.

    Returns:
        dict: answers(최신순, 주장 포함), tally(누적), risky(단정한 주장),
            answer_count(전체 답변 수), asks(최신순 질문 기록),
            ask_count(전체 질문 수).
    """
    empty = {
        "answers": [],
        "tally": asdict(tally({})),
        "risky": [],
        "answer_count": 0,
        "asks": [],
        "ask_count": 0,
    }
    if not db_path(repo).exists():
        return empty

    conn = connect(repo)
    try:
        repo_id = get_repo_id(conn, repo)
        rows = list_answers(conn, repo_id, limit)
        claims = claims_for(conn, [r["id"] for r in rows])
        summary = verdict_summary(conn, repo_id)
        risky = repeated_assertions(conn, repo_id)
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM answers WHERE repo_id = ?", (repo_id,)
        ).fetchone()["n"]
        ask_rows = list_asks(conn, repo_id, limit)
        ask_count = count_asks(conn, repo_id)
    finally:
        conn.close()

    answers = []
    for r in rows:
        mine = [
            {
                "claim": c["claim"],
                "verdict": c["verdict"],
                "hedged": bool(c["hedged"]),
                "evidence": c["evidence"],
                "note": c["note"],
            }
            for c in claims.get(r["id"], [])
        ]
        answers.append(
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "question": r["question_text"],
                "body": r["body"],
                "specificity": r["specificity"],
                "calibration": r["calibration"],
                "groundedness": r["groundedness"],
                "total": r["specificity"] + r["calibration"] + r["groundedness"],
                "verdict_line": r["verdict_line"],
                "revision": r["revision"],
                "claims": mine,
                "risky_count": sum(
                    1 for c in mine
                    if c["verdict"] in RISKY_VERDICTS and not c["hedged"]
                ),
            }
        )

    return {
        "answers": answers,
        "tally": asdict(tally(summary)),
        "risky": [
            {"claim": r["claim"], "verdict": r["verdict"], "created_at": r["created_at"]}
            for r in risky
        ],
        "answer_count": count,
        "asks": [
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "question": r["question"],
                "answer": r["answer"],
                "sources": json.loads(r["sources"]),
                "parent_id": r["parent_id"],
                "parent_question": r["parent_question"],
            }
            for r in ask_rows
        ],
        "ask_count": ask_count,
    }
