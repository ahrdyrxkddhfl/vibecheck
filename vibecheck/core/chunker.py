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

    # 다른 파일 청크와 같은 모양을 지킨다. 첫 조각이 경로 라벨,
    # 두 번째가 사람이 읽을 설명 자리다. 여기만 모양이 다르면
    # 그 자리를 읽는 쪽이 예외를 하나 더 두어야 한다.
    summary_parts = ["pyproject.toml 파일", "패키지 설정과 설치 정보를 담는 파일."]

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
        kind="config",
        start_line=1,
        end_line=len(raw.splitlines()),
        code="\n".join(lines),
        imports=[],
        summary=" / ".join(summary_parts),
    )

README_NAMES = ("README.md", "readme.md", "README.markdown", "Readme.md")
"""README로 인정할 파일 이름.

확장자 없는 README나 .rst는 넣지 않는다. 마크다운 헤딩 규칙으로 자르는
구현이라 다른 형식은 절이 하나도 안 잡히거나 통째로 한 덩어리가 된다.
"""


def split_markdown_sections(raw: str) -> list[tuple[str, int, int]]:
    """마크다운을 최상위 헤딩(#, ##) 단위로 나눈다.

    코드 블록 안의 줄은 헤딩으로 보지 않는다. 설치 안내에 흔한
    `# .env 파일에 키 입력` 같은 주석이 헤딩으로 잡히면 절이
    엉뚱한 자리에서 끊긴다. 파이썬 주석이 #으로 시작하므로
    파이썬 레포의 README에서는 거의 반드시 걸린다.

    ###은 자르지 않는다. "사용법" 아래 명령별 소절을 각각 떼어내면
    명령어 한 줄만 남아 어느 도구 얘기인지 알 수 없는 조각이 된다.
    절 단위로 두면 "이 도구로 무엇을 할 수 있나"에 통째로 답이 된다.

    Args:
        raw (str): 마크다운 원문.

    Returns:
        list[tuple[str, int, int]]: (제목, 시작줄, 끝줄) 목록.
            줄 번호는 1-based이고 끝줄을 포함한다. 내용이 빈 절은 제외된다.
    """
    lines = raw.splitlines()
    in_fence = False
    starts: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        stripped = line.strip()
        # "# "와 "## "만 받는다. "###"은 세 번째 글자가 공백이 아니라
        # 두 조건 모두에서 걸러진다.
        if stripped.startswith("# ") or stripped.startswith("## "):
            starts.append((i, stripped.lstrip("#").strip()))

    if not starts:
        return [("README", 1, len(lines))] if raw.strip() else []

    sections: list[tuple[str, int, int]] = []

    # 첫 헤딩 앞에 글이 있으면 버리지 않는다. 배지나 한 줄 소개가
    # 거기 있는 경우가 많고, 그것이 프로젝트 목적에 가장 가까운 문장이다.
    if starts[0][0] > 0:
        sections.append(("머리말", 1, starts[0][0]))

    for n, (idx, title) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        sections.append((title, idx + 1, end))

    return [
        s for s in sections if "\n".join(lines[s[1] - 1 : s[2]]).strip()
    ]

STATUS_MARKS = ("🚧", "⚠️", "🏗", "WIP", "Work in progress", "개발 중", "작업 중")
"""프로젝트 상태 표시로 보는 낱말.

README 첫 절 앞자리에 자주 놓이지만 "이 프로젝트가 무엇인가"의 답이 아니다.
임베딩에 실리는 자리가 128 토큰뿐이라 이런 줄 하나가 목적 문장을 밀어낸다.
"""


def _is_status_line(line: str) -> bool:
    """상태 표시만으로 이루어진 줄인지 판정한다.

    짧은 줄만 대상으로 한다. 긴 문장 안에 '개발 중'이 들어 있는 경우는
    실제 설명일 가능성이 높아 걷어내면 내용을 잃는다.

    Args:
        line (str): 기호를 걷어낸 뒤의 한 줄.

    Returns:
        bool: 상태 표시 줄이면 True.
    """
    if len(line) > 30:
        return False
    return any(mark in line for mark in STATUS_MARKS)

def _section_keywords(body: str, title: str = "", limit: int = 200) -> str:
    """절 본문에서 검색어와 맞붙을 낱말만 추려 한 줄로 만든다.

    임베딩 모델의 max_seq_length가 128이라 summary에 담기는 앞자리가
    사실상 검색 가능 범위다. 마크다운 기호와 코드 블록은 질의어와
    매칭될 일이 없으므로 걷어내고 낱말 밀도를 높인다.

    ### 소제목은 #만 떼고 남긴다. "답변 채점", "면접 예상질문" 같은
    소제목이 그 절에서 가장 질의어에 가까운 표현인 경우가 많다.

    Args:
        body (str): 절 본문 원문.
        title (str): 절 제목. 본문 첫 줄이 제목과 같으면 건너뛰는 데 쓴다.
        limit (int): 결과 최대 길이.

    Returns:
        str: 공백으로 이어붙인 요약 재료.
    """
    in_fence = False
    picked: list[str] = []

    for line in body.splitlines():
        s = line.strip()

        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not s:
            continue

        if s.startswith("#"):
            s = s.lstrip("#").strip()

        # 목록·인용·표·강조 기호를 걷어낸다. 남는 것은 낱말뿐이다.
        s = s.lstrip("-*>+ ").replace("|", " ").replace("**", "").strip()
        if not s or set(s) <= set("-: "):
            continue

        # 제목은 summary에 이미 따로 실려 있다. 본문 첫 줄로 다시 들어오면
        # 128 토큰뿐인 임베딩 앞자리를 같은 낱말이 두 번 먹는다.
        if picked == [] and s == title.strip():
            continue

        # 배지와 상태 표시를 건너뛴다. README 첫 절 앞자리를 차지하지만
        # 프로젝트가 무엇인지와는 무관해, 정작 목적 문장을 뒤로 밀어낸다.
        if s.startswith("![") or s.startswith("[!["):
            continue
        if _is_status_line(s):
            continue

        picked.append(s)
        if sum(len(p) for p in picked) >= limit:
            break

    return " ".join(picked)[:limit]


def to_readme_chunks(root: str) -> list[Chunk]:
    """README를 절 단위 청크 목록으로 조립한다.

    프로젝트가 무엇을 위한 것인지는 코드에 없다. 함수와 클래스를 모두
    읽어도 "이 도구가 어떤 문제를 풀려고 만들어졌는가"는 나오지 않는다.
    실제로 목적을 정확히 말한 답변이 근거 청크에 없다는 이유로
    확인불가 판정을 받는 것을 확인했다. pyproject.toml 때와 같은 문제이고
    같은 해법을 쓴다.

    절마다 청크를 따로 만드는 이유는 임베딩 길이 제한이다.
    통째로 넣으면 앞부분만 임베딩에 실려 뒤쪽 절은 검색에서 사라진다.
    기술 스택표가 뒤에 있는 README에서는 라이브러리 질문에 닿지 못한다.

    kind는 "doc"이다. "file"로 넣으면 모듈 지도에 README 절이
    파일처럼 나열되고, L1 파일 수도 절 개수만큼 부풀려진다.

    imports는 비운다. 여기에 값을 넣으면 split_dependencies가 함께
    움직여 외부 의존성 수와 내부 참조 수가 바뀐다. 검색을 고치는 변경이
    통계까지 흔들면 원인을 가릴 수 없다.

    Args:
        root (str): 레포 루트 경로.

    Returns:
        list[Chunk]: 절 단위 청크 목록. README가 없거나 읽을 수 없으면 빈 목록.
    """
    for name in README_NAMES:
        path = Path(root) / name
        if path.is_file():
            break
    else:
        return []

    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    lines = raw.splitlines()
    chunks: list[Chunk] = []

    for title, start, end in split_markdown_sections(raw):
        body = "\n".join(lines[start - 1 : end])

        # 다른 청크와 같은 모양을 지킨다. 첫 조각이 경로 라벨,
        # 두 번째가 사람이 읽을 설명 자리다.
        summary_parts = [f"{name} 문서", f"'{title}' 절"]

        keywords = _section_keywords(body, title)
        if keywords:
            summary_parts.append(keywords)

        code = "\n".join([f"문서: {name}", f"절: {title}", "", body])

        chunks.append(
            Chunk(
                file=name,
                symbol=f"{name}#{title}",
                kind="doc",
                start_line=start,
                end_line=end,
                code=code,
                imports=[],
                summary=" / ".join(summary_parts),
            )
        )

    return chunks

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