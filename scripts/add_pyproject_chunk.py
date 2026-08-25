"""pyproject.toml의 사실을 청크로 조립해 기존 인덱스에 추가한다.

원문을 그대로 싣지 않는다.
임베딩 모델(paraphrase-multilingual-MiniLM-L12-v2)의 max_seq_length가 128이라
파일 뒤쪽에 있는 [project.scripts]가 임베딩에서 잘려나간다.
검색으로 닿아야 하는 사실을 summary 앞자리에 놓으려면 조립이 필요하다.

find_script_entries와 같은 tomllib로 읽는다.
조립 경로(리포트·면접 질문)는 이 파일을 읽어 진입점을 알지만
검색 경로(ask)는 이 파일의 존재조차 모르는 상태였다.
같은 출처를 쓰게 만드는 것이 이 스크립트의 목적이다.

--commit 없이 실행하면 청크만 출력하고 인덱스는 건드리지 않는다.
gold_chunk 표기가 실제 청크와 어긋나면 검색 순위 채점이
예외 없이 전부 miss로 기록되므로, 넣기 전에 눈으로 확인해야 한다.
"""

import sys
import tomllib
from pathlib import Path

from vibecheck.models import Chunk
from vibecheck.store.vector import VectorStore, build_embedding_text

TARGET = Path.home() / "work/vibecheck-targets/ctxd"
PERSIST_DIR = str(TARGET / ".vibecheck/chroma")


def build_pyproject_chunk(root: Path) -> Chunk | None:
    """pyproject.toml에서 사실을 뽑아 청크 하나로 조립한다.

    summary의 순서가 검색 성패를 가른다.
    [project.scripts]를 맨 앞에 두는 이유는 그것이 다른 어디에도 없는 사실이기
    때문이다. 의존성 이름은 각 파일의 import에서 이미 잡히고 패키지 이름은
    경로에서 유추되지만, 설치 시 생기는 명령과 그 진입 함수는 이 파일에만 있다.

    imports는 비운다.
    여기에 의존성을 넣으면 split_dependencies가 L1의 imports를 세므로
    external_deps와 internal_import_count가 함께 움직인다.
    이번 변경은 검색만 건드려야 하며 통계까지 흔들면 원인을 가릴 수 없다.

    Args:
        root (Path): 레포 루트.

    Returns:
        Chunk | None: 조립된 청크. 파일이 없거나 형식이 깨졌으면 None.
    """
    path = root / "pyproject.toml"
    if not path.is_file():
        return None

    try:
        raw = path.read_text(encoding="utf-8")
        data = tomllib.loads(raw)
    except (tomllib.TOMLDecodeError, OSError):
        return None

    project = data.get("project", {})
    scripts = project.get("scripts", {})
    deps = project.get("dependencies", [])

    # 검색 임베딩에 실릴 핵심. 앞자리일수록 128 토큰 안에 남는다.
    summary_parts = ["pyproject.toml 패키지 설정 파일"]

    if scripts:
        entries = ", ".join(f"{cmd} -> {target}" for cmd, target in scripts.items())
        summary_parts.append(f"설치하면 생기는 명령: {entries}")

    if project.get("name"):
        summary_parts.append(f"패키지 이름: {project['name']}")
    if project.get("version"):
        summary_parts.append(f"버전: {project['version']}")
    if project.get("requires-python"):
        summary_parts.append(f"파이썬 요구 버전: {project['requires-python']}")
    if deps:
        summary_parts.append(f"의존성과 최소 버전: {', '.join(deps)}")

    # code에는 원문을 싣는다. 임베딩에서는 잘리지만 LLM 컨텍스트로는 전달되므로,
    # 검색으로 닿기만 하면 답변 단계에서 전체를 볼 수 있다.
    lines = [f"파일: pyproject.toml", "", "원문:", raw]

    return Chunk(
        file="pyproject.toml",
        symbol="pyproject.toml",
        kind="file",
        start_line=1,
        end_line=len(raw.splitlines()),
        code="\n".join(lines),
        imports=[],
        summary=" / ".join(summary_parts),
    )


def main() -> None:
    """청크를 조립해 보여주고, --commit이 있으면 인덱스에 넣는다."""
    chunk = build_pyproject_chunk(TARGET)
    if chunk is None:
        print(f"pyproject.toml을 읽지 못했습니다: {TARGET}")
        sys.exit(1)

    print(f"id: {chunk.id}")
    print(f"file: {chunk.file}")
    print(f"symbol: {chunk.symbol}")
    print(f"kind: {chunk.kind}")
    print(f"lines: {chunk.start_line}-{chunk.end_line}")
    print(f"\nsummary:\n{chunk.summary}")
    print(f"\n임베딩 텍스트 앞 300자:\n{build_embedding_text(chunk)[:300]}")

    if "--commit" not in sys.argv:
        print("\n(미리보기입니다. 인덱스에 넣으려면 --commit)")
        return

    store = VectorStore(persist_dir=PERSIST_DIR)
    before = store.count()
    store.add([chunk])
    print(f"\n적재 완료: {before} -> {store.count()}")


if __name__ == "__main__":
    main()