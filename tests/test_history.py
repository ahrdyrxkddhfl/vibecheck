"""연습 기록을 CLI와 웹이 같은 모양으로 꺼내는지 확인한다."""

from types import SimpleNamespace

from vibecheck.services.history import load_history, tally
from vibecheck.store.records import connect, db_path, get_repo_id, save_answer


def feedback(claims: list[tuple[str, bool]]) -> SimpleNamespace:
    """저장에 필요한 속성만 가진 채점 결과를 만든다.

    Args:
        claims (list[tuple[str, bool]]): (판정, 유보 여부) 목록.

    Returns:
        SimpleNamespace: save_answer가 읽는 속성을 가진 객체.
    """
    return SimpleNamespace(
        question="질문",
        user_answer="답변",
        specificity=1,
        calibration=2,
        groundedness=1,
        verdict_line="총평",
        revision="수정",
        claims=[
            SimpleNamespace(claim=f"주장{i}", verdict=v, hedged=h, evidence=None, note="이유")
            for i, (v, h) in enumerate(claims)
        ],
    )


def test_경향은_근거_없는_주장이_쌓여야_짚는다():
    """근거 없는 주장이 셋 미만이면 비율과 상관없이 짚지 않는다."""
    assert tally({"unverifiable:0": 2}).note is None
    assert tally({"unverifiable:0": 3}).tone == "warn"
    assert tally({"unverifiable:1": 3, "confirmed:0": 10}).tone == "good"
    # 확인된 주장은 비율에서 빠진다.
    assert tally({"confirmed:0": 10, "unverifiable:0": 1}).note is None


def test_답변마다_그때의_주장과_단정_수를_붙인다(tmp_path):
    """채점 직후 화면과 같은 모양이어야 기록 화면이 같은 코드로 그린다."""
    conn = connect(tmp_path)
    repo_id = get_repo_id(conn, tmp_path)
    save_answer(conn, repo_id, feedback([("confirmed", False), ("unverifiable", False)]))
    save_answer(conn, repo_id, feedback([("unverifiable", True), ("contradicted", False)]))
    conn.close()

    d = load_history(tmp_path, limit=1)

    assert d["answer_count"] == 2
    assert len(d["answers"]) == 1
    latest = d["answers"][0]
    assert [c["verdict"] for c in latest["claims"]] == ["unverifiable", "contradicted"]
    assert latest["risky_count"] == 1
    assert latest["total"] == 4
    assert d["tally"]["confirmed"] == 1
    assert d["tally"]["asserted"] == 2
    assert d["tally"]["hedged"] == 1


def test_기록이_없는_폴더에_파일을_만들지_않는다(tmp_path):
    """경로만 열어봤는데 .vibecheck가 생기면 안 된다."""
    d = load_history(tmp_path)

    assert d["answers"] == []
    assert not db_path(tmp_path).exists()
