"""Anthropic Claude API 클라이언트 구현."""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

from vibecheck.llm.base import LLMClient

load_dotenv()

class AnthropicClient(LLMClient):
    """Claude API를 통해 텍스트를 생성한다.

    Attributes:
        model (str): 사용할 모델 식별자. 청크 요약처럼 단순하고 반복이 많은 작업에는
        저렴하고 빠른 모델을 쓰고, 리포트 생성처럼 품질이 중요한 작업에는 상위 모델을 쓴다.
    """

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        """클라이언트를 초기화한다.

        Args:
            model (str) : 모델 식별자.
        Raises:
            ValueError: 환경변수에 API 키가 없을 때.
        """
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY가 설정되지 않았습니다."
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