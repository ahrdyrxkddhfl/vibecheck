"""네거티브 컨트롤 채점 결과를 exp_a_control.md에 채워 넣는다.

파일을 통째로 다시 쓰지 않고 채점 칸만 교체하는 이유는
LLM 답변 원문이 채점의 근거이기 때문이다.
재작성 과정에서 한 글자라도 달라지면 무엇을 보고 점수를 줬는지 확인할 수 없게 된다.

빈 채점 칸을 위에서부터 순서대로 채운다.
문항 블록이 Q01부터 차례로 배치되어 있어 등장 순서가 곧 문항 번호이기 때문이다.
"""

import re
import sys
from pathlib import Path

TARGET = Path("experiments/exp_a_control.md")

EMPTY_BLOCK = re.compile(
    r"- 점수\(0~2\): *\n- 플래그\(H/A/-\): *\n- 메모: *\n"
)

DEFAULT = ("0", "A", "코드 없이 기권. in_index=Y이므로 0점.")

GRADES = {
    "Q04": (
        "1",
        "A",
        "기권했으나 CTXD_API_KEY를 정확히 언급. 프로젝트명 대문자 + _API_KEY는 "
        "파이썬 관례라 코드 없이도 유추 가능. 본 측정에서 이 문항을 맞혀도 "
        "1점은 관례로 딸 수 있던 몫임에 주의.",
    ),
    "Q07": (
        "1",
        "A",
        "in_index=N 기권. '코드 중복 제거' 일반론까지 도달했으나 "
        "client.py, _run 등 이 레포 고유의 근거는 전무.",
    ),
    "Q08": (
        "1",
        "A",
        "in_index=N 기권. 보안상 분리라는 관행을 근거와 함께 제시. "
        "다만 clear_api_key 동작 등 실제 코드 근거는 없음.",
    ),
    "Q09": (
        "1",
        "A",
        "in_index=N 기권. 하위 호환성 추정에 근거를 밝힘.",
    ),
}

SUMMARY = """## 집계

| 유형 | 점수 | 만점 |
|---|---|---|
| 개념 (Q01~Q03) | 0 | 6 |
| 식별자 (Q04~Q06) | 1 | 6 |
| 왜 (Q07~Q09) | 3 | 3 |
| 관계 (Q10~Q12) | 0 | 6 |
| 사실 (Q13~Q15) | 0 | 6 |
| **합계** | **4** | **27** |

- 환각(H): 0건
- 기권(A): 15건 (전 문항)

### 판정

모델은 ctxd를 학습하지 않았다. 매 문항에서 저장소를 모른다고 명시했고
없는 심볼을 지어낸 사례가 없다. 기억 오염이 실증적으로 배제되었으며,
본 측정에서 얻는 점수는 대부분 검색의 기여로 해석할 수 있다.

### 기록해둘 단서 둘

1. **Q04는 관례만으로 유추 가능하다.** 환경변수 이름이 프로젝트명 대문자 +
   _API_KEY인 것은 파이썬 관행이다. 본 측정에서 맞혀도 검색의 공로는 1점뿐이다.

2. **"왜" 유형은 점수로 비교할 수 없다.** 만점이 1점인데 컨트롤이 이미 1점을
   받았으므로 차이가 0으로 고정된다. 이는 채점표의 결함이 아니라
   "버린 대안은 코드에 흔적을 남기지 않는다"는 실험 B 결론의 논리적 귀결이다.
   따라서 이 유형은 점수가 아니라 답변 문장의 질로 관찰한다.

   관찰 지점: 본 측정이 client.py, _run 같은 이 레포 고유의 심볼을 근거로 대면서
   기권하는가. 컨트롤은 그 이름들을 알지 못하므로 그렇게 쓸 수 없다.
   구조(코드에 있는 것)를 설명하고 선택 이유(코드에 없는 것)만 기권하는지를 본다.
"""


def fill(text: str) -> str:
    """빈 채점 칸을 순서대로 채운 문서를 돌려준다.

    Args:
        text (str): 원본 문서 전문.

    Returns:
        str: 채점이 채워진 문서.

    Raises:
        ValueError: 빈 채점 칸 수가 15개가 아닐 때.
    """
    blanks = EMPTY_BLOCK.findall(text)
    if len(blanks) != 15:
        raise ValueError(f"빈 채점 칸이 15개가 아닙니다: {len(blanks)}개")

    counter = {"i": 0}

    def replace(_match: re.Match) -> str:
        """등장 순서를 문항 번호로 삼아 채점 내용을 돌려준다."""
        counter["i"] += 1
        qid = f"Q{counter['i']:02d}"
        score, flag, memo = GRADES.get(qid, DEFAULT)
        return f"- 점수(0~2): {score}\n- 플래그(H/A/-): {flag}\n- 메모: {memo}\n"

    return EMPTY_BLOCK.sub(replace, text)


def main() -> None:
    """파일을 읽어 채점을 채우고 집계를 덧붙인다."""
    text = TARGET.read_text(encoding="utf-8")

    # 두 번 돌리면 이미 채워진 칸을 다시 덮어써 채점 이력이 뭉개진다.
    if "## 집계" in text:
        print("이미 채점된 파일입니다. 중복 실행을 막습니다.")
        return

    filled = fill(text).rstrip() + "\n\n" + SUMMARY
    TARGET.write_text(filled, encoding="utf-8")
    print(f"채점 완료: {TARGET}")


if __name__ == "__main__":
    if not TARGET.exists():
        print(f"파일이 없습니다: {TARGET}")
        sys.exit(1)
    main()