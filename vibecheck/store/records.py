"""학습 기록을 SQLite에 저장한다.

기록은 대상 레포의 .vibecheck/records.db에 둔다.
인덱스와 같은 자리에 두는 이유는 레포마다 자기 기록을 갖게 하기 위해서다.
한 파일에 여러 레포 기록이 섞이면 학습 진단이 엉킨다.

ORM을 쓰지 않고 sqlite3를 직접 쓴다. 테이블이 다섯 개뿐이고 쿼리도 단순해
라이브러리를 얹으면 얻는 것보다 늘어나는 개념이 많다.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_FILENAME = "records.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY,
    repo_id     INTEGER NOT NULL REFERENCES repos(id),
    ordinal     INTEGER NOT NULL,
    stage       TEXT NOT NULL,
    text        TEXT NOT NULL,
    answerable  INTEGER NOT NULL,
    can_say     TEXT NOT NULL,
    risky       TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS answers (
    id            INTEGER PRIMARY KEY,
    repo_id       INTEGER NOT NULL REFERENCES repos(id),
    question_id   INTEGER REFERENCES questions(id),
    question_text TEXT NOT NULL,
    body          TEXT NOT NULL,
    specificity   INTEGER NOT NULL,
    calibration   INTEGER NOT NULL,
    groundedness  INTEGER NOT NULL,
    verdict_line  TEXT,
    revision      TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    id          INTEGER PRIMARY KEY,
    answer_id   INTEGER NOT NULL REFERENCES answers(id),
    claim       TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    hedged      INTEGER NOT NULL,
    evidence    TEXT,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS typing_runs (
    id           INTEGER PRIMARY KEY,
    repo_id      INTEGER NOT NULL REFERENCES repos(id),
    chunk_file   TEXT NOT NULL,
    chunk_symbol TEXT NOT NULL,
    line_no      INTEGER NOT NULL,
    typos        INTEGER NOT NULL,
    elapsed_ms   INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);
"""


def now() -> str:
    """현재 시각을 ISO 문자열로 반환한다.

    SQLite에 날짜 타입이 없어 텍스트로 저장한다.
    ISO 형식은 문자열 정렬이 곧 시간 정렬이라 별도 변환 없이 정렬할 수 있다.
    """
    return datetime.now(timezone.utc).isoformat()


def db_path(repo: Path) -> Path:
    """대상 레포의 기록 파일 경로를 만든다.

    Args:
        repo (Path): 대상 레포 루트.

    Returns:
        Path: records.db 경로.
    """
    return repo / ".vibecheck" / DB_FILENAME


def connect(repo: Path) -> sqlite3.Connection:
    """기록 DB에 연결하고 없으면 테이블을 만든다.

    CREATE TABLE IF NOT EXISTS를 매번 실행하는 이유는 첫 연결과 이후 연결을
    호출자가 구분하지 않아도 되게 하기 위해서다. 이미 있으면 아무 일도
    일어나지 않으므로 비용이 없다.

    row_factory를 설정해 조회 결과를 이름으로 접근할 수 있게 한다.
    row[3]보다 row["text"]가 나중에 칼럼 순서가 바뀌어도 안 깨진다.

    Args:
        repo (Path): 대상 레포 루트.

    Returns:
        sqlite3.Connection: 열린 연결.
    """
    path = db_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def get_repo_id(conn: sqlite3.Connection, repo: Path) -> int:
    """레포 행을 찾고 없으면 만들어 id를 반환한다.

    모든 기록이 repo_id를 갖는 이유는 나중에 여러 레포의 기록을 한곳에
    모아 볼 가능성 때문이다. 지금은 파일이 레포마다 따로 있어 항상 1이지만,
    통합 진단이 필요해지면 파일을 합치는 것만으로 끝난다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo (Path): 대상 레포 루트.

    Returns:
        int: repos 테이블의 id.
    """
    key = str(repo)

    row = conn.execute("SELECT id FROM repos WHERE path = ?", (key,)).fetchone()
    if row:
        return row["id"]

    cur = conn.execute(
        "INSERT INTO repos (path, created_at) VALUES (?, ?)", (key, now())
    )
    conn.commit()
    return cur.lastrowid


def save_questions(conn: sqlite3.Connection, repo_id: int, questions: list) -> None:
    """질문 목록을 저장한다. 기존 질문은 지운다.

    덮어쓰는 이유는 질문 번호가 항상 현재 코드 기준이어야 하기 때문이다.
    세대를 쌓으면 practice에서 3번을 고를 때 어느 세대의 3번인지 모호해진다.
    과거 채점 기록은 answers에 질문 문장이 복사돼 있어 여기서 지워도 남는다.

    can_say와 risky는 JSON 문자열로 넣는다. 질문을 꺼낼 때 늘 함께 나오는
    부속물이고 가로질러 세어볼 일이 없어 별도 테이블로 뺄 이유가 없다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.
        questions (list): Question 객체 목록.
    """
    conn.execute("DELETE FROM questions WHERE repo_id = ?", (repo_id,))

    stamp = now()
    for i, q in enumerate(questions, start=1):
        conn.execute(
            "INSERT INTO questions "
            "(repo_id, ordinal, stage, text, answerable, can_say, risky, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                repo_id,
                i,
                q.stage,
                q.text,
                1 if q.answerable else 0,
                json.dumps(q.can_say, ensure_ascii=False),
                json.dumps(q.risky, ensure_ascii=False),
                stamp,
            ),
        )

    conn.commit()


def get_question(conn: sqlite3.Connection, repo_id: int, ordinal: int):
    """번호로 질문 하나를 꺼낸다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.
        ordinal (int): 질문 번호 (1부터).

    Returns:
        sqlite3.Row | None: 질문 행. 없으면 None.
    """
    return conn.execute(
        "SELECT * FROM questions WHERE repo_id = ? AND ordinal = ?",
        (repo_id, ordinal),
    ).fetchone()


def count_questions(conn: sqlite3.Connection, repo_id: int) -> int:
    """저장된 질문 수를 센다.

    번호를 잘못 넣었을 때 "1에서 N 사이"라고 안내하기 위해 필요하다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.

    Returns:
        int: 질문 수.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM questions WHERE repo_id = ?", (repo_id,)
    ).fetchone()
    return row["n"]