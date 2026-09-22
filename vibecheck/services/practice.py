"""사용자가 작성한 면접 답변을 코드 근거와 대조해 채점한다.

이 프로젝트에서 처음으로 사용자 텍스트를 입력으로 받는 기능이다.
채점자 LLM은 정답을 모른다. "왜 이렇게 짰는가"류 질문은 정답이 코드에
남아 있지 않기 때문이다. 따라서 채점의 기준은 내용의 정답 여부가 아니라
검색으로 뽑은 근거 청크와 답변이 어떤 관계에 있는가이다.

질문과 답변으로 각각 검색해 합친다.
처음에는 질문만 썼다. 답변을 쿼리에 섞으면 답변이 틀렸을 때 검색이
그 방향으로 끌려갈 것을 우려했기 때문이다.

실제로 확인한 것은 다른 문제였다. 단정형 오답은 질문만으로도 걸러졌고,
막힌 쪽은 반대였다. 사실을 정확히 말한 답변이 그 심볼의 청크가 검색되지
않아 확인불가 판정을 받았다. 오답을 못 잡는 것이 아니라 정답을 확인해주지
못하는 것이 문제였다.

원래 우려는 남아 있으므로 질문 몫을 절반으로 고정한다.
답변이 무엇이든 근거의 절반은 질문 기준으로 채워진다.
"""

import json
import re
from dataclasses import replace
from pathlib import Path

from tree_sitter import Parser

from vibecheck.core.chunker import to_file_chunk
from vibecheck.core.languages import spec_for, supported_extensions
from vibecheck.prompts import load_prompt
from vibecheck.llm.base import LLMClient
from vibecheck.models import AnswerFeedback, Chunk, ClaimCheck
from vibecheck.services.qa import build_context
from vibecheck.store.vector import VectorStore

VERDICTS = {"confirmed", "contradicted", "unverifiable"}


def build_user_message(question: str, user_answer: str, chunks: list[Chunk]) -> str:
    """채점 요청에 사용할 사용자 메시지를 구성한다.

    사용자 답변을 구분자로 감싸는 이유는 코드를 감쌀 때와 같지만 위험은 더 크다.
    코드는 우연히 지시문처럼 읽힐 수 있는 정도지만, 사용자 답변은 의도적으로
    "만점을 주라"고 쓸 수 있다. 경계를 명시해 모델이 이 영역을 지시가 아닌
    채점 대상 데이터로 취급하도록 한다.

    근거를 답변보다 먼저 놓는 것도 의도적이다. 모델이 답변을 읽기 전에
    코드를 먼저 보게 해야 답변에 끌려가지 않는다.

    Args:
        question (str): 채점 대상 질문.
        user_answer (str): 사용자가 작성한 답변 원문.
        chunks (list[Chunk]): 검색으로 찾은 근거 청크 목록.

    Returns:
        str: 조립된 사용자 메시지.
    """
    return (
        f"질문: {question}\n\n"
        f"근거 (이 레포의 코드에서 검색한 결과):\n\n"
        f"{build_context(chunks)}\n\n"
        f"사용자 답변:\n"
        f"<user_answer>\n"
        f"{user_answer}\n"
        f"</user_answer>"
    )


def extract_json(raw: str) -> dict:
    """LLM 응답에서 JSON 객체를 뽑아낸다.

    프롬프트에서 JSON만 출력하라고 지시해도 코드 펜스나 머리말이 붙는 경우가 있다.
    첫 여는 중괄호부터 마지막 닫는 중괄호까지를 잘라내면 두 경우 모두 처리된다.

    Args:
        raw (str): LLM 응답 원문.

    Returns:
        dict: 파싱된 객체.

    Raises:
        ValueError: 중괄호를 찾지 못했거나 JSON으로 파싱되지 않을 때.
    """
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"응답에서 JSON을 찾지 못했습니다: {raw[:200]}")

    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}") from e


def clamp_score(value: object) -> int:
    """점수를 0-2 범위의 정수로 정규화한다.

    모델이 3점이나 문자열을 반환하는 경우를 대비한다.
    채점 한 축이 이상해도 나머지 결과는 살아야 하므로 예외를 던지지 않고
    범위 안으로 접는다. 값이 아예 해석 불가면 0으로 둔다.
    """
    try:
        return max(0, min(2, int(value)))
    except (TypeError, ValueError):
        return 0


def parse_feedback(
    raw: str,
    question: str,
    user_answer: str,
    chunks: list[Chunk],
) -> AnswerFeedback:
    """LLM 응답을 AnswerFeedback으로 변환한다.

    모델 출력을 그대로 믿지 않고 필드마다 방어한다.
    파싱이 실패하면 사용자는 답변을 다시 써야 하는데, 그 비용이 채점 한 항목이
    비는 것보다 크다. 따라서 알 수 없는 값은 버리거나 안전한 기본값으로 대체하고
    나머지는 살린다.

    Args:
        raw (str): LLM 응답 원문.
        question (str): 채점 대상 질문.
        user_answer (str): 사용자 답변 원문.
        chunks (list[Chunk]): 채점에 사용한 근거 청크.

    Returns:
        AnswerFeedback: 채점 결과.
    """
    data = extract_json(raw)

    claims = []
    for item in data.get("claims", []):
        verdict = item.get("verdict")
        if verdict not in VERDICTS:
            # 알 수 없는 판정은 "확인 불가"로 둔다.
            # 모르는 값을 confirmed나 contradicted로 밀면 없는 사실이 생긴다.
            verdict = "unverifiable"

        claims.append(
            ClaimCheck(
                claim=str(item.get("claim", "")),
                verdict=verdict,
                hedged=bool(item.get("hedged", False)),
                evidence=item.get("evidence") or None,
                note=str(item.get("note", "")),
            )
        )

    return AnswerFeedback(
        question=question,
        user_answer=user_answer,
        claims=claims,
        specificity=clamp_score(data.get("specificity")),
        calibration=clamp_score(data.get("calibration")),
        groundedness=clamp_score(data.get("groundedness")),
        verdict_line=str(data.get("verdict_line", "")),
        revision=str(data.get("revision", "")),
        evidence_chunks=[
            f"{c.file}:{c.start_line}-{c.end_line} {c.symbol}" for c in chunks
        ],
    )

PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:"
    + "|".join(sorted(re.escape(ext.lstrip(".")) for ext in supported_extensions()))
    + r")(?![A-Za-z0-9_])"
)
"""답변에서 소스 파일 경로를 떼어내는 무늬.

"cli.py"처럼 이름만 쓴 것과 "web/routers/report.py"처럼 경로를 쓴 것을 모두 잡는다.
뒤쪽 경계를 \b로 두지 않는 이유는 한글 조사다. 파이썬 정규식은 한글을 글자로
보므로 "cli.py가"에서 y와 가 사이에 경계가 없다고 판단해 통째로 놓친다.

확장자는 지원 언어 목록에서 만든다. .py만 적어두면 Java 답변이 짚은
"RuleEvaluator.java"를 못 잡아, 파이썬에서 고친 확인불가 문제가 Java에서
그대로 되살아난다.
"""

TYPE_NAME_PATTERN = re.compile(r"(?<![A-Za-z0-9_./-])[A-Z][A-Za-z0-9_]*(?![A-Za-z0-9_])")
"""답변에서 대문자로 시작하는 이름을 떼어내는 무늬.

"RuleEvaluator가"처럼 한글 조사가 바로 붙어도 잡히도록 뒤쪽 경계를 PATH_PATTERN과
같은 방식으로 둔다. 앞쪽에 점이나 슬래시가 오면 잡지 않는다. com.a.B나 a/B처럼
경로의 한 조각인 경우라, 그 경로 전체는 PATH_PATTERN의 몫이다.

"RuleEvaluator.evaluate"처럼 뒤에 점이 오는 것은 잡는다. 메서드를 짚으면서
클래스 이름을 쓴 것이다.
"""


def find_mentioned_files(user_answer: str, chunks: list[Chunk]) -> list[Chunk]:
    """답변이 이름으로 짚은 파일의 파일 단위(L1) 청크를 찾는다.

    "cli.py가 services를 import한다"는 주장을 확인해줄 수 있는 것은 cli.py의
    파일 청크뿐이다. import 문은 함수 밖에 있어 함수 청크에는 담기지 않고,
    파일 청크 본문의 import 목록에만 있다. 그런데 벡터 검색은 파일 이름이 아니라
    문장의 뜻으로 찾으므로, 답변에 cli.py라고 적혀 있어도 그 청크를 가져오지 못했다.
    그 결과 사실을 정확히 말한 사용자가 근거 없이 단정했다는 판정을 받았다.

    사용자가 짚은 파일을 가져오는 것은 답변 쪽으로 검색이 끌려가는 것과 다르다.
    틀린 파일을 짚었다면 그 파일을 봐야 채점기가 반박할 수 있다.
    끌려가는 것이 아니라 확인하러 가는 것이다.

    이름만 써서 파일이 둘 이상 걸리면 건너뛴다. "report.py"는 services와
    web/routers에 하나씩 있다. 어느 쪽인지 짐작해 가져오면 틀렸을 때 근거
    한 자리를 버리게 되고, 그 자리는 벡터 검색이 채우는 편이 낫다.

    확장자 없이 타입 이름만 써도 파일을 찾는다. 단, 타입 이름이 곧 파일 이름이라는
    것이 언어 규칙인 경우만이다(언어 설정의 type_named_files, 지금은 Java).
    Java 답변은 "RuleEvaluator가 조건을 DB에서 읽는다"처럼 파일이 아니라 클래스를
    말하는 것이 자연스럽고, 공개 클래스는 파일 이름과 같아야 하므로 이름에서 파일이
    하나로 정해진다. 파이썬은 그런 규칙이 없어 "practice 서비스"가 어느 파일인지
    이름만으로 정할 수 없다. 규칙이 없는 곳에서 짐작하면 틀린 근거를 가져온다.

    그 이름의 파일이 레포에 없으면 아무것도 가져오지 않는다. "Spring"이나 "API"
    같은 대문자 낱말은 그래서 걸리지 않는다. 반대로 Claim.java가 있는 레포에서
    "Claim"을 일반 명사처럼 써도 그 파일을 가져오는데, 그 파일을 보고 판정하는
    것이 확인하러 가는 것의 범위 안이라 받아들인다.

    Args:
        user_answer (str): 사용자 답변 원문.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.

    Returns:
        list[Chunk]: 답변에 처음 나온 순서대로 정렬한 파일 청크 목록.
    """
    file_chunks = [c for c in chunks if c.kind == "file" and spec_for(c.file)]

    # 두 무늬로 찾은 것을 답변에 나온 자리 순으로 합친다. 근거 자리가 모자랄 때
    # 앞에 짚은 것이 남아야 한다. 무늬별로 따로 이어붙이면 경로를 쓴 것이
    # 늘 이름만 쓴 것보다 앞서게 된다.
    mentions: list[tuple[int, Chunk]] = []

    for m in PATH_PATTERN.finditer(user_answer):
        mention = m.group()
        matches = [
            c for c in file_chunks
            if c.file == mention or c.file.endswith("/" + mention)
        ]
        if len(matches) == 1:
            mentions.append((m.start(), matches[0]))

    by_type: dict[str, list[Chunk]] = {}
    for c in file_chunks:
        if spec_for(c.file).type_named_files:
            by_type.setdefault(Path(c.file).stem, []).append(c)

    for m in TYPE_NAME_PATTERN.finditer(user_answer):
        matches = by_type.get(m.group(), [])
        if len(matches) == 1:
            mentions.append((m.start(), matches[0]))

    found: list[Chunk] = []
    seen: set[str] = set()

    for _, chunk in sorted(mentions, key=lambda pair: pair[0]):
        if chunk.id in seen:
            continue
        seen.add(chunk.id)
        found.append(chunk)

    return found


def search_union(
    question: str,
    user_answer: str,
    chunks: list[Chunk],
    store: VectorStore,
    top_k: int,
) -> list[Chunk]:
    """질문과 답변으로 각각 검색해 합친다.

    질문만으로 검색하면 답변에 나온 심볼이 쿼리에 없어 그 청크가 걸리지
    않는다. 사실을 정확히 말한 답변이 "근거 청크에 없다"는 이유로
    확인불가 판정을 받는다. 실제로 tree-sitter와 프로젝트 목적에서
    이것을 확인했다.

    두 쿼리를 이어붙이지 않고 따로 검색하는 이유는 임베딩 길이 제한이다.
    max_seq_length가 128이라 답변이 길면 질문이 통째로 밀려난다.

    질문 몫을 먼저 채우고 답변 몫을 뒤에 붙인다. 답변이 틀렸을 때
    검색이 그쪽으로 끌려가는 것이 이 방식의 위험인데, 질문 몫을 고정해두면
    답변이 무엇이든 절반은 질문 기준으로 남는다.

    답변 몫에서는 답변이 이름으로 짚은 파일의 파일 청크가 벡터 검색보다 먼저
    자리를 받는다. 답변 전체를 벡터 하나로 검색하면 여러 주장의 뜻이 섞이고
    128토큰 뒤의 주장은 아예 반영되지 않는다. 의존 방향을 묻는 질문에서
    cli.py와 web/routers/report.py를 정확히 짚은 답변이 그 두 파일을 근거로
    받지 못해, 사실인 주장 일곱 중 넷이 확인불가가 됐다.

    전체 개수는 top_k를 넘기지 않는다. 근거 수가 늘면 같은 답변의 점수가
    달라지는 것을 확인했으므로, 쿼리 방식만 바뀐 비교가 되려면
    근거 수는 그대로여야 한다.

    Args:
        question (str): 채점 대상 질문.
        user_answer (str): 사용자 답변. 검색 쿼리로도 쓴다.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
        store (VectorStore): 검색에 사용할 벡터 저장소.
        top_k (int): 근거로 사용할 청크 수의 상한.

    Returns:
        list[Chunk]: 합쳐진 근거 청크 목록. 질문 기준 결과, 답변이 짚은 파일,
            답변 기준 결과 순이다.
    """
    by_id = {c.id: c for c in chunks}

    # 질문 몫을 절반으로 둔다. 홀수면 질문 쪽이 하나 더 갖는다.
    # 채점의 기준은 어디까지나 질문이고 답변은 보조 재료다.
    question_k = (top_k + 1) // 2

    found: list[Chunk] = []
    seen: set[str] = set()

    def take(chunk: Chunk | None) -> bool:
        """근거에 하나를 더하고, 상한에 닿았는지 돌려준다."""
        if chunk is None or chunk.id in seen:
            return False
        seen.add(chunk.id)
        found.append(chunk)
        return len(found) >= top_k

    if question.strip():
        for hit in store.search(question, top_k=question_k):
            if take(by_id.get(hit["id"])):
                return found

    if user_answer.strip():
        for chunk in find_mentioned_files(user_answer, chunks):
            if take(chunk):
                return found

        for hit in store.search(user_answer, top_k=top_k):
            if take(by_id.get(hit["id"])):
                return found

    return found

L2_KINDS = ("function", "method", "class")


def compact_file_chunk(chunk: Chunk, chunks: list[Chunk]) -> Chunk:
    """파일 청크를 채점기에 넘길 개요로 줄인다.

    파일 청크는 import 목록과 심볼 요약을 담은 개요로 설계됐지만,
    인덱스에서 복원할 때 줄 범위(1~끝)로 지금 파일 원문을 다시 읽어 그 자리를
    채운다. 답변이 짚은 파일을 근거로 가져오기 시작하자 원문 네 개가 통째로
    들어가, 채점 한 번의 입력이 12,709토큰에서 27,561토큰으로 늘었다.

    개요만 넣으면 입력은 9,213토큰으로 줄지만 "post_practice가 save_answer를
    부른다" 같은 주장이 세 판 모두 확인불가가 됐다. import 목록에는 모듈 이름만
    있고 함수 이름은 없기 때문이다. 인덱싱 때 해석해둔 호출 관계를 심볼마다
    한 줄씩 붙이면 10,372토큰에 그 주장이 세 판 모두 확인됐다.

    복원 경로(load_chunks)를 고치지 않고 여기서 바꾸는 이유는 범위다.
    파일 청크는 모듈 지도, 리포트, 면접 질문, 질의응답에서도 쓰이므로
    복원을 바꾸면 그 전부를 다시 확인해야 한다. 잰 것은 채점뿐이다.

    지원 언어의 파일 청크면 모두 줄인다. 파일 설명은 인덱싱 때 파일 청크를 만든
    것과 같은 함수(언어 설정의 extract_docstring)로 다시 꺼낸다. 파이썬 ast로
    따로 꺼내면 Java는 설명을 잃고, 파이썬도 인덱스의 개요와 채점기가 보는 개요가
    다른 함수로 만들어진다.

    Args:
        chunk (Chunk): 근거 청크 하나. 지원 언어의 파일 청크가 아니면 그대로 돌려준다.
        chunks (list[Chunk]): 인덱싱된 전체 청크. 같은 파일의 심볼을 찾는 데 쓴다.

    Returns:
        Chunk: 코드 자리를 개요와 호출 목록으로 바꾼 사본, 또는 원래 청크.
    """
    spec = spec_for(chunk.file)
    if chunk.kind != "file" or spec is None:
        return chunk

    members = [c for c in chunks if c.file == chunk.file and c.kind in L2_KINDS]

    # 복원된 파일 청크의 코드 자리가 지금은 원문이므로 거기서 파일 설명을
    # 다시 꺼낸다. tree-sitter는 문법 오류가 있어도 트리를 돌려주므로,
    # 설명 자리가 온전하면 그대로 꺼내고 아니면 None이 나온다.
    source = chunk.code.encode()
    tree = Parser(spec.language).parse(source)
    docstring = spec.extract_docstring(tree.root_node, source)

    rebuilt = to_file_chunk(
        members,
        chunk.file,
        chunk.end_line,
        imports=chunk.imports,
        source_text=chunk.code,
        docstring=docstring,
    )
    if rebuilt is None:
        return chunk

    code = rebuilt.code
    calls = [f" {c.symbol} -> {', '.join(c.calls)}" for c in members if c.calls]
    if calls:
        code += "\n\n각 심볼이 부르는 것:\n" + "\n".join(calls)

    return replace(chunk, code=code)


def grade(
    question: str,
    user_answer: str,
    chunks: list[Chunk],
    store: VectorStore,
    llm: LLMClient,
    top_k: int = 8,
) -> AnswerFeedback:
    """사용자 답변을 코드 근거와 대조해 채점한다.

    검색과 채점을 한 함수에서 처리하는 이유는 채점에 사용한 근거가
    반환값에 함께 남아야 하기 때문이다. 사용자가 "코드에서 확인하기"로
    넘어갈 때 채점의 출발점과 같은 청크를 봐야 피드백이 검증 가능해진다.

    Args:
        question (str): 채점 대상 질문. 검색 쿼리로도 사용된다.
        user_answer (str): 사용자가 작성한 답변.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
        store (VectorStore): 검색에 사용할 벡터 저장소.
        llm (LLMClient): 채점에 사용할 LLM 클라이언트.
        top_k (int): 근거로 사용할 청크 수. ask와 같은 값을 쓴다.
            채점 근거가 ask 답변의 근거보다 좁으면 사용자가 확인 화면에서
            채점에 없던 코드를 보게 된다.

    Returns:
        AnswerFeedback: 채점 결과. 근거 청크를 찾지 못하면 모든 점수가 0이고
            verdict_line에 그 사실이 담긴다.
    """
    found = [
        compact_file_chunk(c, chunks)
        for c in search_union(question, user_answer, chunks, store, top_k)
    ]

    if not found:
        return AnswerFeedback(
            question=question,
            user_answer=user_answer,
            verdict_line="관련된 코드를 찾지 못해 채점할 수 없습니다.",
        )

    system = load_prompt("grade_answer")
    user = build_user_message(question, user_answer, found)
    raw = llm.complete(system, user, max_tokens=2000)

    return parse_feedback(raw, question, user_answer, found)