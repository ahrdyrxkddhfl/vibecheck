"""LLM을 사용해 청크별 요약을 생성한다.

요약은 검색 품질을 위해 존재한다. 사용자는 "로그인 어떻게 처리돼?"라고 묻지만
코드에는 verify_token 같은 식별자만 있고 '로그인'이라는 단어가 없다.
코드 원문을 그대로 임베딩하면 자연어 질문과 매칭되지 않으므로,
자연어 요약을 생성해 함께 임베딩하므로써 둘 사이를 연결한다.
"""

from concurrent.futures import ThreadPoolExecutor

from vibecheck.llm.base import LLMClient
from vibecheck.models import Chunk
from vibecheck.prompts import load_prompt


def build_user_message(chunk: Chunk) -> str:
    """요약 요청에 사용할 사용자 메시지를 구성한다.

    코드 본문을 구분자로 감싸 전달한다.
    이는 코드 내부의 텍스트가 프롬프트의 일부로 해석되는 것을 막기 위한 것으로,
    경계를 명시해 모델이 해당 영역을 지시가 아닌 데이터로 취급하도록 유도한다.

    import 문을 함께 전달하는 이유는 청크가 함수 본문만 담기 때문이다.
    파일 상단의 import가 잘려나가면 모델이 어떤 라이브러리를 쓰는지 알 수 없어
    추측으로 채운다. 실제로 tree-sitter 기반 파서가 "파이썬 파서"로 요약되어
    해당 청크가 검색에서 누락되는 사례가 확인되었다.

    Args:
        chunk (Chunk): 요약 대상 청크.

    Returns:
        str: 파일 경로, 심볼명, 종류, import 목록과 코드 본문을 포함한 메시지.
    """
    parts = [
        f"파일: {chunk.file}",
        f"심볼: {chunk.symbol}",
        f"종류: {chunk.kind}",
    ]

    # import가 없는 청크도 있으므로 있을 때만 넣는다.
    if chunk.imports:
        parts.append("\n이 파일의 import:")
        parts.extend(chunk.imports)

    parts.append(f"\n<code>\n{chunk.code}\n</code>")

    return "\n".join(parts)
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

SUMMARY_WORKERS = 4
"""파일 하나의 청크를 동시에 요약할 요청 수.

작게 잡는다. 분당 한도는 초 단위로 나뉘어 적용될 수 있어 몰아 보내면 한도에
걸리고, 사용 이력이 짧은 조직은 기본보다 낮은 한도에서 시작한다. 요금은 동시성과
무관하게 청크 수만큼 나가므로, 빨라지는 것 말고 얻을 것이 없는 자리에서 한도를
시험할 이유가 없다.

4는 claim-trace의 파일별 청크 수(79개 파일, 중앙값 3개)로 계산해 정했다. 요청이
하나에 1초라 치면 순차 362초가 121초(3.0배)로 준다. 8로 늘려도 90초(4.0배)라
한도 위험에 비해 얻는 것이 적다.
"""


def summarize_all(
    chunks: list[Chunk], llm: LLMClient, workers: int = SUMMARY_WORKERS
) -> list[Chunk]:
    """청크 목록 전체를 요약한다. 요약이 필요한 것은 동시에 보낸다.

    순차로 두던 때의 기준은 "실제 병목이 확인된 뒤에 개선한다"였다. 청크 362개인
    claim-trace를 처음 인덱싱하며 몇 분이 걸린 것이 그 확인이다.

    병렬은 이 함수가 받은 청크, 즉 파일 하나 안에서만 한다. 파일을 넘나들면 더
    빨라지지만(동시 4개에서 3.0배가 4.0배) 인덱서가 파일마다 끝내고 저장하는
    흐름을 뜯어야 한다. 그 저장이 끊겨도 요약을 잃지 않게 하는 장치라 지킨다.

    요청 하나가 실패하면 나머지 대기 중인 요청을 취소하고 예외를 올린다. 이미
    나간 요청은 끝날 때까지 기다리지 않는다. Ctrl+C가 같은 길로 오므로, 기다리면
    끊은 뒤에도 그 파일의 남은 요청이 다 나간다.

    Args:
        chunks (list[Chunk]): 요약할 청크 목록. 요약이 이미 있는 것은 건너뛴다.
        llm (LLMClient): LLM 클라이언트. 여러 스레드가 함께 쓴다.
        workers (int): 동시에 보낼 요청 수. 1이면 순차로 처리한다.

    Returns:
        list[Chunk]: 입력과 같은 목록. 청크 객체에 요약을 직접 채운다.
    """
    todo = [c for c in chunks if c.summary is None]

    if workers <= 1 or len(todo) <= 1:
        for c in todo:
            summarize(c, llm)
        return chunks

    pool = ThreadPoolExecutor(max_workers=min(workers, len(todo)))
    try:
        futures = [pool.submit(summarize, c, llm) for c in todo]
        # 결과는 청크에 직접 채워지므로 값은 필요 없다. 기다리면서 예외만 받는다.
        for future in futures:
            future.result()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return chunks

if __name__ == "__main__":
    from vibecheck.core.chunker import to_chunks
    from vibecheck.core.parser import parse_file, walk
    from vibecheck.llm.anthropic import AnthropicClient

    tree, source = parse_file("tests/fixtures/sample.py")
    chunks = to_chunks(walk(tree.root_node, source), source, "tests/fixtures/sample.py")

    llm = AnthropicClient()
    for c in summarize_all(chunks, llm):
        print(f"{c.symbol:16} {c.summary}")
        