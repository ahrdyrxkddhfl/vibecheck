"""Symbol에 코드 본문을 결합해 Chunk를 생성한다.

파서가 찾아낸 위치 정보(Symbol)을 받아 실제 소스에서 해당 범위를 잘라내고, 
파일 경로와 전체 심볼명을 붙여 검색 가능한 단위(Chunk)로 만든다.

파싱과 청킹을 분리한 이유는 언어 확장 때문이다.
파서는 언어마다 달라지지만 위치로 코드를 잘라내는 청킹 로직은 언어와 무관하므로
그대로 재사용할 수 있다.
"""

import tomllib
from pathlib import Path

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
        source_text: str = "",
        docstring: str | None = None,
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

    모듈 독스트링이 있으면 그것을 파일 설명의 우선 재료로 쓴다.
    조립된 요약은 심볼 이름의 나열이라 "무엇이 들어 있는가"는 알려주지만
    "이 파일이 왜 있는가"는 말해주지 않는다. 독스트링은 작성자가 파일 전체를
    두고 쓴 문장이므로 LLM 호출 없이 얻을 수 있는 가장 정확한 파일 설명이다.

    요약 필드에는 첫 줄만, 본문에는 전문을 싣는다.
    요약은 임베딩에 실려 질의어와 대조되는 자리라 짧을수록 초점이 서고,
    구글 스타일에서 첫 줄은 이미 한 문장 요약이다. 뒤따르는 배경 설명까지
    넣으면 문장이 길어져 핵심 단어가 묽어진다. 반면 본문은 사람이 읽는
    자리이므로 전문이 있는 편이 낫다.

    심볼이 하나도 없는 파일도 청크를 만든다.
    __init__.py는 정의가 없고 재수출 import만 있어 tree-sitter가 심볼을 찾지 못하는데,
    그렇다고 내용이 없는 것은 아니다. "패키지가 무엇을 내보내는가"의 답이 거기에만 있다.
    이 경우 조립할 심볼 목록이 없으므로 원문을 그대로 본문에 싣는다.
    LLM 호출은 여전히 없다.

    Args:
        chunks (list[Chunk]): 같은 파일에서 생성된 L2 청크 목록.
            요약이 채워진 뒤에 호출해야 한다. 비어 있어도 된다.
        file_path (str): 레포 루트 기준 상대 경로.
        total_lines (int): 파일의 총 줄 수.
        imports (list[str] | None): 파일의 import문 목록.
        source_text (str): 파일 원문. 심볼이 없을 때만 본문 재료로 쓴다.
            심볼이 있으면 조립된 개요가 더 압축적이므로 무시한다.
        docstring (str | None): 모듈 독스트링 전문. 없으면 None.
            파서가 자르지 않은 상태로 넘겨야 하며, 요약용으로 줄이는 일은
            검색 텍스트의 길이를 정하는 이쪽 책임이다.

    Returns:
        Chunk | None: 파일 수준 청크.
            심볼도 import도 원문도 없는 빈 파일이면 None.
    """
    import_list = imports or []

    # 셋 다 없으면 인덱싱할 내용 자체가 없다. 빈 __init__.py가 이 경우다.
    if not chunks and not import_list and not source_text.strip():
        return None

    lines = [f"파일: {file_path}", ""]

    # 설명을 심볼 목록보다 앞에 둔다. 목록은 무엇이 들어 있는지만 말하므로
    # 무슨 파일인지 먼저 읽히게 해야 개요로서 쓸모가 있다.
    if docstring:
        lines.append("파일 설명:")
        lines.append(docstring)
        lines.append("")

    if import_list:
        lines.append("import 목록:")
        lines.extend(f" {imp}" for imp in import_list)
        lines.append("")

    # 파일이 무엇을 내놓는지 보는 자리이므로 남이 부를 수 없는 함수는 뺀다.
    # 클래스 이름 집합과 대조하는 이유는 parser가 부모가 있으면 무조건
    # method로 찍어, 함수 안의 중첩 함수도 메서드와 같은 kind를 갖기 때문이다.
    # 클래스와 함수 이름이 겹치면 오판하지만, 그 경우 목록에 한 줄 더 나올 뿐이라 감수한다.
    class_names = {c.symbol for c in chunks if c.kind == "class"}
    public = [c for c in chunks if not c.parent or c.parent in class_names]

    if public:
        lines.append(f"정의된 심볼 {len(public)}개:")
        for c in public:
            prefix = "class " if c.kind == "class" else ""
            lines.append(f" {prefix}{c.symbol}")
        lines.append("")

        # 심볼별 요약을 함께 실어 파일 개요만으로도 무슨 일을 하는 파일인지 읽히게 한다.
        summarized = [c for c in chunks if c.summary]
        if summarized:
            lines.append("각 심볼 요약:")
            lines.extend(f" {c.symbol}: {c.summary}" for c in summarized)
    else:
        lines.append("원문:")
        lines.append(source_text)

    overview = "\n".join(lines)

    # 요약 필드에는 검색 임베딩에 실릴 핵심만 담는다.
    # 심볼 이름과 라이브러리명이 질의어와 직접 매칭되는 부분이기 때문이다.
    summary_parts = [f"{file_path} 파일"]

    # 경로 라벨 바로 뒤가 실질적인 첫 내용 자리다. 라벨을 밀어내지 않는 이유는
    # 파일명 자체가 질의어로 자주 들어와 매칭 재료로 필요하기 때문이다.
    if docstring:
        first_line = docstring.splitlines()[0].strip()
        if first_line:
            summary_parts.append(first_line)

    if import_list:
        summary_parts.append(f"사용 라이브러리: {', '.join(import_list)}")
    if public:
        symbol_names = ", ".join(c.symbol for c in public)
        summary_parts.append(f"정의: {symbol_names}")
    else:
        # 정의가 없다는 사실 자체가 이 파일의 성격이다.
        summary_parts.append("정의된 함수·클래스 없음")

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

def to_pyproject_chunk(root: str) -> Chunk | None:
    """pyproject.toml의 사실을 청크 하나로 조립한다.

    설치하면 생기는 명령과 그 진입 함수는 이 파일에만 있다.
    수집 대상이 .py뿐이라 이 파일은 인덱스에 들어가지 않았고,
    그 결과 리포트는 진입점을 아는데 검색은 그 파일의 존재조차 모르는
    상태가 됐다. 실제로 진입점을 정확히 말한 답변이 "근거 청크에 없다"는
    이유로 확인불가 판정을 받는 것을 확인했다.

    원문을 그대로 싣지 않고 조립하는 이유는 임베딩 모델의 max_seq_length가
    128이기 때문이다. [project.scripts]는 파일 뒤쪽에 있어 원문을 그대로
    임베딩하면 잘려나간다. 검색으로 닿아야 하는 사실일수록 summary
    앞자리에 놓아야 한다.

    imports는 비운다. 여기에 의존성을 넣으면 L1의 imports를 세는
    split_dependencies가 함께 움직여 외부 의존성 수와 내부 참조 수가
    바뀐다. 검색을 고치는 변경이 통계까지 흔들면 원인을 가릴 수 없다.

    Args:
        root (str): 레포 루트 경로.

    Returns:
        Chunk | None: 조립된 청크. 파일이 없거나 형식이 깨졌으면 None.
    """
    path = Path(root) / "pyproject.toml"
    if not path.is_file():
        return None

    try:
        raw = path.read_text(encoding="utf-8")
        data = tomllib.loads(raw)
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        return None

    project = data.get("project", {})
    scripts = project.get("scripts", {})
    deps = project.get("dependencies", [])

    # 앞자리일수록 128 토큰 안에 남는다. 다른 어디에도 없는 사실을 먼저 둔다.
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

    # 본문에는 원문을 싣는다. 임베딩에서는 잘리지만 LLM 컨텍스트로는
    # 전달되므로, 검색으로 닿기만 하면 답변 단계에서 전체를 볼 수 있다.
    lines = ["파일: pyproject.toml", "", "원문:", raw]

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