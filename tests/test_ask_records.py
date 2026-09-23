"""질문 기록의 저장과 조회를 지킨다.

채점 기록과 테이블을 나눈 약속을 확인한다. 질문 기록은 누적(주장 판정)에
들어가지 않고, 채점 기록이 없어도 따로 꺼내진다. 질문 기록 테이블이 생기기 전에
만든 records.db를 열어도 테이블이 새로 생겨야 한다.
"""

import sqlite3

from vibecheck.services.history import load_history
from vibecheck.store.records import (
    connect,
    count_asks,
    db_path,
    get_repo_id,
    list_asks,
    save_ask,
)

SOURCES = [
    {
        "file": "vibecheck/services/practice.py",
        "start_line": 218,
        "end_line": 259,
        "symbol": "grade",
    }
]


def test_save_and_list_asks_newest_first(tmp_path):
    """저장한 질문이 최신순으로 나오고, 근거는 JSON으로 저장된다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포로 쓴다.
    """
    conn = connect(tmp_path)
    repo_id = get_repo_id(conn, tmp_path)
    save_ask(conn, repo_id, "처음 질문", "첫 답", SOURCES)
    save_ask(conn, repo_id, "두 번째 질문", "둘째 답", [])

    rows = list_asks(conn, repo_id)

    assert [r["question"] for r in rows] == ["두 번째 질문", "처음 질문"]
    assert count_asks(conn, repo_id) == 2
    conn.close()


def test_load_history_returns_asks_apart_from_grading(tmp_path):
    """질문 기록은 따로 나오고, 채점 기록과 누적은 비어 있는 그대로다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포로 쓴다.
    """
    conn = connect(tmp_path)
    save_ask(conn, get_repo_id(conn, tmp_path), "채점은 어디서?", "## 답", SOURCES)
    conn.close()

    history = load_history(tmp_path)

    assert history["ask_count"] == 1
    assert history["asks"][0]["sources"] == SOURCES
    assert history["answers"] == []
    assert history["answer_count"] == 0
    assert history["tally"]["confirmed"] == 0


def test_load_history_without_db_has_empty_asks(tmp_path):
    """기록 파일이 없으면 만들지 않고 빈 질문 기록을 돌려준다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포로 쓴다.
    """
    history = load_history(tmp_path)

    assert history["asks"] == []
    assert history["ask_count"] == 0
    assert not db_path(tmp_path).exists()


def test_old_db_gets_asks_table_on_connect(tmp_path):
    """질문 기록 테이블이 없던 records.db도 열기만 하면 테이블이 생긴다.

    이미 기록이 쌓인 레포에서 옮겨 가는 과정이 따로 필요 없다는 약속이다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 레포로 쓴다.
    """
    path = db_path(tmp_path)
    path.parent.mkdir(parents=True)
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE repos (id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, "
        "created_at TEXT NOT NULL)"
    )
    old.commit()
    old.close()

    conn = connect(tmp_path)
    assert count_asks(conn, get_repo_id(conn, tmp_path)) == 0
    conn.close()
