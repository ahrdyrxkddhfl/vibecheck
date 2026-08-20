"""LLM을 사용해 청크별 요약을 생성한다.

요약은 검색 품질을 위해 존재한다. 사용자는 "로그인 어떻게 처리돼?"라고 묻지만
코드에는 verify_token 같은 식별자만 있고 '로그인'이라는 단어가 없다.
코드 원문을 그대로 임베딩하면 자연어 질문과 매칭되지 않으므로,
자연어 요약을 생성해 함께 임베딩하므로써 둘 사이를 연결한다.
"""

from pathlib import Path

from vibecheck.llm.base import LLMClient
from vibecheck.models import Chunk

PROMPT_DIR = Path(__file__).parent.parent / "prompts"

def load_prompt(name:str) -> str:
    """프롬프트 파일을 읽는다.

    프롬프트를 코드에 하드코딩하지 않고 파일로 분리한 이유는 반복적인 수정이 잦기 때문이다.
    파일로 두면 프롬프트만 독립적으로 편집하고 변경 이력을 추적할 수 있다.

    Args:
        name (str) : 확장자를 제외한 프롬프트 파일 이름.

    Returns:
        str: 프롬프트 내용.
    """
    return (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")

def build_user_message(chunk: Chunk) -> str:
    """요약 요청에 사용할 사용자 메시지를 구성한다.

    코드 본문을 구분자로 감싸 전달한다.
    이는 코드 내부의 텍스트가 프롬프트의 일부로 해석되는 것을 막기 위한 것으로, 
    경계를 명시해 모델이 해당 영역을 지시가 아닌 데이터로 취급하도록 유도한다.

    Args: 
        chunk (Chunk) : 요약 대상 청크.
    
    Returns:
        str : 파일 경로, 심볼명, 종류와 코드 본문을 포함한 메시지.
    """
    return (
        f"파일: {chunk.file}\n"
        f"파일: {chunk.symbol}\n"
        f"종류: {chunk.kind}\n"
        f"\n"
        f"<code>\n{chunk.code}\n</code>"
    )
def summarize(chunk:Chunk, llm: LLMClient) -> Chunk:
    """청크에 요약을 채워 반환한다.

    이미 요약이 있는 청크는 LLM을 호출하지 않고 그대로 반환한다.
    재인덱싱 시 변경되지 않은 청크의 중복 호출을 피하기 위한 것으로,
    청크 수가 많은 레포에서 비용과 시간을 크게 절감한다.

    Args:
        chunk (Chunk): 요약할 청크.
        llm (LLMClient): LLM 클라이언트. 구체 구현이 아닌 인터페이스에 의존하므로
                         테스트 시 가짜 구현을 주입할 수 있다.

    Returns:
        Chunk: summary가 채워진 청크. 입력 객체를 직접 수정한다.
    """
    if chunk.summary is not None:
        return chunk

    system = load_prompt("summarize_chunk")
    user = build_user_message(chunk)

    chunk.summary = llm.complete(system, user, max_tokens=200).strip()
    return chunk

def summarize_all(chunks: list[Chunk], llm: LLMClient) -> list[Chunk]:
    """청크 목록 전체를 순차적으로 요약한다.

    현재는 순차 처리이며, 청크 수가 많아지면 병렬화가 필요하다.
    조기 최적화를 피하기 위해 실제 병목이 확인된 뒤에 개선한다.

    Args:
        chunks (list[Chunk]): 요약할 청크 목록.
        llm (LLMClient): LLM 클라이언트.

    Returns:
        list[Chunk]: 요약이 채워진 청크 목록.
    """
    return [summarize(c, llm) for c in chunks]

if __name__ == "__main__":
    from vibecheck.core.chunker import to_chunks
    from vibecheck.core.parser import parse_file, walk
    from vibecheck.llm.anthropic import AnthropicClient

    tree, source = parse_file("sample.py")
    chunks = to_chunks(walk(tree.root_node, source), source, "sample.py")

    llm = AnthropicClient()
    for c in summarize_all(chunks, llm):
        print(f"{c.symbol:16} {c.summary}")
        