"""수집한 호출을 정의 한 곳으로 좁혀 호출 그래프를 만든다.

파서는 "foo가 불렸다"까지만 안다. 그 foo가 어느 파일의 어느 정의인지는
레포 전체의 심볼 목록이 있어야 정해진다. 이 모듈이 그 대조를 맡는다.

검색으로는 답할 수 없는 질문이 있어서 만들었다.
`store.prune()` 같은 메서드 호출에는 클래스 이름이 코드에 없다.
`VectorStore.prune은 어디서 호출되나요`로 물으면 그 문자열이 소스에 존재하지 않아
임베딩도 문자열 매칭도 닿지 못한다. 실제로 유일한 호출처를 하나도 찾지 못했다.
변수 이름과 클래스를 잇는 일은 검색이 아니라 대조의 몫이다.

갈리지 않으면 찍지 않고 버린다. 후보가 둘인데 반반 확률로 고르면
절반이 틀린 화살표가 되어 검색 근거로 들어가고, 없던 오류를 새로 만든다.
빠뜨리는 것보다 틀린 것을 내놓는 쪽이 나쁘다.
"""

from collections import defaultdict

from vibecheck.models import CallSite, Symbol

BUILTIN_METHODS = {
    # 컨테이너
    "add", "append", "extend", "insert", "remove", "pop", "clear",
    "get", "keys", "values", "items", "update", "setdefault", "copy",
    "sort", "reverse", "count", "index",
    # 문자열
    "join", "split", "splitlines", "strip", "lstrip", "rstrip",
    "replace", "format", "startswith", "endswith", "lower", "upper",
    "encode", "decode", "find",
    # 파일·경로
    "read", "write", "close", "open", "read_text", "write_text",
    "read_bytes", "exists", "resolve", "expanduser", "mkdir", "glob",
    "is_file", "is_dir", "unlink", "relative_to",
    # 그 외 흔한 것
    "run", "main", "start", "stop", "send", "next", "group", "match",
    "search", "commit", "execute", "fetchall", "fetchone", "connect",
}
"""우리 심볼과 이름이 겹쳐도 붙이지 않는 이름.

파이썬 내장이나 표준 라이브러리에서 흔한 메서드다.
`seen.add()`가 `VectorStore.add`로 붙는 것을 막는다.
1판에서 실제로 그렇게 붙어 없는 호출 관계가 그려졌다.

진짜 호출 몇 개를 잃는다. `VectorStore.add`를 부르는 자리가 여기에 걸린다.
그래도 버리는 쪽을 택한다. 가짜 화살표는 답변의 근거로 들어가
사용자가 코드를 확인하러 갔을 때 그런 호출이 없다는 것을 발견하게 한다.
없는 정보보다 틀린 정보가 비싸다.
"""


def qualify(rel: str, symbol: Symbol) -> str:
    """심볼을 청크 식별자와 같은 형식의 이름으로 만든다.

    `Chunk.id`가 "파일경로::심볼명" 형식이고 `Chunk.symbol`이 소속을 포함하므로
    같은 규칙으로 조립한다. 형식이 어긋나면 해석 결과를 청크에 담을 때
    가리키는 대상을 찾지 못한다.

    Args:
        rel (str): 레포 루트 기준 상대 경로.
        symbol (Symbol): 대상 심볼.

    Returns:
        str: "파일경로::소유자.이름" 형식의 식별자.
    """
    owner = f"{symbol.parent}." if symbol.parent else ""
    return f"{rel}::{owner}{symbol.name}"


def build_definitions(
    symbols_by_file: dict[str, list[Symbol]]
) -> dict[str, list[tuple[str, Symbol]]]:
    """이름에서 그 이름을 가진 정의들로 가는 표를 만든다.

    대조의 출발점이다. 이름 하나에 정의가 하나뿐이면 바로 정해지고,
    여럿이면 좁히는 규칙으로 넘어간다.

    Args:
        symbols_by_file (dict[str, list[Symbol]]): 파일 경로 -> 심볼 목록.

    Returns:
        dict[str, list[tuple[str, Symbol]]]: 이름 -> [(파일 경로, 심볼)].
    """
    defs: dict[str, list[tuple[str, Symbol]]] = defaultdict(list)
    for rel, symbols in symbols_by_file.items():
        for symbol in symbols:
            defs[symbol.name].append((rel, symbol))
    return dict(defs)


def resolve(
    call: CallSite,
    caller_file: str,
    caller_parent: str | None,
    defs: dict[str, list[tuple[str, Symbol]]],
    imports_by_file: dict[str, list[str]],
) -> tuple[str | None, str]:
    """호출된 이름을 정의 한 곳으로 좁힌다.

    규칙을 좁은 순서로 밟는다. 앞의 규칙이 더 확실하므로 먼저 시도한다.

    1. 유일 — 그 이름의 정의가 레포에 하나뿐이다. 대부분이 여기서 끝난다.
    2. 같은클래스 — `self.foo()`는 자기 클래스 안을 먼저 본다.
       self는 자기 자신이므로 다른 파일의 같은 이름보다 우선한다.
    3. 같은파일 — 부르는 파일 안에 정의가 하나뿐이다.
    4. import대조 — 부르는 파일이 가져온 모듈에 있는 것만 남긴다.
       `cli.py`의 `store.prune()`이 이 규칙으로 갈렸다. prune은 Manifest에도
       VectorStore에도 있지만 cli.py는 VectorStore만 import한다.
       장부 관리는 indexer가 안에서 하므로 cli가 Manifest를 직접 쓸 일이 없다.

    넷으로도 갈리지 않으면 버린다. 같은 `prune`이라도 indexer.py에서 부른 것은
    그 파일이 둘 다 import해 끝내 모호로 남았다. 찍지 않는 것이 규칙이다.

    Args:
        call (CallSite): 해석할 호출.
        caller_file (str): 부르는 쪽 파일의 상대 경로.
        caller_parent (str | None): 부르는 심볼의 상위 클래스 이름.
        defs (dict[str, list[tuple[str, Symbol]]]): build_definitions의 결과.
        imports_by_file (dict[str, list[str]]): 파일 경로 -> import한 모듈 이름.

    Returns:
        tuple[str | None, str]: (가리키는 식별자, 적용된 규칙 이름).
            좁히지 못하면 (None, 버린 사유).
    """
    if call.name in BUILTIN_METHODS:
        return None, "내장이름"

    candidates = defs.get(call.name)
    if not candidates:
        return None, "외부"

    if len(candidates) == 1:
        rel, symbol = candidates[0]
        return qualify(rel, symbol), "유일"

    if call.receiver == "self" and caller_parent:
        same_class = [
            (rel, s)
            for rel, s in candidates
            if rel == caller_file and s.parent == caller_parent
        ]
        if len(same_class) == 1:
            rel, symbol = same_class[0]
            return qualify(rel, symbol), "같은클래스"

    same_file = [(rel, s) for rel, s in candidates if rel == caller_file]
    if len(same_file) == 1:
        rel, symbol = same_file[0]
        return qualify(rel, symbol), "같은파일"

    modules = imports_by_file.get(caller_file, [])
    reachable = [
        (rel, s) for rel, s in candidates if _is_imported(rel, modules)
    ]
    if len(reachable) == 1:
        rel, symbol = reachable[0]
        return qualify(rel, symbol), "import대조"

    return None, "모호"


def _is_imported(rel: str, modules: list[str]) -> bool:
    """그 파일이 import 목록 중 하나로 가리켜지는지 본다.

    양쪽 끝을 다 대조하는 이유는 기준점이 실행 위치에 따라 달라지기 때문이다.
    같은 파일이 `vibecheck.core.parser`로도 `core.parser`로도 적힐 수 있다.

    Args:
        rel (str): 후보 정의가 있는 파일의 상대 경로.
        modules (list[str]): 부르는 파일이 import한 모듈 이름 목록.

    Returns:
        bool: 가리켜지면 True.
    """
    module = rel[:-3].replace("/", ".") if rel.endswith(".py") else rel
    for name in modules:
        if module == name or module.endswith("." + name.split(".")[-1]):
            return True
        if name.endswith(module):
            return True
    return False


def build_call_map(
    symbols_by_file: dict[str, list[Symbol]],
    calls_by_file: dict[str, list[tuple[CallSite, Symbol]]],
    imports_by_file: dict[str, list[str]],
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """부르는 심볼에서 불리는 심볼로 가는 표를 만든다.

    파일 단위로 할 수 없는 계산이다. "이 이름의 정의가 하나뿐인가"는
    레포 전체를 훑은 뒤에야 답할 수 있어, 인덱싱 루프가 끝난 자리에서 부른다.

    자기 자신을 부르는 것은 담지 않는다. 재귀는 실행 흐름의 정보지만
    "어디서 쓰이는가"의 답은 아니고, 화살표로 그리면 자기로 도는 고리가 된다.

    Args:
        symbols_by_file (dict[str, list[Symbol]]): 파일 경로 -> 심볼 목록.
        calls_by_file (dict[str, list[tuple[CallSite, Symbol]]]):
            파일 경로 -> [(호출, 그 호출을 감싸는 심볼)].
        imports_by_file (dict[str, list[str]]): 파일 경로 -> import한 모듈 이름.

    Returns:
        tuple[dict[str, list[str]], dict[str, int]]:
            (부르는 식별자 -> 불리는 식별자 목록, 규칙별 집계).
            집계는 유일·같은파일 같은 적용 규칙과 외부·모호 같은 사유를 함께 센다.
            해석률이 떨어지면 규칙을 손볼 자리를 찾는 근거가 된다.
    """
    defs = build_definitions(symbols_by_file)
    edges: dict[str, set[str]] = defaultdict(set)
    stats: dict[str, int] = defaultdict(int)

    for rel, entries in calls_by_file.items():
        for call, holder in entries:
            target, rule = resolve(call, rel, holder.parent, defs, imports_by_file)
            stats[rule] += 1

            if target is None:
                continue

            caller = qualify(rel, holder)
            if target != caller:
                edges[caller].add(target)

    return (
        {caller: sorted(targets) for caller, targets in edges.items()},
        dict(stats),
    )
