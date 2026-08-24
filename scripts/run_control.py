"""네거티브 컨트롤: 코드 없이 질문만 던져 기준선 점수를 만든다.

실험 A는 남의 레포를 다루므로, 답이 맞았을 때 그것이 검색의 성과인지
모델이 원래 알고 있던 것인지 구분되지 않는다.
코드를 주지 않은 상태의 점수를 먼저 재두고 본 측정에서 빼야
검색이 실제로 기여한 몫이 남는다.

레포 이름을 알려주는 이유는 실제 Q&A가 답변에 파일 경로를 함께 출력하기 때문이다.
정체를 숨기고 재면 컨트롤 점수가 실제보다 낮게 나오고,
그만큼 검색의 공로가 부풀려진다. 컨트롤은 모델에게 유리하게 잡아야 안전하다.

answer_question.txt를 쓰지 않는 이유도 같다.
그 프롬프트는 제공된 코드에만 근거하라고 지시하므로 코드가 없으면 전 문항이 기권이 되고,
컨트롤 점수가 인위적으로 0에 수렴한다.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from vibecheck.llm.anthropic import AnthropicClient

QUESTIONS_PATH = Path("experiments/exp_a_questions.json")
OUTPUT_PATH = Path("experiments/exp_a_control.md")

SYSTEM = """당신은 파이썬 라이브러리에 대한 질문에 답하는 도우미입니다.

질문 대상은 GitHub의 ctxd-dev/ctxd 저장소입니다.
파이썬 SDK와 명령줄 도구를 함께 제공하는 패키지입니다.

이번에는 코드가 제공되지 않습니다. 알고 있는 지식만으로 답하세요.

규칙:
- 한국어로 답합니다.
- 아는 내용이 있으면 최대한 구체적으로 답합니다. 함수 이름, 파일 경로,
  환경변수 이름처럼 확실한 것이 있으면 그대로 말합니다.
- 확실하지 않으면 추측임을 밝히고 답합니다.
  이때 무엇을 근거로 그렇게 추측하는지 함께 적습니다.
- 전혀 짐작할 근거가 없으면 "알 수 없습니다"라고 말합니다.
- 없는 이름을 지어내지 않습니다."""


def ask(llm: AnthropicClient, question: str) -> str:
    """코드 없이 질문 하나를 던지고 답변을 받는다.

    Args:
        llm (AnthropicClient): 답변 생성에 사용할 LLM 클라이언트.
        question (str): 던질 질문.

    Returns:
        str: 답변 텍스트.
    """
    return llm.complete(SYSTEM, f"질문: {question}", max_tokens=2000)


def run() -> None:
    """질문 전체를 실행하고 채점표를 파일로 남긴다.

    한 문항이 끝날 때마다 파일에 이어 쓴다.
    15회의 API 호출 도중 하나가 실패해도 앞의 결과를 잃지 않기 위해서다.

    채점 칸을 비운 채로 출력하는 이유는 채점이 사람의 일이기 때문이다.
    답변을 읽고 옆 칸을 채우는 형태여야 터미널 출력을 옮겨 적는 과정이 사라진다.
    """
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    questions = data["questions"]

    llm = AnthropicClient(model="claude-sonnet-4-6")

    header = (
        "# 실험 A — 네거티브 컨트롤 (코드 미제공)\n\n"
        f"- 실행 시각: {datetime.now():%Y-%m-%d %H:%M}\n"
        f"- 대상: {data['target']}\n"
        "- 조건: 코드 없음. 레포 이름만 알려주고 모델의 사전지식으로만 답변\n"
        "- 채점: `exp_a_grading.md` 기준 그대로 적용\n\n"
        "> 본 측정 결과를 보기 **전에** 채점을 끝낼 것.\n"
        "> 정답을 알고 나면 이 답변들이 실제보다 그럴듯해 보인다.\n\n"
        "---\n\n"
    )
    OUTPUT_PATH.write_text(header, encoding="utf-8")

    for i, q in enumerate(questions, start=1):
        print(f"[{i}/{len(questions)}] {q['id']} ...", flush=True)

        text = ask(llm, q["question"])

        block = (
            f"## {q['id']} ({q['type']})\n\n"
            f"**질문**: {q['question']}\n\n"
            f"**정답 요지**: {q['expected']}\n\n"
            f"**근거 출처**: {q['source']}  \n"
            f"**인덱스내 근거**: {q['in_index']}\n\n"
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
    run()