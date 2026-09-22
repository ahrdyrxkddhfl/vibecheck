"""인덱싱된 코드베이스에 대해 질문에 답한다.

벡터 검색으로 관련 청크를 찾고, 그 코드를 근거로 LLM이 답변을 생성한다.
레포 전체를 LLM에 넣지 않고 검색으로 좁히는 이유는 두 가지다.
첫째, 큰 레포는 컨텍스트 한계를 넘는다.
둘째, 무관한 코드가 많이 섞이면 답변 품질이 떨어진다.
"""

import json
import re

from vibecheck.prompts import load_prompt
from vibecheck.llm.base import LLMClient
from vibecheck.models import Chunk
from vibecheck.store.vector import VectorStore

def build_context(chunks: list[Chunk]) -> str:
    """검색된 청크들을 LLM에 전달할 컨텍스트 문자열로 조립한다.

    각 청크를 구분자로 감싸 경계를 명확히 한다.
    여러 조각을 이어 붙일 때 경계가 모호하면 서로 다른 함수의 코드가 하나로 읽힐 수 있고,
    코드 내부의 텍스트가 지시문으로 해석될 여지도 생긴다.

    Args:
        chunks (list[Chunk]): 컨텍스트에 포함할 청크 목록.

    Returns:
        str: 조립된 컨텍스트 문자열.
    """
    blocks = []
    for c in chunks:
        blocks.append(
            f"<chunk>\n"
            f"파일: {c.file}\n"
            f"심볼: {c.symbol} ({c.kind})\n"
            f"위치: {c.start_line}-{c.end_line}행\n"
            f"요약: {c.summary or '없음'}\n"
            f"\n"
            f"{c.code}\n"
            f"</chunk>"
        )
    return "\n\n".join(blocks)

CODE_KINDS = ("file", "function", "method", "class")
"""줄 범위로 코드를 담는 청크 종류. 문서와 설정 청크는 범위가 겹쳐도 코드 중복이 아니다."""


def covers(outer: Chunk, inner: Chunk, file_is_code: bool = True) -> bool:
    """outer가 inner의 코드를 통째로 담고 있는지 판정한다.

    같은 파일에서 inner의 줄 범위가 outer의 줄 범위 안에 들어가면 inner의 코드는
    outer에 이미 실려 있다. 클래스와 그 메서드, 파일 원문과 그 안의 함수가 이 경우다.

    채점처럼 파일 청크를 개요로 줄여 보내는 곳에서는 파일 청크가 코드를 담지 않는다.
    그때는 file_is_code를 False로 넘겨 파일 청크를 이 판정에서 뺀다.

    Args:
        outer (Chunk): 담는 쪽 후보.
        inner (Chunk): 담기는 쪽 후보.
        file_is_code (bool): 파일 청크가 원문 그대로 실리는지.

    Returns:
        bool: outer가 inner를 담으면 True. 같은 청크면 False.
    """
    if outer is inner or outer.file != inner.file:
        return False
    if outer.kind not in CODE_KINDS or inner.kind not in CODE_KINDS:
        return False
    if not file_is_code and "file" in (outer.kind, inner.kind):
        return False
    return outer.start_line <= inner.start_line and inner.end_line <= outer.end_line


def drop_contained(chunks: list[Chunk], file_is_code: bool = True) -> list[Chunk]:
    """다른 청크 안에 통째로 들어 있는 청크를 빼고, 담는 쪽을 남긴다.

    근거 목록에 클래스와 그 메서드가 함께 뽑히면 메서드 코드가 두 번 실린다.
    이 레포와 claim-trace로 질문 여섯 개를 재니 셋에서 이런 겹침이 생겼고, 생기면
    근거 8칸 중 2~4칸이 이미 실린 코드였다. 근거 수는 고정이라 그만큼 다른 근거가
    들어갈 자리를 잃는다.

    담는 쪽을 남긴다. 안쪽 코드를 이미 다 담고 있어 잃는 정보가 없다. 반대로 하면
    담는 쪽에만 있던 코드(뽑히지 않은 다른 메서드, 필드)를 잃는다.

    담는 쪽이 뒤에 나오면 안쪽 중 가장 앞의 자리에 넣는다. 앞에 올수록 관련이 깊다고
    고른 순서라, 맨 뒤로 보내면 그 판단을 뒤집게 된다.

    Args:
        chunks (list[Chunk]): 관련 순으로 정렬된 근거 후보.
        file_is_code (bool): 파일 청크가 원문 그대로 실리는지. covers 참고.

    Returns:
        list[Chunk]: 겹침을 없앤 목록. 순서는 위의 규칙대로다.
    """
    kept: list[Chunk] = []

    for chunk in chunks:
        if any(covers(k, chunk, file_is_code) for k in kept):
            continue

        inside = [i for i, k in enumerate(kept) if covers(chunk, k, file_is_code)]
        if inside:
            at = inside[0]
            kept = [k for i, k in enumerate(kept) if i not in inside]
            kept.insert(at, chunk)
        else:
            kept.append(chunk)

    return kept


def pick_distinct(
    picked: list[Chunk], candidates: list[Chunk], top_k: int
) -> list[Chunk]:
    """재정렬이 고른 것에서 겹침을 빼고, 모자라면 나머지 후보로 채워 top_k개를 만든다.

    재정렬에게 몇 개 더 고르게 해도 칸이 모자랄 수 있다. 재정렬이 한두 파일 안에서만
    고르면 더 고른 것까지 같은 클래스의 메서드라 겹침으로 함께 빠진다. claim-trace의
    "개입 규칙은 어떻게 평가되나요?"에서 12개를 골랐는데 겹침을 빼니 4개가 남았다.

    모자란 칸은 재정렬이 고르지 않은 후보를 검색 순서대로 이어 채운다. 재정렬이 고른
    것은 순서 그대로 앞에 둔다. 후보는 top_k의 몇 배로 뽑아두므로 모자라지 않는다.

    Args:
        picked (list[Chunk]): 재정렬이 관련 순으로 고른 청크.
        candidates (list[Chunk]): 재정렬에 넘긴 후보 전체. 검색 순서다.
        top_k (int): 남길 청크 수.

    Returns:
        list[Chunk]: 서로 겹치지 않는 청크 top_k개. 후보가 모자라면 그보다 적다.
    """
    found = drop_contained(picked)
    if len(found) < top_k:
        rest = [c for c in candidates if all(c is not p for p in picked)]
        found = drop_contained(found + rest)
    return found[:top_k]


KIND_QUOTAS = [
    (None, 4),
    (["file"], 2),
    (["doc"], 1),
    (["config"], 1),
]
"""검색 결과에서 청크 종류별로 확보할 자리.

같은 판에서 경쟁시키면 함수·클래스 청크가 전부 차지한다. 이 레포에서
155개 중 121개가 L2라 상위 8칸에 나머지가 낄 자리가 없었다.

증상은 일관됐다. "어떤 벡터 DB를 쓰나요"에 VectorStore 클래스가 1위로
오고 정작 ChromaDB라고 적힌 문서는 오지 않는다. 개념을 물으면 그 개념을
구현한 코드가 먼저 오고 그 개념을 설명한 글이 밀린다.

pyproject.toml 청크의 kind가 file이라 설정 파일은 L1과 같은 몫을 쓴다.
따로 떼면 몫이 하나뿐인 종류가 생기는데, 설정 파일이 없는 레포에서는
그 자리가 통째로 낭비된다.

첫 줄이 None인 것은 종류를 가리지 않는다는 뜻이다. 이 자리는 원래의
검색 결과 그대로이고, 나머지가 그 위에 얹히는 구조다.
"""

def is_identifier_query(question: str) -> bool:
    """질의가 식별자 하나로만 되어 있는지 판정한다.

    문자열 경로를 모든 질의에 붙이면 자연어 질의가 망가진다.
    "요약을 캐시할 때 왜 해시를 쓰나요?"에 문자열 매칭이 끼면
    '해시'가 든 무관한 청크가 앞자리를 먹어 지금 3등인 답을 밀어낸다.
    그래서 문자열 경로는 벡터가 실제로 못 하는 질의에만 연다.

    밑줄이나 대소문자 혼용을 요구하는 이유는 평범한 영단어를 걸러내기
    위해서다. "authentication"은 공백 없는 아스키지만 식별자가 아니라
    자연어 질의이고, 벡터가 처리해야 할 몫이다.

    이 조건이면 "prune" 같은 순수 소문자 이름은 걸러진다. 의도한
    것이다. 식별자가 섞인 자연어 질의는 지금도 2등으로 닿으므로
    고칠 대상이 아니다.

    Args:
        question (str): 사용자 질의.

    Returns:
        bool: 식별자 질의로 볼 수 있으면 True.
    """
    q = question.strip()

    if len(q) < 2 or not all(c.isalnum() and c.isascii() or c == "_" for c in q):
        return False

    return "_" in q or (q.lower() != q and q.upper() != q)

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
"""질의에서 낱말 하나를 떼어내는 무늬.

파이썬 이름 규칙과 같다. 숫자로 시작하지 않고 글자·숫자·밑줄로 이어진다.
"""


def extract_identifiers(question: str) -> list[str]:
    """질의 안에 섞인 식별자를 뽑는다.

    질의 전체가 식별자일 때만 문자열 경로를 열면 실제 사용을 놓친다.
    "child_by_field_name 어디서 써?"는 공백이 있어 식별자 질의가
    아니지만, 벡터로 검색하면 사용처 세 곳 중 하나만 걸린다.
    quirks.py의 collect_used_names, function_params처럼 이름만 닮은
    것이 근거 여덟 자리 중 넷을 먹기 때문이다.

    is_identifier_query와 같은 조건을 낱말 하나하나에 적용한다.
    밑줄이나 대소문자 혼용을 요구하므로 "어디서"나 "authentication"
    같은 평범한 낱말은 걸리지 않는다.

    Args:
        question (str): 사용자 질의.

    Returns:
        list[str]: 식별자로 볼 수 있는 낱말 목록. 등장 순서를 지킨다.
    """
    found = []

    for token in IDENTIFIER_PATTERN.findall(question):
        if len(token) < 2 or token in found:
            continue

        if "_" in token or (token.lower() != token and token.upper() != token):
            found.append(token)

    return found

def search_by_identifier(
    question: str, chunks: list[Chunk], limit: int = 3
) -> list[Chunk]:
    """코드 원문에 그 문자열이 있는 청크를 등장 횟수 순으로 찾는다.

    등장 횟수로 정렬하는 이유는 언급과 사용을 가르기 위해서다.
    독스트링에 이름만 적어둔 자리는 대개 한 번 나오고, 실제로 부르는
    코드는 여러 번 나오거나 최소한 같은 횟수다. 정렬 없이 순회 순서로
    집으면 벡터 검색이 저지른 실수를 그대로 반복한다. 측정에서 실제
    사용처(18등)보다 독스트링 언급(4등)이 앞선 그 일이다.

    summary를 보지 않고 code만 보는 이유도 같다. "이 함수는 X를 쓴다"는
    요약문이 걸리면 다시 언급이 사용을 이긴다.

    Args:
        question (str): 식별자 질의.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
        limit (int): 반환할 최대 개수. 종류별 몫을 지나치게 밀어내지
            않도록 상한을 둔다.

    Returns:
        list[Chunk]: 등장 횟수가 많은 순의 청크 목록.
    """
    # 파일 청크는 파일 전체를 담아 등장 횟수가 구조적으로 높다.
    # 함수 청크와 같은 자로 재면 흔한 이름일수록 앞자리를 독식한다.
    # top_k로 재보니 파일 청크 둘이 1·2등을 먹고 정의부가 5등으로 밀렸다.
    # 파일 청크는 벡터 경로로도 잡히므로 여기서는 뺀다.
    # 낱말 경계를 요구한다. 부분 문자열로 세면 짧은 이름이 긴 이름 안에
    # 걸려 엉뚱한 쪽이 이긴다. ctxd에서 "Client"로 찾으면 AsyncClient
    # 코드에도 걸리는데, 짧은 이름일수록 빽빽하게 나와 client.py가
    # 여섯 자리 중 여섯을 먹고 AsyncClient 클래스 청크가 밀려났다.
    pattern = re.compile(rf"\b{re.escape(question)}\b")
    scored = [
        (len(pattern.findall(c.code)), c) for c in chunks if c.kind != "file"
    ]
    hits = [(n, c) for n, c in scored if n > 0]
    hits.sort(key=lambda pair: pair[0], reverse=True)

    return [c for _, c in hits[:limit]]

CALLER_LIMIT = 10
"""한 심볼에 대해 보여줄 호출처 수의 상한.

전부 싣는 것이 원칙이지만 널리 쓰이는 유틸리티는 호출처가 수십 개가 된다.
프롬프트가 호출 목록으로 채워지면 정작 코드를 읽을 자리가 줄어든다.
"""


def find_callers(question: str, chunks: list[Chunk]) -> dict[str, list[str]]:
    """질문에 이름이 나온 심볼을 부르는 곳을 대조로 찾는다.

    검색이 아니라 전체 대조다. 인덱싱 때 이미 해석해둔 호출 관계를
    거꾸로 훑으므로 상위 몇 개를 고르는 일이 없고, 놓치는 것은
    이름이 겹쳐 끝내 좁히지 못한 호출뿐이다.

    이것이 필요한 이유는 검색이 원리적으로 못 하는 질의가 있기 때문이다.
    `store.prune()`으로 적힌 자리에는 VectorStore라는 글자가 없다.
    `VectorStore.prune은 어디서 호출되나요`로 물으면 그 문자열이 소스에
    존재하지 않아 임베딩도 문자열 매칭도 닿지 못하고, 실제로 유일한
    호출처를 하나도 찾지 못했다.

    심볼 전체 이름으로만 대조한다. `prune`처럼 소유자를 뗀 이름은 받지 않는다.
    이 레포에는 prune이 Manifest에도 VectorStore에도 있어 어느 쪽을 묻는지
    정할 수 없다. 둘 다 보여주면 사용자가 없는 호출 관계를 믿게 된다.
    좁히지 못하면 이 경로를 열지 않고 기존 검색에 맡긴다.

    Args:
        question (str): 사용자 질문.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.

    Returns:
        dict[str, list[str]]: 불리는 심볼 식별자 -> 부르는 심볼 식별자 목록.
            질문에 심볼 이름이 없으면 빈 딕셔너리.
    """
    # \b를 쓰지 않는다. 파이썬 정규식에서 한글은 단어 문자라
    # "VectorStore.prune은"처럼 조사가 바로 붙으면 경계가 성립하지 않아
    # 긴 이름이 통째로 탈락한다. 영어 기준으로 맞는 규칙이 한글 질문에서 깨진다.
    # 앞뒤가 식별자로 이어지지만 않으면 된다. 점은 이어짐으로 보지 않으므로
    # VectorStore.prune을 물으면 VectorStore도 함께 걸리는데, 그것은 아래에서 거른다.
    named = {
        c.id: c.symbol
        for c in chunks
        if c.kind not in ("file", "doc", "config")
        and re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(c.symbol)}(?![A-Za-z0-9_])", question
        )
    }
    if not named:
        return {}

    # 긴 이름에 짧은 이름이 포함되면 짧은 쪽은 버린다.
    # VectorStore.prune을 물었는데 VectorStore까지 남으면 클래스를 쓰는 곳이
    # 대조 결과에 실려, 묻지 않은 답이 한 문단 따라붙는다.
    symbols = set(named.values())
    named = {
        cid: sym
        for cid, sym in named.items()
        if not any(other != sym and sym in other for other in symbols)
    }

    result: dict[str, list[str]] = {}
    for target_id in named:
        callers = sorted(c.id for c in chunks if target_id in c.calls)
        if callers:
            result[target_id] = callers[:CALLER_LIMIT]

    return result


def format_callers(callers: dict[str, list[str]]) -> str:
    """호출처 대조 결과를 프롬프트에 실을 문장으로 만든다.

    검색 근거와 구분해서 싣는다. 근거 청크는 질문과 가까운 것을 골라 온
    추정이지만 이쪽은 레포 전체를 대조한 결과다. 확신의 근거가 다른 둘을
    섞으면 모델이 같은 무게로 다루게 된다.

    빠질 수 있다는 것도 함께 적는다. 이름이 겹쳐 좁히지 못한 호출은
    찍지 않고 버렸으므로 목록이 전부가 아닐 수 있다.

    Args:
        callers (dict[str, list[str]]): find_callers의 결과.

    Returns:
        str: 프롬프트에 넣을 문장. 결과가 비었으면 빈 문자열.
    """
    if not callers:
        return ""

    lines = [
        "인덱싱 때 레포 전체를 대조해 얻은 호출 관계입니다.",
        "검색 결과가 아니라 대조 결과이므로 아래 목록은 그대로 단정해도 됩니다.",
        "다만 이름이 겹쳐 어느 정의를 가리키는지 좁히지 못한 호출은 빠져 있습니다.",
        "",
    ]
    for target, who in callers.items():
        lines.append(f"{target} 를 호출하는 곳:")
        lines += [f"  - {caller}" for caller in who]
        lines.append("")

    return "\n".join(lines)


def search_by_kind(
    question: str,
    chunks: list[Chunk],
    store: VectorStore,
    top_k: int,
) -> list[Chunk]:
    """청크 종류별로 자리를 나눠 검색한 뒤 합친다.

    몫을 채우지 못한 자리는 비워두지 않고 종류를 가리지 않는 검색으로
    메운다. 문서가 없는 레포에서 그 자리가 놀면 근거가 그만큼 줄어든다.

    Args:
        question (str): 사용자 질문.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
        store (VectorStore): 검색에 사용할 벡터 저장소.
        top_k (int): 근거로 사용할 청크 수.

    Returns:
        list[Chunk]: 합쳐진 근거 청크 목록.
    """
    by_id = {c.id: c for c in chunks}

    found: list[Chunk] = []
    seen: set[str] = set()

    # 식별자는 벡터가 받아내지 못한다. 코드 원문에 그 이름이 있는데도
    # 19등, 130등으로 밀려 재정렬 후보에도 들지 못하는 것을 측정했다.
    # 문자열로 찾은 것을 앞자리에 먼저 담아 후보에 확실히 올린다.
    #
    # 질의 전체가 식별자일 때만 열면 실제 사용을 놓친다.
    # "child_by_field_name 어디서 써?"로 물으면 사용처 셋 중 하나만
    # 걸려 답변이 "한 번 사용됩니다"로 나왔다. 낱말 단위로 뽑는다.
    for identifier in extract_identifiers(question):
        for chunk in search_by_identifier(identifier, chunks):
            if chunk.id in seen:
                continue

            seen.add(chunk.id)
            found.append(chunk)

            # take와 같은 상한을 둔다. 식별자 하나당 셋이므로 여럿이
            # 섞인 질의에서 top_k를 넘길 수 있다. 실제로는 식별자들이
            # 같은 자리를 가리켜 중복 제거에 걸리므로 넘치는 일이
            # 드물지만, 함수가 약속한 수를 지키게 해둔다.
            if len(found) >= top_k:
                return found

    def take(kinds: list[str] | None, limit: int) -> None:
        """한 종류에서 limit개까지 골라 담는다."""
        for hit in store.search(question, top_k=limit, kinds=kinds):
            chunk = by_id.get(hit["id"])
            if chunk is None or chunk.id in seen:
                continue

            seen.add(chunk.id)
            found.append(chunk)

            if len(found) >= top_k:
                return

    for kinds, quota in KIND_QUOTAS:
        take(kinds, quota)
        if len(found) >= top_k:
            return found

    # 남은 자리는 종류를 가리지 않고 채운다.
    if len(found) < top_k:
        take(None, top_k)

    return found

RERANK_SPARE = 4
"""재정렬에게 top_k보다 더 고르게 할 수.

재정렬이 고른 것 중에서 겹치는 청크를 빼고 top_k로 자른다. 딱 top_k만 고르게 하면
겹침을 뺀 자리가 빈 채로 남는다. 빈 자리를 무엇으로 채울지도 재정렬의 판단을 따르려고
미리 몇 개 더 고르게 한다. 재보니 겹침은 한 번에 최대 4칸이었다.
"""

CANDIDATE_MULTIPLIER = 4
"""재정렬에 넘길 후보를 top_k의 몇 배로 뽑을지.

임베딩은 후보를 좁히는 데까지는 성공하나 그 안에서 순서를 매기지 못한다.
"코드를 어떻게 파싱하나요"에서 상위 셋의 거리가 0.6608, 0.6612, 0.6649로
차이가 0.004였고, 정답인 parser.py가 3위라 잘렸다. 문서에서도 같은 일이
있었다. 후보를 넓히면 정답이 그 안에 들어오고, 고르는 일은 LLM이 한다.

3배로 시작했으나 4배로 넓혔다. 두 파일의 관계를 묻는 질문에서 한쪽이
24, 25위에 있어 딱 한 끗 차이로 잘렸다. 이름이 비슷한 파일이 있으면
(index_access와 indexer) 임베딩이 둘을 구분하지 못해 한쪽이 관련
청크를 몰고 상위를 채운다.

넓히는 것이 공짜인 이유는 재정렬이 뒤에 있기 때문이다. 후보가 늘어도
최종 근거 수는 top_k로 고정되므로 답변 품질이 흔들리지 않는다.
재정렬 이전이라면 후보를 넓히는 것이 곧 근거를 넓히는 것이었다.
"""


def rerank(
    question: str,
    candidates: list[Chunk],
    llm: LLMClient,
    top_k: int,
) -> list[Chunk]:
    """후보 청크를 질문에 대한 유용성 순으로 다시 고른다.

    임베딩이 못 하는 일을 맡는다. 벡터 검색은 주제가 비슷한 것과 답이
    들어 있는 것을 구분하지 못한다. 진입점을 물으면 EntryPoint 클래스가
    1위로 오는데, 그것은 진입점을 다루는 코드일 뿐 진입점이 어디인지는
    말해주지 않는다.

    청크 전문이 아니라 요약과 심볼 이름만 넘긴다. 20개 전문을 넣으면
    프롬프트가 거대해지고, 고르는 데 필요한 것은 "이 청크에 무엇이
    들어 있는가"이지 코드 자체가 아니다.

    실패하면 원래 순서 그대로 자른다. 재정렬은 순서를 개선하는 층이고,
    이것 때문에 질문 자체가 실패하면 잃는 것이 더 크다.

    Args:
        question (str): 사용자 질문.
        candidates (list[Chunk]): 임베딩 검색이 뽑은 후보 목록.
        llm (LLMClient): 재정렬에 사용할 LLM 클라이언트.
        top_k (int): 최종적으로 남길 청크 수.

    Returns:
        list[Chunk]: 재정렬된 청크 목록. 실패하면 후보 앞에서 top_k개.
    """
    if len(candidates) <= top_k:
        return candidates

    lines = [
        f"{i}. [{c.kind}] {c.symbol} — {c.summary or '요약 없음'}"
        for i, c in enumerate(candidates, start=1)
    ]
    user = (
        f"질문: {question}\n\n"
        f"고를 개수: {top_k}\n\n"
        f"후보:\n" + "\n".join(lines)
    )

    try:
        raw = llm.complete(load_prompt("rerank"), user, max_tokens=300)
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1:
            return candidates[:top_k]

        picked = json.loads(raw[start : end + 1]).get("selected", [])
    except Exception:
        return candidates[:top_k]

    found: list[Chunk] = []
    seen: set[int] = set()

    for n in picked:
        # 범위 밖 번호와 중복은 버린다. 모델이 없는 번호를 만들거나
        # 같은 것을 두 번 고르는 경우가 있다.
        if not isinstance(n, int) or not 1 <= n <= len(candidates):
            continue
        if n in seen:
            continue

        seen.add(n)
        found.append(candidates[n - 1])

        if len(found) >= top_k:
            break

    # 모델이 요청한 개수보다 적게 골랐으면 원래 순서로 채운다.
    # 근거 수가 조건마다 달라지면 답변 품질 비교가 불가능해진다.
    for i, chunk in enumerate(candidates, start=1):
        if len(found) >= top_k:
            break
        if i not in seen:
            found.append(chunk)

    return found

def answer(
    question: str,
    chunks: list[Chunk],
    store: VectorStore,
    llm: LLMClient,
    top_k: int = 8,
) -> tuple[str, list[Chunk]]:
    """질문에 대한 답변과 근거 청크를 반환한다.

    벡터 검색은 정답 하나를 맞히는 것이 아니라 후보를 좁히는 역할을 한다.
    상위 top_k개를 모두 전달하면 그 중 관련 있는 것을 LLM이 판단하므로,
    검색 1위가 정답이 아니어도 답변은 정확할 수 있다.

    Args:
        question (str): 사용자 질문.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
            검색 결과의 id로 코드 본문을 찾기 위해 사용한다.
        store (VectorStore): 검색에 사용할 벡터 저장소.
        llm (LLMClient): 답변 생성에 사용할 LLM 클라이언트.
        top_k (int): 컨텍스트에 포함할 청크 수.
            실험 A3에서 5에서 8로 늘렸을 때 답변 점수가 21에서 23으로 올랐다.
            정답이 큰 함수 안에 있어 상위 5개에 들지 못하던 경우가 해소됐다.
            ctxd 규모(67청크)에서 관찰된 값이므로 일반적 최적값은 아니다.

    Returns:
        tuple[str, list[Chunk]]: 답변 텍스트와 근거로 사용된 청크 목록.
            근거를 함께 반환하는 이유는 사용자가 답변의 출처를 직접 확인할 수 있어야 하기 때문이다.
            LLM답변은 검증 가능해야 한다.
    """
    candidates = search_by_kind(question, chunks, store, top_k * CANDIDATE_MULTIPLIER)
    # 겹치는 청크를 뺀 뒤 자르므로, 재정렬에게는 몇 개 더 고르게 한다.
    # 그래도 모자라면 나머지 후보로 채운다(pick_distinct).
    picked = rerank(question, candidates, llm, top_k + RERANK_SPARE)
    found = pick_distinct(picked, candidates, top_k)

    if not found:
        return "관련된 코드를 찾지 못했습니다.", []

    system = load_prompt("answer_question")

    # 대조 결과를 코드 앞에 둔다. 뒤에 두면 긴 코드 블록에 묻히고,
    # 이 질문에서 가장 확실한 사실이 가장 늦게 읽힌다.
    parts = [f"질문: {question}", ""]

    callers = format_callers(find_callers(question, chunks))
    if callers:
        parts += [callers, ""]

    parts += ["참고할 코드:", "", build_context(found)]
    user = "\n".join(parts)

    return llm.complete(system, user, max_tokens=2000), found

if __name__ == "__main__":
    import sys

    from vibecheck.llm.anthropic import AnthropicClient
    from vibecheck.services.indexer import index_repo

    target = "."
    question = sys.argv[1] if len(sys.argv) > 1 else "파일 수집은 어떻게 이루어지나요?"

    llm = AnthropicClient(model="claude-sonnet-4-6")
    chunks = index_repo(target, llm, verbose=True)

    store = VectorStore()
    store.add(chunks)

    print(f"\n{'=' * 50}")
    print(f"Q. {question}\n")

    text, sources = answer(question, chunks, store, llm)
    print(text)

    print(f"\n{'-' * 50}")
    print("근거: ")
    for c in sources:
        print(f"    {c.file}:{c.start_line}-{c.end_line}    {c.symbol}")