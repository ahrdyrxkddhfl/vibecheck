"""요약을 동시에 보내되 한도를 지키고, 실패를 삼키지 않는지 확인한다."""

import threading
import time

import pytest

from vibecheck.core.summarizer import summarize_all
from vibecheck.models import Chunk


class SlowLLM:
    """요청마다 잠깐 기다리며 동시에 몇 개가 들어와 있는지 잰다.

    Attributes:
        peak (int): 한 순간에 동시에 처리 중이던 요청의 최대 수.
        calls (int): 받은 요청 수.
        fail_on (int | None): 이 번째 요청에서 예외를 던진다.
    """

    def __init__(self, fail_on: int | None = None) -> None:
        """측정 상태를 초기화한다.

        Args:
            fail_on (int | None): 실패시킬 요청 번째. None이면 실패하지 않는다.
        """
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.calls = 0
        self.fail_on = fail_on

    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        """동시 처리 수를 기록하고 잠깐 기다린 뒤 고정 요약을 돌려준다.

        Args:
            system (str): 시스템 프롬프트. 쓰지 않는다.
            user (str): 사용자 메시지. 쓰지 않는다.
            max_tokens (int): 최대 출력 토큰 수. 쓰지 않는다.

        Returns:
            str: 고정 요약.

        Raises:
            RuntimeError: fail_on 번째 요청일 때.
        """
        with self.lock:
            self.calls += 1
            n = self.calls
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(0.05)
            if n == self.fail_on:
                raise RuntimeError("한도 초과")
            return "요약"
        finally:
            with self.lock:
                self.active -= 1


def chunks(n: int, done: int = 0) -> list[Chunk]:
    """청크 n개를 만들고 앞의 done개는 요약이 있는 것으로 둔다.

    Args:
        n (int): 청크 수.
        done (int): 이미 요약된 것으로 둘 개수.

    Returns:
        list[Chunk]: 청크 목록.
    """
    return [
        Chunk(file="a.py", symbol=f"f{i}", kind="function", start_line=i, end_line=i,
              code="", summary="캐시" if i < done else None)
        for i in range(n)
    ]


def test_동시에_보내되_정한_수를_넘지_않는다():
    """열 개를 동시 4개로 보내면 한순간 최대 4개이고 모두 채워진다."""
    llm = SlowLLM()
    out = chunks(10)
    summarize_all(out, llm, workers=4)

    assert llm.peak == 4
    assert [c.summary for c in out] == ["요약"] * 10


def test_이미_요약된_것은_보내지_않는다():
    """캐시로 채워진 청크는 요청하지 않고 그대로 둔다."""
    llm = SlowLLM()
    out = chunks(6, done=4)
    summarize_all(out, llm, workers=4)

    assert llm.calls == 2
    assert [c.summary for c in out] == ["캐시"] * 4 + ["요약"] * 2


def test_요청이_실패하면_예외를_올린다():
    """병렬로 돌려도 실패가 묻히지 않아야 인덱서가 그 파일을 저장하지 않는다."""
    with pytest.raises(RuntimeError):
        summarize_all(chunks(8), SlowLLM(fail_on=3), workers=4)
