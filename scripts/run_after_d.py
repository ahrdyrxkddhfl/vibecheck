"""실험 D after 측정: pyproject.toml 청크를 넣은 뒤의 답변을 기록한다.

before(exp_d_before.md, 3/8)와 같은 질문·같은 인덱스·같은 top_k로 잰다.
바뀐 것은 청크 하나가 추가된 것뿐이므로 두 결과의 차이가 곧 그 청크의 기여분이다.

청크는 LLM을 타지 않고 tomllib로 조립되었고 upsert로 넣었으므로,
기존 67개 청크의 요약은 before와 바이트 단위로 동일하다.
재인덱싱했다면 요약이 새로 생성되어 "청크 추가 효과"와
"요약이 우연히 달라진 효과"가 섞였을 것이다.

run_measure.py와 달리 preflight를 하지 않는다.
D04는 근거가 없는 것이 정답인 트랩 문항이라
정답 청크가 상위에 뜨는 것 자체가 위험 신호이며, 순위 채점 대상이 아니다.

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
OUTPUT_PATH = Path("experiments/exp_d_after.md")

TARGET = str(Path.home() / "work/vibecheck-targets/ctxd")
PERSIST_DIR = str(Path.home() / "work/vibecheck-targets/ctxd/.vibecheck/chroma")
TOP_K = 8


def load_chunks() -> list[Chunk]:
    """저장된 인덱스로부터 코드 본문이 채워진 청크 목록을 복원한다.

    Chroma에는 임베딩 텍스트와 메타데이터만 있고 코드 원문이 없다.
    answer()는 원문을 컨텍스트로 넘겨야 하므로 소스 파일에서 줄 범위를 다시 읽는다.

    pyproject.toml 청크도 이 경로로 복원된다.
    파일이 실재하고 start_line/end_line이 파일 전체를 가리키므로
    원문이 그대로 읽히며, .py가 아니어도 줄 범위 읽기에는 차이가 없다.

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
    질문지 표기와 청커가 붙인 이름이 어긋나면 정답을 1등으로 물어와도
    전부 miss로 기록되는데, 이 실패는 예외 없이 조용히 진행된다.

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

    # 이번엔 있어야 정상이다. 없으면 적재가 안 된 것이므로 측정 의미가 없다.
    if not any("pyproject" in c.file for c in chunks):
        print("\npyproject.toml 청크가 인덱스에 없습니다.")
        print("먼저 실행하세요: python scripts/add_pyproject_chunk.py --commit")
        sys.exit(1)

    llm = AnthropicClient(model="claude-sonnet-4-6")
    store = VectorStore(persist_dir=PERSIST_DIR)

    header = (
        "# 실험 D after — pyproject.toml 청크 추가 후\n\n"
        f"- 실행 시각: {datetime.now():%Y-%m-%d %H:%M}\n"
        f"- 대상: {data['target']}\n"
        f"- 인덱스: {PERSIST_DIR} ({len(chunks)}청크, tests 제외, L1 포함, pyproject 포함)\n"
        f"- top_k: {TOP_K}\n"
        "- 대조군: `exp_d_before.md` (3/8)\n"
        "- D04는 트랩 문항. 순위가 상위여도 그것이 정답의 근거는 아니다\n"
        "- 채점: 답변 품질만 수동. 질문지의 expected 기준\n\n"
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