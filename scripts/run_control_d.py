"""실험 D 네거티브 컨트롤: 기존 15문항이 새 청크에 밀려나지 않았는지 확인한다.

pyproject.toml 청크가 top_k=8 경쟁에 들어왔으므로, 기존 질문에서
코드 청크 하나가 밀려났을 수 있다. 새 문항이 3점 올랐어도 기존이 그만큼
내려갔다면 순이득이 없다.

특히 Q05(httpx를 쓰나)와 Q09(pydantic/SearchItem)가 새 청크와 키워드를
공유하므로 간섭 위험이 가장 크다.

A3(23/27)와 직접 비교하지 않는다.
A3를 측정한 인덱스는 소실되었고 현재 인덱스는 요약이 새로 생성된 것이라
같은 조건이 아니다. 이 측정이 새 기준선이 되며,
A3 점수는 참고용으로만 머리말에 남긴다.

preflight는 유지한다.
여기서는 정답 청크 15개가 모두 인덱스에 있어야 정상이고,
하나라도 없으면 순위 채점이 조용히 전부 miss가 된다.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import chromadb

from vibecheck.llm.anthropic import AnthropicClient
from vibecheck.models import Chunk
from vibecheck.services.qa import answer
from vibecheck.store.vector import VectorStore

QUESTIONS_PATH = Path("experiments/exp_a_questions.json")
OUTPUT_PATH = Path("experiments/exp_d_control15.md")

TARGET = str(Path.home() / "work/vibecheck-targets/ctxd")
PERSIST_DIR = str(Path.home() / "work/vibecheck-targets/ctxd/.vibecheck/chroma")
TOP_K = 8


def load_chunks() -> list[Chunk]:
    """저장된 인덱스로부터 코드 본문이 채워진 청크 목록을 복원한다.

    Chroma에는 임베딩 텍스트와 메타데이터만 있고 코드 원문이 없다.
    answer()는 원문을 컨텍스트로 넘겨야 하므로 소스 파일에서 줄 범위를 다시 읽는다.

    Returns:
        list[Chunk]: 코드 본문이 채워진 청크 목록.
    """
    col = chromadb.PersistentClient(path=PERSIST_DIR).get_collection("chunks")
    got = col.get()

    chunks = []
    for meta in got["metadatas"]:
        path = Path(TARGET) / meta["file"]
        src_lines = path.read_text(encoding="utf-8").split("\n")
        code = "\n".join(src_lines[meta["start_line"] - 1 : meta["end_line"]])

        chunks.append(
            Chunk(
                file=meta["file"],
                symbol=meta["symbol"],
                kind=meta["kind"],
                start_line=meta["start_line"],
                end_line=meta["end_line"],
                code=code,
                summary=meta["summary"],
            )
        )
    return chunks


def matches(chunk: Chunk, gold: str) -> bool:
    """청크가 질문지에 적힌 정답 청크인지 판별한다.

    심볼 이름은 마지막 마디만 비교한다.
    질문지에는 AsyncClient.search로 적혀 있는데 청커는 search로만 이름 붙이므로,
    표기 차이 때문에 정답을 놓치는 일을 막기 위해서다.

    Args:
        chunk (Chunk): 검사할 청크.
        gold (str): "파일 경로::심볼" 형식의 정답 표기.

    Returns:
        bool: 같은 청크로 볼 수 있으면 True.
    """
    gold_file, _, gold_symbol = gold.partition("::")
    if chunk.file != gold_file:
        return False
    return chunk.symbol.split(".")[-1] == gold_symbol.split(".")[-1]


def preflight(questions: list[dict], chunks: list[Chunk]) -> list[str]:
    """정답 청크가 인덱스에 실재하는지 검사한다.

    Args:
        questions (list[dict]): 질문 목록.
        chunks (list[Chunk]): 인덱싱된 전체 청크.

    Returns:
        list[str]: 인덱스에서 찾지 못한 정답 표기 목록. 비어 있으면 정상.
    """
    missing = []
    for q in questions:
        gold = q["gold_chunk"]
        if not any(matches(c, gold) for c in chunks):
            missing.append(f"{q['id']}: {gold}")
    return missing


def rank_of(sources: list[Chunk], gold: str) -> str:
    """근거 목록에서 정답 청크의 순위를 찾는다.

    Args:
        sources (list[Chunk]): answer()가 돌려준 근거 목록. 순서가 검색 순위다.
        gold (str): 정답 청크 표기.

    Returns:
        str: 1부터 시작하는 순위 문자열. 없으면 "miss".
    """
    for i, c in enumerate(sources, start=1):
        if matches(c, gold):
            return str(i)
    return "miss"


def run() -> None:
    """질문 전체를 실행하고 채점표를 파일로 남긴다."""
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    questions = data["questions"]

    chunks = load_chunks()
    print(f"인덱스 청크 {len(chunks)}개 복원")

    if not any("pyproject" in c.file for c in chunks):
        print("\npyproject.toml 청크가 인덱스에 없습니다. 컨트롤 측정 조건이 아닙니다.")
        sys.exit(1)

    # 채점이 가능한 상태인지 먼저 확인한다. (요금이 나가기 전에)
    missing = preflight(questions, chunks)
    if missing:
        print("\n정답 청크를 인덱스에서 찾지 못했습니다. 검색 순위 채점이 불가능합니다:")
        for m in missing:
            print(f"    - {m}")
        sys.exit(1)

    print(f"정답 청크 {len(questions)}개 모두 인덱스에서 확인됨\n")

    llm = AnthropicClient(model="claude-sonnet-4-6")
    store = VectorStore(persist_dir=PERSIST_DIR)

    header = (
        "# 실험 D 컨트롤 — 기존 15문항 재측정 (pyproject 청크 추가 후)\n\n"
        f"- 실행 시각: {datetime.now():%Y-%m-%d %H:%M}\n"
        f"- 대상: {data['target']}\n"
        f"- 인덱스: {PERSIST_DIR} ({len(chunks)}청크, tests 제외, L1 포함, pyproject 포함)\n"
        f"- top_k: {TOP_K}\n"
        "- 목적: 새 청크가 기존 문항을 밀어냈는지 확인. Q05·Q09가 간섭 위험 최대\n"
        "- 참고: A3는 23/27이었으나 그 인덱스는 소실됨. 요약이 새로 생성되어 직접 비교 불가\n"
        "- 채점: `exp_a_grading.md` 기준. 검색 순위는 자동, 답변 품질은 수동\n\n"
    )
    OUTPUT_PATH.write_text(header, encoding="utf-8")

    for i, q in enumerate(questions, start=1):
        print(f"[{i}/{len(questions)}] {q['id']} ...", flush=True)

        text, sources = answer(q["question"], chunks, store, llm, top_k=TOP_K)
        rank = rank_of(sources, q["gold_chunk"])

        retrieved = "\n".join(
            f"{n}. `{c.file}::{c.symbol}`" for n, c in enumerate(sources, start=1)
        )

        # 새 청크가 이 문항의 top_k에 끼어들었는지 한눈에 보이게 표시한다.
        intruded = any("pyproject" in c.file for c in sources)

        block = (
            f"## {q['id']} ({q['type']})\n\n"
            f"**질문**: {q['question']}\n\n"
            f"**정답 요지**: {q['expected']}\n\n"
            f"**근거 출처**: {q['source']}  \n"
            f"**인덱스내 근거**: {q['in_index']}  \n"
            f"**정답 청크**: `{q['gold_chunk']}`\n\n"
            f"### 검색 결과 (순서 = 순위)\n\n{retrieved}\n\n"
            f"**정답 청크 순위: {rank}**  \n"
            f"**pyproject 청크 진입: {'예' if intruded else '아니오'}**\n\n"
            f"### 답변\n\n{text}\n\n"
            "### 채점\n\n"
            "- 점수(0~2): \n"
            "- 플래그(H/A/-): \n"
            "- 메모: \n\n"
            "---\n\n"
        )
        with OUTPUT_PATH.open("a", encoding="utf-8") as f:
            f.write(block)

    print(f"\n완료. {OUTPUT_PATH}")


if __name__ == "__main__":
    if not QUESTIONS_PATH.exists():
        print(f"질문 파일이 없습니다: {QUESTIONS_PATH}")
        sys.exit(1)
    if OUTPUT_PATH.exists() and "### 답변" in OUTPUT_PATH.read_text(encoding="utf-8"):
        print(f"이미 측정된 파일입니다: {OUTPUT_PATH}")
        print("다시 측정하려면 파일을 비우거나 이름을 바꾸세요.")
        sys.exit(1)
    run()