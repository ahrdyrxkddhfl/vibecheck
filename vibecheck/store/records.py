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

CREATE TABLE IF NOT EXISTS asks (
    id          INTEGER PRIMARY KEY,
    repo_id     INTEGER NOT NULL REFERENCES repos(id),
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL,
    sources     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    parent_id   INTEGER REFERENCES asks(id)
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
    upgrade(conn)
    return conn


def upgrade(conn: sqlite3.Connection) -> None:
    """이전 버전이 만든 기록 파일에 새로 생긴 칸을 더한다.

    CREATE TABLE IF NOT EXISTS는 테이블이 이미 있으면 아무것도 하지 않아, 칸을
    더한 스키마로 바꿔도 이미 쌓인 records.db에는 반영되지 않는다. 그래서 열 때마다
    빠진 칸을 확인하고 더한다. 지우거나 옮기지 않고 더하기만 하므로 기존 기록은
    그대로 남는다.

    asks.parent_id: 이어지는 질문이 어느 질문에 이어졌는지. 질문 이어가기를 붙이며
    더했다. 기존 질문은 이 칸이 비어 첫 질문으로 읽힌다.

    같은 파일을 두 연결이 거의 동시에 처음 열면 둘 다 칸이 없다고 보고 더하려 한다.
    뒤에 온 쪽은 "이미 있다"로 실패하는데, 원하는 상태는 이미 된 것이라 넘어간다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(asks)")}
    if "parent_id" not in columns:
        try:
            conn.execute("ALTER TABLE asks ADD COLUMN parent_id INTEGER REFERENCES asks(id)")
            conn.commit()
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc):
                raise


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

def save_answer(
    conn: sqlite3.Connection,
    repo_id: int,
    feedback,
    question_id: int | None = None,
) -> int:
    """채점 결과를 저장한다.

    질문 문장을 question_id와 별개로 복사해 넣는다.
    interview를 다시 돌리면 질문이 새로 생성되어 과거 채점이 사라진 질문을
    가리키게 되는데, 그때도 무엇에 답한 기록인지는 남아야 한다.
    정규화보다 기록의 자족성이 중요한 자리다.

    주장은 별도 테이블에 행으로 푼다. JSON으로 뭉치면
    "이 사용자가 반복해서 단정하는 주제"를 SQL로 셀 수 없다.
    학습 진단이 보려는 것이 정확히 그것이다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.
        feedback (AnswerFeedback): 채점 결과.
        question_id (int | None): 저장된 질문의 id. 직접 입력한 질문이면 None.

    Returns:
        int: 저장된 answers 행의 id.
    """
    cur = conn.execute(
        "INSERT INTO answers "
        "(repo_id, question_id, question_text, body, "
        " specificity, calibration, groundedness, verdict_line, revision, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            repo_id,
            question_id,
            feedback.question,
            feedback.user_answer,
            feedback.specificity,
            feedback.calibration,
            feedback.groundedness,
            feedback.verdict_line,
            feedback.revision,
            now(),
        ),
    )
    answer_id = cur.lastrowid

    for c in feedback.claims:
        conn.execute(
            "INSERT INTO claims "
            "(answer_id, claim, verdict, hedged, evidence, note) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (answer_id, c.claim, c.verdict, 1 if c.hedged else 0, c.evidence, c.note),
        )

    conn.commit()
    return answer_id

def answered_questions(conn: sqlite3.Connection, repo_id: int) -> set[str]:
    """채점받은 적 있는 질문 문장을 모은다.

    면접 질문 탭이 답한 질문에 표시를 다는 재료다. 채점 기록은 질문 id가 아니라
    질문 문장을 남기므로(save_answer) 문장으로 맞춘다. 질문 목록을 다시 만들어도
    같은 질문이면 문장이 같아 표시가 이어진다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.

    Returns:
        set[str]: 질문 문장 집합.
    """
    rows = conn.execute(
        "SELECT DISTINCT question_text FROM answers WHERE repo_id = ?", (repo_id,)
    ).fetchall()
    return {r["question_text"] for r in rows}


def list_answers(conn: sqlite3.Connection, repo_id: int, limit: int = 20) -> list:
    """최근 채점 기록을 시간 역순으로 가져온다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.
        limit (int): 가져올 최대 개수.

    Returns:
        list: answers 행 목록. 최신순.
    """
    return conn.execute(
        "SELECT * FROM answers WHERE repo_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (repo_id, limit),
    ).fetchall()


def claims_for(conn: sqlite3.Connection, answer_ids: list[int]) -> dict[int, list]:
    """여러 답변의 주장을 한 번에 꺼내 답변별로 묶는다.

    답변마다 따로 조회하면 기록 화면 한 번에 쿼리가 답변 수만큼 나간다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        answer_ids (list[int]): 답변 id 목록.

    Returns:
        dict[int, list]: 답변 id -> claim 행 목록. 저장된 순서를 지킨다.
    """
    if not answer_ids:
        return {}

    marks = ", ".join("?" for _ in answer_ids)
    rows = conn.execute(
        f"SELECT * FROM claims WHERE answer_id IN ({marks}) ORDER BY id",
        answer_ids,
    ).fetchall()

    grouped: dict[int, list] = {}
    for r in rows:
        grouped.setdefault(r["answer_id"], []).append(r)
    return grouped


def verdict_summary(conn: sqlite3.Connection, repo_id: int) -> dict:
    """주장 판정을 종류별로 센다.

    개별 채점 점수보다 이 누적 비율이 중요하다.
    한 번 단정한 것은 실수지만 계속 단정하는 것은 습관이고,
    면접에서 무너지는 것은 후자다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.

    Returns:
        dict: (verdict, hedged) 조합별 개수. 키는 "verdict:hedged" 형식.
    """
    rows = conn.execute(
        "SELECT c.verdict, c.hedged, COUNT(*) AS n "
        "FROM claims c JOIN answers a ON c.answer_id = a.id "
        "WHERE a.repo_id = ? "
        "GROUP BY c.verdict, c.hedged",
        (repo_id,),
    ).fetchall()

    return {f"{r['verdict']}:{r['hedged']}": r["n"] for r in rows}


def repeated_assertions(conn: sqlite3.Connection, repo_id: int, limit: int = 5) -> list:
    """근거 없이 단정한 주장을 최근 순으로 가져온다.

    verdict가 unverifiable이거나 contradicted인데 유보하지 않은 것들이다.
    사용자가 무엇을 반복해서 단정하는지 눈으로 보게 하는 것이 목적이므로
    집계하지 않고 문장을 그대로 보여준다. 자동 분류는 주제를 잘못 묶을
    위험이 있고, 사람은 자기 문장 몇 개만 나란히 봐도 패턴을 알아본다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.
        limit (int): 가져올 최대 개수.

    Returns:
        list: claim 행 목록.
    """
    return conn.execute(
        "SELECT c.claim, c.verdict, a.created_at "
        "FROM claims c JOIN answers a ON c.answer_id = a.id "
        "WHERE a.repo_id = ? AND c.hedged = 0 "
        "  AND c.verdict IN ('unverifiable', 'contradicted') "
        "ORDER BY a.created_at DESC LIMIT ?",
        (repo_id, limit),
    ).fetchall()


def save_ask(
    conn: sqlite3.Connection,
    repo_id: int,
    question: str,
    answer: str,
    sources: list[dict],
    parent_id: int | None = None,
) -> int:
    """질문과 그때 받은 답, 근거를 저장한다.

    채점 기록(answers)과 테이블을 나눈다. 기록 화면 맨 위의 누적은 채점된 주장의
    판정으로 세는데, 질문과 답은 채점된 적이 없어 섞이면 그 숫자가 흐려진다.

    근거는 JSON 문자열로 넣는다. 질문을 꺼낼 때 늘 함께 나오는 부속물이고
    가로질러 세어볼 일이 없다. questions의 can_say와 같은 이유다.

    근거의 줄 번호는 저장할 때 그대로 남는다. 나중에 코드를 고치면 줄이 어긋나지만,
    이것은 "그때 그 답이 무엇을 근거로 했나"의 기록이라 고쳐 쓰지 않는다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.
        question (str): 사용자 질문.
        answer (str): 받은 답(마크다운).
        sources (list[dict]): 근거 목록. services.qa.source_refs의 결과.
        parent_id (int | None): 이 질문이 이어진 앞 질문의 id. 첫 질문이면 None.

    Returns:
        int: 저장된 asks 행의 id.
    """
    cur = conn.execute(
        "INSERT INTO asks (repo_id, question, answer, sources, created_at, parent_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            repo_id,
            question,
            answer,
            json.dumps(sources, ensure_ascii=False),
            now(),
            parent_id,
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_asks(conn: sqlite3.Connection, repo_id: int, limit: int = 20) -> list:
    """최근 질문 기록을 시간 역순으로 가져온다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.
        limit (int): 가져올 최대 개수.

    이어진 질문에는 앞 질문의 문장(parent_question)을 붙인다. 목록은 최근 몇 건만
    꺼내므로 앞 질문이 목록에서 잘렸을 수 있는데, 화면은 그래도 무엇에 이어진
    질문인지 보여줘야 한다.

    Returns:
        list: asks 행 목록. 최신순. sources는 JSON 문자열 그대로다.
    """
    return conn.execute(
        "SELECT a.*, p.question AS parent_question "
        "FROM asks a LEFT JOIN asks p ON p.id = a.parent_id "
        "WHERE a.repo_id = ? ORDER BY a.created_at DESC LIMIT ?",
        (repo_id, limit),
    ).fetchall()


def get_ask_chain(
    conn: sqlite3.Connection, repo_id: int, ask_id: int, limit: int
) -> list:
    """질문 하나에서 앞 질문을 거슬러 올라가 대화를 꺼낸다.

    이어지는 질문에 붙일 앞 대화다. 화면이 보낸 대화 내용을 믿지 않고 기록에서
    꺼내, 화면에 보인 대화와 모델이 받은 대화가 어긋나지 않게 한다.

    limit까지만 거슬러 올라간다. 오래된 턴은 답변에 붙이지 않으므로 더 읽을
    필요가 없고, 기록이 어떤 식으로 꼬여 있어도 반복이 끝나게 한다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.
        ask_id (int): 거슬러 올라가기 시작할 질문의 id. 대화의 마지막 턴이다.
        limit (int): 꺼낼 최대 턴 수.

    Returns:
        list: asks 행 목록. 오래된 것부터. 그 id가 없으면 빈 목록.
    """
    chain = []
    current = ask_id
    while current is not None and len(chain) < limit:
        row = conn.execute(
            "SELECT * FROM asks WHERE id = ? AND repo_id = ?", (current, repo_id)
        ).fetchone()
        if row is None:
            break
        chain.append(row)
        current = row["parent_id"]

    chain.reverse()
    return chain


def count_asks(conn: sqlite3.Connection, repo_id: int) -> int:
    """저장된 질문 수를 센다.

    목록은 최근 몇 건만 꺼내므로, 잘렸는지 밝히려면 전체 수가 따로 필요하다.

    Args:
        conn (sqlite3.Connection): 열린 연결.
        repo_id (int): 대상 레포 id.

    Returns:
        int: 질문 수.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM asks WHERE repo_id = ?", (repo_id,)
    ).fetchone()
    return row["n"]
