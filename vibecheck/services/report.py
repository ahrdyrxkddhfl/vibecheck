"""레포 개요를 사람이 읽는 리포트로 조립한다.

목차는 "면접에서 이 레포를 설명해야 한다면 무엇을 알아야 하는가"에서 역산했다.
각 절이 실제로 나올 법한 질문 하나에 대응한다.

LLM 호출은 레포 요약 한 번뿐이고 나머지는 조립이다.
통계와 목록은 이미 인덱싱된 정보에서 계산되므로 물어볼 이유가 없고,
조립은 실행할 때마다 같은 결과를 낸다.
"""

from datetime import datetime

from vibecheck.core.quirks import QuirkGroup
from vibecheck.core.overview import RepoOverview, summarize_repo
from vibecheck.llm.base import LLMClient
from vibecheck.models import Chunk

FOLD_THRESHOLD = 5
"""심볼 목록을 접어둘 기준 개수.

셋넷은 펼쳐두는 편이 읽기 쉽고, 열 몇 개가 펼쳐져 있으면
모듈 지도 전체가 한눈에 들어오지 않는다.
"""

ENTRY_FOLD_THRESHOLD = 4
"""추정 진입점을 접어둘 기준 개수.

확정 진입점이 있을 때만 접는다.
pyproject.toml에 등록된 것이 있다는 것은 "이 프로젝트는 어디서 시작하는가"가
이미 답해졌다는 뜻이고, 나머지는 참고 사항이다.
실제로 확정 1개가 추정 19개에 묻혀 읽히지 않는 일이 있었다.

확정이 없으면 접지 않는다. 그때는 추정이 유일한 단서이므로
접어두면 답을 감추는 셈이 된다.
"""


def format_symbol_lines(symbols: list[Chunk]) -> list[str]:
    """심볼별 요약을 목록 줄로 만든다.

    Args:
        symbols (list[Chunk]): 한 파일에 속한 L2 청크 목록.

    Returns:
        list[str]: 마크다운 목록 줄.
    """
    return [
        f"- `{s.symbol}` ({s.start_line}-{s.end_line}) — {s.summary or '요약 없음'}"
        for s in sorted(symbols, key=lambda c: c.start_line)
    ]


def format_module_map(overview: RepoOverview, l2: list[Chunk]) -> list[str]:
    """모듈 지도 절을 만든다.

    심볼이 많은 파일은 접어둔다.
    "이 기능이 어느 파일에 있는가"에 답하려면 심볼 목록이 필요하지만,
    파일마다 열 몇 줄씩 펼쳐져 있으면 파일 단위 구조가 보이지 않는다.
    details 태그는 마크다운 뷰어와 브라우저 양쪽에서 동작한다.

    Args:
        overview (RepoOverview): 조립된 개요.
        l2 (list[Chunk]): 함수·클래스 청크 목록.

    Returns:
        list[str]: 마크다운 줄 목록.
    """
    by_file: dict[str, list[Chunk]] = {}
    for chunk in l2:
        by_file.setdefault(chunk.file, []).append(chunk)

    lines = []

    for file_path, _ in overview.file_map:
        symbols = by_file.get(file_path, [])
        lines.append(f"### `{file_path}`")
        lines.append("")

        if not symbols:
            lines += ["정의된 함수나 클래스가 없습니다.", ""]
            continue

        symbol_lines = format_symbol_lines(symbols)

        if len(symbols) > FOLD_THRESHOLD:
            lines.append(f"<details><summary>심볼 {len(symbols)}개</summary>")
            lines.append("")
            lines += symbol_lines
            lines.append("")
            lines.append("</details>")
        else:
            lines += symbol_lines

        lines.append("")

    return lines


def build_report(
    overview: RepoOverview,
    chunks: list[Chunk],
    llm: LLMClient,
    quirk_groups: list[QuirkGroup] | None = None,
) -> str:
    """레포 리포트를 마크다운으로 조립한다.

    Args:
        overview (RepoOverview): 조립된 개요.
        chunks (list[Chunk]): 인덱싱된 청크 목록.
        llm (LLMClient): 레포 요약 생성에 사용할 LLM 클라이언트.
        quirk_groups (list[QuirkGroup] | None): 특이 지점 그룹 목록.
            없으면 해당 절을 넣지 않는다.

    Returns:
        str: 마크다운 리포트 전문.
    """
    l2 = [c for c in chunks if c.kind != "file"]

    # 첫 줄과 본문을 분리해 한 줄 정의를 인용구로 강조한다.
    # 리포트를 훑는 사람이 가장 먼저 보는 문장이기 때문이다.
    summary = summarize_repo(overview, llm).strip()
    headline, _, body = summary.partition("\n")
    summary = f"> **{headline.strip()}**\n\n{body.strip()}"

    lines = [
        f"# {overview.name}",
        "",
        f"> `whyd report`로 생성 · {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "---",
        "",
        "## 1. 이 프로젝트는 무엇인가",
        "",
        summary,
        "",
        "---",
        "",
        "## 2. 규모",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 파일 | {overview.file_count}개 |",
        f"| 줄 | {overview.total_lines:,}줄 |",
        f"| 함수·클래스 | {overview.symbol_count}개 |",
        f"| 파일 간 참조 | {overview.internal_import_count}건 |",
        "",
        "---",
        "",
        "## 3. 외부 의존성",
        "",
    ]

    if overview.external_deps:
        lines.append("이 프로젝트가 선택해서 가져온 라이브러리입니다.")
        lines.append("면접에서 \"왜 이걸 썼나요\"를 물을 수 있는 대상입니다.")
        lines.append("")
        lines += [f"- `{dep}`" for dep in overview.external_deps]
    else:
        lines.append("서드파티 의존성이 없습니다. 표준 라이브러리만 사용합니다.")

    lines += ["", "<details><summary>표준 라이브러리</summary>", ""]
    lines.append(", ".join(f"`{d}`" for d in overview.stdlib_deps) or "없음")
    lines += ["", "</details>", "", "---", "", "## 4. 진입점", ""]

    # 확정과 추정을 구분해 표시한다. 섞으면 읽는 사람이 확신도를 오해한다.
    confirmed = [e for e in overview.entry_points if e.confirmed]
    guessed = [e for e in overview.entry_points if not e.confirmed]

    if not overview.entry_points:
        lines.append("진입점을 찾지 못했습니다. 라이브러리로만 쓰이는 코드일 수 있습니다.")
    else:
        for entry in confirmed:
            lines.append(f"- **확정** `{entry.target}` — {entry.evidence}")

        guessed_lines = [
            f"- 추정 `{e.target}` — {e.evidence}" for e in guessed
        ]

        # 확정이 있고 추정이 많을 때만 접는다.
        if confirmed and len(guessed) > ENTRY_FOLD_THRESHOLD:
            lines += [
                "",
                f"<details><summary>직접 실행 가능한 파일 {len(guessed)}개</summary>",
                "",
            ]
            lines += guessed_lines
            lines += ["", "</details>"]
        else:
            lines += guessed_lines
    lines += ["", "---", "", "## 5. 모듈 지도", ""]
    lines += format_module_map(overview, l2)

    lines += ["---", "", "## 6. 물어볼 만한 지점", ""]

    if quirk_groups:
        lines.append(
            "코드에 남아 있지만 이유는 적혀 있지 않은 지점들입니다. "
            "면접에서 \"왜 이렇게 했나요\"가 나올 자리이므로 미리 답을 준비해두면 좋습니다."
        )
        lines.append("")

        for i, group in enumerate(quirk_groups, start=1):
            lines.append(f"### {i}. {group.question}")
            lines.append("")
            lines.append("확인된 사실:")
            for quirk in group.quirks:
                lines.append(
                    f"- `{quirk.file}:{quirk.line}` — `{quirk.symbol}`"
                )
            lines.append("")
            # group.key에 백틱이 들어 있어 그대로 두면 셸에서 명령 치환으로 해석된다.
            # 복사해 붙여 쓰라고 내놓는 명령줄이므로 실행 가능한 형태여야 한다.
            plain_key = group.key.replace("`", "")
            lines.append(
                f'> 직접 물어보기: `whyd ask {overview.root} '
                f'"{group.quirks[0].symbol}은 왜 {plain_key}을 받고 안 쓰나요?"`'
            )
            lines.append("")
    else:
        lines.append("규칙으로 탐지된 지점이 없습니다.")
        lines.append("")

    lines += [
        "---",
        "",
        "## 다음으로",
        "",
        "궁금한 지점은 직접 물어볼 수 있습니다.",
        "",
        "```bash",
        f'whyd ask {overview.root} "이 함수는 왜 이렇게 짰어?"',
        "```",
        "",
    ]

    return "\n".join(lines)