"""프롬프트 파일을 담고 읽어주는 패키지.

읽는 함수를 프롬프트 파일과 같은 곳에 둔다. 이전에는 요약기 안에 있어서
Q&A와 채점기가 프롬프트 하나 읽으려고 요약기를 import해야 했다.
쓰지 않는 모듈에 의존하면 그 모듈이 바뀔 때 영향 범위를 잘못 읽게 된다.
"""

from pathlib import Path

PROMPT_DIR = Path(__file__).parent
"""프롬프트 파일이 있는 디렉토리.

이 파일 자신이 그 디렉토리 안에 있으므로 부모를 거슬러 오르지 않는다.
"""


def load_prompt(name: str) -> str:
    """프롬프트 파일을 읽는다.

    프롬프트를 코드에 하드코딩하지 않고 파일로 분리한 이유는 수정이 잦기
    때문이다. 파일로 두면 프롬프트만 독립적으로 편집하고 변경 이력을
    추적할 수 있다.

    Args:
        name (str): 확장자를 제외한 프롬프트 파일 이름.

    Returns:
        str: 프롬프트 내용.
    """
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")