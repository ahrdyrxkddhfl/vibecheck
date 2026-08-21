"""후보 레포가 실험 A에 적합한지 판정한다.

LLM API를 호출하지 않고 정적 분석만으로 레포를 평가하는 것이 목적이다.
인덱싱은 청크 수에 비례해 비용이 들기 때문에,
돈을 쓰기 전에 부적합한 후보를 걸러내는 관문이 필요하다.

1단계에서는 파싱 성공률만 측정한다.
파싱에 실패한 파일은 청크가 생성되지 않아 검색 대상에서 통째로 빠지므로,
이 비율이 낮으면 나머지 지표를 재는 것 자체가 무의미하다.
"""

import ast
import sys

from vibecheck.core.collector import collect_files, to_relative

def screen(root: str) -> None:
    """레포를 스크리닝하고 결과를 출력한다.

    실제 인덱싱과 동일한 수집 규칙(collect_files)을 사용한다.
    스크리닝이 세는 파일과 인덱싱될 파일이 다르면
    예상 비용과 실제 비용이 어긋나 판정 자체가 쓸모없어지기 때문이다.

    Args:
        root (str): 검사할 레포 루트 경로.
    """
    files = collect_files(root)

    if not files:
        print(f"수집된 .py 파일이 없습니다: {root}")
        return

    total_lines = 0
    failures: list[tuple[str, str]] = []

    for path in files:
        rel = to_relative(path, root)

        # 인코딩이 깨진 파일은 파싱 이전에 읽기부터 실패한다.
        # SyntaxError와 원인이 다르므로 구분해서 기록한다.
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            failures.append((rel, f"인코딩 오류: {e.reason}"))
            continue

        total_lines += source.count("\n") + 1

        # tree-sitter가 아니라 ast를 쓰는 이유:
        # tree-sitter는 문법 오류가 있어도 ERROR 노드를 남기고 계속 파싱하므로 실패를 감지할 수 없다.
        # 여기서 알고 싶은 것은 "이 코드가 현재 파이썬 버전에서 온전히 읽히는가"이므로 엄격한 파서가 필요하다.
        try:
            ast.parse(source)
        except SyntaxError as e:
            failures.append((rel, f"{e.msg} (line {e.lineno})"))
    parsed = len(files) - len(failures)
    rate = parsed / len(files) * 100

    print(f"\n{'=' * 50}")
    print(f"대상: {root}")
    print(f"{'=' * 50}")
    print(f"파일 수      : {len(files)}개")
    print(f"총 라인 수   : {total_lines:,}줄")
    print(f"파싱 성공    : {parsed}/{len(files)} ({rate:.1f}%)")

    if failures:
        print(f"\n실패 {len(failures)}건:")
        for rel, reason in failures:
            print(f"    - {rel}: {reason}")

    print()
    if rate >= 95:
        print("판정: 통과 - 다음 지표 측정 가능")
    else:
        print("판정: 부적합 - 파싱 실패가 많아 인덱싱 결과를 신뢰할 수 없음")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    screen(target)