"""Anthropic Claude API 클라이언트 구현."""

import os

from anthropic import Anthropic
from dotenv import find_dotenv, load_dotenv

from vibecheck.llm.base import LLMClient
from vibecheck.llm.errors import MissingAPIKey


def load_env() -> None:
    """.env 파일에서 API 키 같은 설정을 환경변수로 읽어 온다.

    먼저 명령을 실행한 폴더에서 위로 올라가며 찾고, 없으면 이 코드 파일이 있는
    폴더에서 위로 올라가며 찾는다.

    인자 없는 load_dotenv()는 이 코드 파일의 위치에서만 찾는다. 편집 모드
    (pip install -e .)에서는 코드가 레포 안에 있어 레포의 .env를 찾지만, 패키지로
    설치하면 코드가 가상환경의 site-packages 안에 있어 사용자가 만든 .env를 끝내
    찾지 못했다(2026-09-23, 깨끗한 가상환경에 휠을 설치해 재현). 그래서 실행한 폴더를
    먼저 본다. 코드 위치도 계속 보는 것은 레포 밖에서 whyd를 실행하던 편집 모드
    사용법을 깨지 않기 위해서다.

    이미 설정된 환경변수는 덮어쓰지 않는다. 셸에서 export한 키가 .env보다 앞선다.
    두 곳에 모두 .env가 있으면 먼저 읽은 실행 폴더 쪽 값이 남는다.
    """
    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv()


load_env()

SUMMARY_MODEL = "claude-haiku-4-5-20251001"
"""청크 요약과 리포트의 요약 문장에 쓰는 모델.

요약은 청크마다 한 번씩, 레포 하나에 수백 번 부른다. 판단이 단순하고 횟수가
많아 싸고 빠른 모델을 쓴다.
"""

ANSWER_MODEL = "claude-sonnet-4-6"
"""질문 답변과 채점에 쓰는 모델.

코드를 근거로 답하고, 답변을 코드와 대조하는 판단이 필요해 상위 모델을 쓴다.

모델 이름은 이 한 곳에만 둔다. CLI와 웹 라우터에 따로 적혀 있으면 한쪽만 바꿨을 때
같은 질문과 같은 답변이 두 경로에서 다른 모델로 답해지고 채점되어, 결과를 비교할
수 없게 된다.
"""

class AnthropicClient(LLMClient):
    """Claude API를 통해 텍스트를 생성한다.

    Attributes:
        model (str): 사용할 모델 식별자. 청크 요약처럼 단순하고 반복이 많은 작업에는
        저렴하고 빠른 모델을 쓰고, 리포트 생성처럼 품질이 중요한 작업에는 상위 모델을 쓴다.
    """

    def __init__(self, model: str = SUMMARY_MODEL):
        """클라이언트를 초기화한다.

        Args:
            model (str) : 모델 식별자.
        Raises:
            MissingAPIKey: 환경변수에 API 키가 없을 때. ValueError의 하위다.
        """
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise MissingAPIKey(
                "ANTHROPIC_API_KEY가 설정되지 않았습니다. "
                ".env 파일을 확인하세요."
            )

        self.client = Anthropic(api_key=api_key)
        self.model = model

    def complete(self, system, user, max_tokens = 1024) -> str:
        """프롬프트를 전달하고 응답 텍스트를 받는다.

        Args:
            system (str) : 시스템 프롬프트.
            user (str) : 사용자 메시지.
            max_tokens (int) : 응답 최대 토큰 수.

        Returns:
            str: 응답 텍스트. 여러 텍스트 블록이 오면 이어 붙인다.
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        )