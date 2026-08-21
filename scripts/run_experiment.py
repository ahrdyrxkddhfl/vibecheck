"""대조 실험: 독스트링 유무에 따른 Q&A 품질을 비교한다.

이미 저장된 인덱스를 재사용해 질문만 던진다.
매번 재인덱싱하면 비용이 들 뿐 아니라 요약이 실행마다 미세하게 달라져 두 조건을 비교할 수 없게 된다.
실험에서는 인덱스를 고정해야 한다.

Chunk 객체를 저장된 메타데이터로부터 복원하는 이유는 answer()가 코드 본문을 필요로 하는데
Chroma에는 임베딩 텍스트만 있기 때문이다.
따라서 원본 소스 파일에서 해당 줄 범위를 다시 읽어 채운다.
"""

import sys
from pathlib import Path

import chromadb

from vibecheck.llm.anthropic import AnthropicClient
from vibecheck.models import Chunk
from vibecheck.services.qa import answer
from vibecheck.store.vector import VectorStore

QUESTIONS = [
    "인덱싱할 파일은 어떻게 골라져?",
    "walk() 함수는 무슨 일을 해?",
    "왜 정규식 대신 tree-sitter를 썼어?",
    "왜 코드 원문이 아니라 요약을 임베딩해?",
    "Chunk 객체는 어디서 만들어져?",
    "답변을 생성할 때 어떤 모델을 쓰지?",
]

CONDITIONS = {
    "original": (".vibecheck/chroma", "vibecheck"),
    "stripped": (".vibecheck/chroma_stripped", "experiments/stripped/vibecheck"),
}

def load_chunks(persist_dir: str, source_root: str) -> list[Chunk]:
    """저장된 인덱스로부터 Chunk 목록을 복원한다.

    Args:
        persist_dir (str): Chroma 인덱스 경로.
        source_root (str): 코드 본문을 읽어올 소스 루트.

    Returns:
        list[Chunk]: 코드 본문이 채워진 청크 목록.
    """
    col = chromadb.PersistentClient(path=persist_dir).get_collection("chunks")
    got = col.get()

    chunks = []
    for meta in got["metadatas"]:
        path = Path(source_root) / meta["file"]
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

def run(condition:str) -> None:
    """한 조건에 대해 모든 질문을 실행하고 결과를 출력한다.

    Args:
        condition (str): CONDITIONS의 키.
    """
    persist_dir, source_root = CONDITIONS[condition]

    llm = AnthropicClient(model="claude-sonnet-4-6")
    store = VectorStore(persist_dir=persist_dir)
    chunks = load_chunks(persist_dir, source_root)

    for i, question in enumerate(QUESTIONS, start=1):
        print("=" * 60)
        print(f"[{condition}] Q{i}. {question}\n")

        text, sources = answer(question, chunks, store, llm)
        print(text)

        print("\n--- 검색된 청크 (순서 = 검색 순위) ---")
        for rank, c in enumerate(sources, start=1):
            print(f"    {rank}. {c.file}::{c.symbol}")
        print()

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "original")