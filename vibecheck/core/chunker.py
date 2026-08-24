"""Symbol에 코드 본문을 결합해 Chunk를 생성한다.

파서가 찾아낸 위치 정보(Symbol)을 받아 실제 소스에서 해당 범위를 잘라내고, 
파일 경로와 전체 심볼명을 붙여 검색 가능한 단위(Chunk)로 만든다.

파싱과 청킹을 분리한 이유는 언어 확장 때문이다.
파서는 언어마다 달라지지만 위치로 코드를 잘라내는 청킹 로직은 언어와 무관하므로
그대로 재사용할 수 있다.
"""

from vibecheck.models import Chunk, Symbol

def to_chunks(
        symbols: list[Symbol],
        source: bytes,
        file_path:str,
        imports: list[str] | None = None,
        ) -> list[Chunk]:
    """Symbol 목록을 Chunk 목록으로 변환한다.

    각 심볼의 라인 범위로 소스를 잘라 코드 본문을 채운다.
    클래스 Chunk는 하위 메서드의 코드를 통째로 포함하므로 
    메서드 Chunk와 내용이 중복되는데, 이는 의도된 설계이다.
    클래스 단위 질문(이 클래스는 무슨 역할인가?)와
    메서드 단위 질문(이 함수는 왜 이렇게 동작하는가?)는
    서로 다른 범위의 맥락을 필요로 하기 때문이다.

    Args:
        symbols (list[Symbol]): 파서가 추출한 심볼 목록.
        source (bytes): 원본 소스 바이트.
        file_path (str): 레포 루트 기준 상대 경로. Chunk의 식별자와 검색 텍스트에 포함됨
        imports (list[str] | None): 파일의 import 문 목록.
            요약 단계에서 라이브러리를 추측하지 않도록 전달한다.
    Returns:
        list[Chunk]: 코드 본문이 채워진 청크 목록. 입력 순서를 유지한다
    """
    lines = source.decode().splitlines()
    chunks = []

    for s in symbols:
        # 라인 번호는 1-based, 리스트 인덱스는 0-based이므로 시작에 -1을 적용
        # 파이썬 슬라이스는 끝 인덱스를 포함하지 않으므로 end_line은 보정하지 않는다.
        # 결과적을 [start-1:end]가 start-end행을 모두 포함한다.
        body = "\n".join(lines[s.start_line -1 : s.end_line])

        # 소속을 포함한 전체 이름을 만든다. 검색 시 login보다 auth.login이
        # 더욱 정확하게 매칭되므로 이 형태로 저장한다.
        symbol_name = f"{s.parent}.{s.name}" if s.parent else s.name

        chunks.append(
            Chunk(
                file=file_path,
                symbol=symbol_name,
                kind=s.kind,
                start_line=s.start_line,
                end_line=s.end_line,
                code=body,
                parent=s.parent,
                imports=imports or [],
            )
        )
    return chunks

def to_file_chunk(
        chunks: list[Chunk],
        file_path: str,
        total_lines: int,
        imports: list[str] | None = None,
) -> Chunk | None:
    """한 파일의 L2 청크들을 묶어 파일 수준(L1) 청크를 만든다.

    함수, 클래스 단위 청크만으로는 답할 수 없는 질문이 있다.
    "이 파일은 어떤 HTTP 라이브러리를 쓰나"의 답은 파일 상단 import 줄에 있는데,
    그 줄은 어떤 함수에도 속하지 않아 L2 청크 어디에도 담기지 않는다.
    Chunk.imports로 요약 프롬프트에는 넣었으나 그것은 검색 대상이 아니다.

    LLM을 다시 호출하지 않고 기존 요약을 조립하는 이유는 재현성이다.
    파일 요약을 매번 생성하면 실행마다 내용이 달라져,
    검색 성능이 올랐을 때 L1 도입 효과인지 요약이 우연히 잘 나온 것인지 구분할 수 없다.
    또한 임베딩 검색은 문장의 매끄러움보다 키워드의 존재에 반응하므로,
    httpx라는 단어가 텍스트에 있는지가 문장이 자연스러운지보다 중요하다.

    Args:
        chunks (list[Chunk]): 같은 파일에서 생성된 L2 청크 목록.
            요약이 채워진 뒤에 호출해야 한다.
        file_path (str): 레포 루트 기준 상대 경로.
        total_lines (int): 파일의 총 줄 수.
        imports (list[str] | None): 파일의 import문 목록.

    Returns:
        Chunk | None: 파일 수준 청크. 청크가 없는 파일이면 None.
    """
    if not chunks:
        return None

    import_list = imports or []

    lines = [f"파일: {file_path}", ""]

    if import_list:
        lines.append("import 목록:")
        lines.extend(f" {imp}" for imp in import_list)
        lines.append("")

    lines.append(f"정의된 심볼 {len(chunks)}개:")
    for c in chunks:
        prefix = "class " if c.kind == "class" else ""
        lines.append(f" {prefix}{c.symbol}")
    lines.append("")

    # 심볼별 요약을 함께 실어 파일 개요만으로도 무슨 일을 하는 파일인지 읽히게 한다.
    summarized = [c for c in chunks if c.summary]
    if summarized:
        lines.append("각 심볼 요약:")
        lines.extend(f" {c.symbol}: {c.summary}" for c in summarized)
    overview = "\n".join(lines)

    # 요약 필드에는 검색 임베딩에 실릴 핵심만 담는다.
    # 심볼 이름과 라이브러리명이 질의어와 직접 매칭되는 부분이기 때문이다.
    symbol_names = ", ".join(c.symbol for c in chunks)
    summary_parts = [f"{file_path} 파일"]
    if import_list:
        summary_parts.append(f"사용 라이브러리: {', '.join(import_list)}")
    summary_parts.append(f"정의: {symbol_names}")

    return Chunk(
        file=file_path,
        symbol=file_path,
        kind="file",
        start_line=1,
        end_line=total_lines,
        code=overview,
        imports=import_list,
        summary=" / ".join(summary_parts),
    )

# ================
# 실행부
# ================

if __name__ == "__main__":
    from vibecheck.core.parser import parse_file, walk

    tree, source = parse_file("tests/fixtures/sample.py")
    symbols = walk(tree.root_node, source)
    chunks = to_chunks(symbols, source, "tests/fixtures/sample.py")

    for c in chunks:
        print(f"\n{'=' * 40}")
        print(f"{c.id} [{c.kind}] {c.start_line}-{c.end_line}")
        print(c.code)