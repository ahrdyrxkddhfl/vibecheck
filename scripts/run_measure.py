"""실험 A 본 측정: 인덱싱된 ctxd에 질문 15개를 던지고 결과를 기록한다.

컨트롤과 같은 질문을 쓰되 검색 결과를 붙여 답변하게 한다.
두 조건의 차이가 곧 검색의 기여분이므로 질문은 한 글자도 바꾸지 않는다.

검색 순위는 자동으로 채점한다. answer()가 돌려주는 근거 목록의 순서가 곧 검색 순위이므로,
정답 청크가 몇 번째에 있는지 세면 된다.
답변 품질(0-2점)만 사람이 채점한다.

API를 호출하기 전에 정답 청크가 인덱스에 실재하는지 먼저 검사한다.
청커가 붙인 심볼 이름과 질문지에 적어둔 이름이 어긋나면
검색이 정답을 1등으로 물어봐도 전부 miss로 기록되는데,
이 실패는 예외 없이 조용히 진행된다.
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
OUTPUT_PATH = Path("experiments/exp_a3_results_topk8.md")

TARGET = str(Path.home() / "work/vibecheck-targets/ctxd")
PERSIST_DIR = ".vibecheck/cache_ctxd_l1/chroma"
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
    질문지에는 AsyncClient.search로 적엇는데 청커는 search로만 이름 붙일 수 있어,
    표기 차이 때문에 정답을 놓치는 일을 막기 위해서다.

    Args:
        chunk (Chunk): 검사할 청크.
        gold (str): "파일 경로::심볼" 형식의 정답 표기
    
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
        gold (str): 정답 청크 표기
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

    # 채점이 가능한 상태인지 먼저 확인한다. (요금이 나가기 전에)
    missing = preflight(questions, chunks)
    if missing:
        print("\n정답 청크를 인덱스에서 찾지 못했습니다. 검색 순위 채점이 불가능합니다:")
        for m in missing:
            print(f"    - {m}")
        print("\n질문지의 gold_chunk 표기를 실제 심볼 이름에 맞춰야 합니다.")
        sys.exit(1)

    print("정답 청크 15개 모두 인덱스에서 확인됨\n")

    llm = AnthropicClient(model="claude-sonnet-4-6")
    store = VectorStore(persist_dir=PERSIST_DIR)

    header = (
        "# 실험 A3 — top_k 5->8 (인덱스는 A2와 동일)\n\n"
        f"- 실행 시각: {datetime.now():%Y-%m-%d %H:%M}\n"
        f"- 대상: {data['target']}\n"
        f"- 인덱스: {PERSIST_DIR} (9파일 {len(chunks)}청크, tests 제외, L1 포함)\n"
        f"- top_k: {TOP_K}\n"
        "- 채점: `exp_a_grading.md` 기준. 검색 순위는 자동, 답변 품질은 수동\n"
        "- 대조군: `exp_a2_results_l1.md` (21/27, top_k=5)\n\n"
    )
    OUTPUT_PATH.write_text(header, encoding="utf-8")

    for i, q in enumerate(questions, start=1):
        print(f"[{i}/{len(questions)}] {q['id']} ...", flush=True)

        text, sources = answer(q["question"], chunks, store, llm, top_k=TOP_K)
        rank = rank_of(sources, q["gold_chunk"])

        retrieved = "\n".join(
            f"{n}. `{c.file}::{c.symbol}`" for n, c in enumerate(sources, start=1)
        )

        block = (
            f"## {q['id']} ({q['type']})\n\n"
            f"**질문**: {q['question']}\n\n"
            f"**정답 요지**: {q['expected']}\n\n"
            f"**근거 출처**: {q['source']}  \n"
            f"**인덱스내 근거**: {q['in_index']}  \n"
            f"**정답 청크**: `{q['gold_chunk']}`\n\n"
            f"### 검색 결과 (순서 = 순위)\n\n{retrieved}\n\n"
            f"**정답 청크 순위: {rank}**\n\n"
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