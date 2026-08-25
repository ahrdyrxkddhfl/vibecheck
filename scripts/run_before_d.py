"""실험 D before 측정: pyproject.toml 청크를 넣기 전의 답변을 기록한다.

after와 비교할 기준선이다.
청크를 넣은 뒤에만 재면 좋은 점수가 나와도 그것이 검색 덕인지
모델이 원래 알던 것인지(또는 그럴듯하게 지어낸 것인지) 구분할 수 없다.

run_measure.py와 달리 preflight를 하지 않는다.
정답 청크가 인덱스에 없는 것이 이 실행의 전제이므로,
없다고 멈추면 측정 자체가 불가능하다.
검색 순위는 전부 miss가 나오는 것이 정상이고, 볼 것은 답변 품질뿐이다.

PERSIST_DIR을 절대 경로로 둔다.
상대 경로로 두었던 이전 실험 인덱스가 다른 디렉터리의 삭제 명령에
휩쓸려 사라진 적이 있다. 실행 위치에 의존하지 않아야 한다.
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

QUESTIONS_PATH = Path("experiments/exp_d_questions.json")
OUTPUT_PATH = Path("experiments/exp_d_before.md")

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


def run() -> None:
    """질문 전체를 실행하고 채점표를 파일로 남긴다."""
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    questions = data["questions"]

    chunks = load_chunks()
    print(f"인덱스 청크 {len(chunks)}개 복원")

    # 정답 청크가 없어야 정상이므로, 있으면 전제가 깨진 것이다.
    if any("pyproject" in c.file for c in chunks):
        print("\npyproject.toml 청크가 이미 인덱스에 있습니다. before 측정이 아닙니다.")
        sys.exit(1)

    llm = AnthropicClient(model="claude-sonnet-4-6")
    store = VectorStore(persist_dir=PERSIST_DIR)

    header = (
        "# 실험 D before — pyproject.toml 청크 추가 전\n\n"
        f"- 실행 시각: {datetime.now():%Y-%m-%d %H:%M}\n"
        f"- 대상: {data['target']}\n"
        f"- 인덱스: {PERSIST_DIR} ({len(chunks)}청크, tests 제외, L1 포함)\n"
        f"- top_k: {TOP_K}\n"
        "- 정답 청크가 인덱스에 없으므로 검색 순위는 전부 miss가 정상\n"
        "- 채점: 답변 품질만 수동. 질문지의 expected 기준\n\n"
    )
    OUTPUT_PATH.write_text(header, encoding="utf-8")

    for i, q in enumerate(questions, start=1):
        print(f"[{i}/{len(questions)}] {q['id']} ...", flush=True)

        text, sources = answer(q["question"], chunks, store, llm, top_k=TOP_K)

        retrieved = "\n".join(
            f"{n}. `{c.file}::{c.symbol}`" for n, c in enumerate(sources, start=1)
        )

        block = (
            f"## {q['id']} ({q['type']})\n\n"
            f"**질문**: {q['question']}\n\n"
            f"**정답 요지**: {q['expected']}\n\n"
            f"**근거 출처**: {q['source']}  \n"
            f"**인덱스내 근거**: {q['in_index']}\n\n"
            f"### 검색 결과 (순서 = 순위)\n\n{retrieved}\n\n"
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