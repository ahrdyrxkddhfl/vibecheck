"""LLM 제공자 인터페이스.

요약, 리포트, 생성, 질의응답 등에서 사용하는 LLM 호출을 추상화한다.
구체 구현(Anthropic, OpenAI, 로컬 모델 등)을 직접 참조하지 않고
이 인터페이스에만 의존함으로써, 제공자를 교체해도 상위 로직을 수정하지 않아도 되게 한다.
테스트 시 가짜 구현을 주입할 수 있다는 이점도 있다.
"""

from abc import ABC, abstractmethod

class LLMClient(ABC):
    """LLM 호출의 공통 계약"""

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        """프롬프트를 전달하고 응답 텍스트를 받는다.

        Args:
            system (str) : 모델의 역할과 규칙을 정의하는 시스템 프롬프트.
            user (str) : 실제 요청 내용
            max_tokens (int) : 응답 최대 토큰 수.
        Returns:
            str: 모델이 생성한 텍스트.
        """
        ...