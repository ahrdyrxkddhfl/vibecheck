"""파일 하나를 가운데 두고 그 파일의 호출 관계를 조립한다.

관계도 화면이 쓰는 재료다. 처음에는 폴더를 전부 놓고 화살표를 전부 긋는
한 장짜리 그림이었는데, 모두가 쓰는 파일(models.py, prompts)에서 화살표가
사방으로 뻗어 읽을 수 없었다. 한 번에 한 파일의 이웃만 그리면 그림이
거미줄이 될 수 없고, 이웃을 눌러 가운데로 옮기며 따라갈 수 있다.

재료는 인덱싱 때 해석해둔 Chunk.calls다. 검색이 아니라 대조이므로
상위 몇 개를 고르는 일이 없고, 빠지는 것은 이름이 겹쳐 끝내 좁히지 못한
호출뿐이다.

호출을 수집하지 않는 언어(Java)는 호출 대신 타입 참조로 파일을 잇는다. 코드에
어떤 클래스 이름이 나오는지다. 인덱스에 저장해두지 않고 관계도를 열 때 파일을
읽어 센다. 저장하려면 청크 형식과 저장·복원을 모두 고쳐야 하는데, 파싱은 레포
하나에 한순간이고 파일 수정 시각을 열쇠로 캐시한다. 그래서 이 연결은 인덱싱
시점이 아니라 지금 디스크의 코드 기준이다.

접기는 여기서 하지 않는다. 몇 개를 보여줄지는 화면의 결정이고, 이 계층이
잘라서 넘기면 화면이 "더 보기"를 만들 재료가 없다.
"""

from collections import Counter, defaultdict
from pathlib import Path

from tree_sitter import Parser

from vibecheck.core.languages import LanguageSpec, spec_for
from vibecheck.models import Chunk

L2_KINDS = ("function", "method", "class")


def file_of(chunk_id: str) -> str:
    """청크 식별자에서 파일 경로를 떼어낸다.

    식별자는 "파일경로::심볼" 형식이다(Chunk.id). 심볼 쪽에는 "::"가
    나오지 않으므로 처음 나오는 구분자에서 자르면 된다.

    Args:
        chunk_id (str): 청크 식별자.

    Returns:
        str: 파일 경로.
    """
    return chunk_id.split("::", 1)[0]


def neighbor_files(counts: Counter) -> list[dict]:
    """이웃 파일을 호출 건수가 많은 순으로 정렬해 목록으로 만든다.

    건수 순으로 두는 이유는 화면이 앞에서부터 보여주고 뒤를 접기 때문이다.
    많이 엮인 파일이 앞에 와야 접혔을 때 가려지는 쪽이 약한 연결이 된다.
    건수가 같으면 경로 순으로 두어 실행마다 순서가 흔들리지 않게 한다.

    Args:
        counts (Counter): 파일 경로별 호출 건수.

    Returns:
        list[dict]: {"file", "count"} 목록.
    """
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"file": f, "count": n} for f, n in ordered]


_REF_CACHE: dict[tuple[str, int], Counter] = {}
"""(파일 경로, 수정 시각) -> 그 파일의 타입 참조.

관계도에서 파일을 누를 때마다 레포의 같은 언어 파일을 전부 훑으므로, 바뀌지 않은
파일은 다시 파싱하지 않는다. 수정 시각을 열쇠에 넣어 고친 파일은 새로 센다.
"""


def type_refs_of(path: Path, spec: LanguageSpec) -> Counter:
    """파일 하나의 타입 참조를 센다. 읽을 수 없으면 빈 결과다.

    Args:
        path (Path): 파일의 실제 경로.
        spec (LanguageSpec): 그 파일의 언어 설정.

    Returns:
        Counter: 타입 이름 -> 나온 횟수.
    """
    try:
        key = (str(path), path.stat().st_mtime_ns)
        if key not in _REF_CACHE:
            source = path.read_bytes()
            tree = Parser(spec.language).parse(source)
            _REF_CACHE[key] = Counter(spec.collect_type_refs(tree.root_node, source))
        return _REF_CACHE[key]
    except OSError:
        return Counter()


def type_neighbors(
    repo: Path, chunks: list[Chunk], file: str, spec: LanguageSpec
) -> tuple[Counter, Counter]:
    """타입 참조로 이 파일을 쓰는 파일과 이 파일이 쓰는 파일을 센다.

    이름에서 파일을 정하는 것은 이름이 레포에서 하나뿐일 때만이다. 다른 패키지에
    같은 이름의 클래스가 있으면 어느 쪽인지 짐작하지 않고 뺀다. 가운데 파일의
    이름이 겹치면 이 파일을 쓰는 쪽도 정할 수 없어 비운다.

    대상은 인덱스에 들어간 같은 언어 파일이다. 인덱싱에서 뺀 폴더의 파일은
    이웃으로 나오지 않는다.

    Args:
        repo (Path): 레포 루트.
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
        file (str): 가운데 파일의 레포 기준 상대 경로.
        spec (LanguageSpec): 가운데 파일의 언어 설정.

    Returns:
        tuple[Counter, Counter]: (이 파일을 쓰는 파일별 횟수, 이 파일이 쓰는 파일별 횟수).
    """
    files = sorted(
        {c.file for c in chunks if c.kind == "file" and spec_for(c.file) is spec}
    )

    by_name: dict[str, list[str]] = defaultdict(list)
    for f in files:
        by_name[Path(f).stem].append(f)
    unique = {name: fs[0] for name, fs in by_name.items() if len(fs) == 1}

    calls: Counter = Counter()
    for name, n in type_refs_of(repo / file, spec).items():
        target = unique.get(name)
        if target and target != file:
            calls[target] += n

    called_by: Counter = Counter()
    center = Path(file).stem
    if unique.get(center) == file:
        for other in files:
            if other == file:
                continue
            n = type_refs_of(repo / other, spec).get(center, 0)
            if n:
                called_by[other] += n

    return called_by, calls


def file_relations(
    chunks: list[Chunk], file: str, repo: Path | None = None
) -> dict | None:
    """한 파일을 가운데 둔 호출 관계를 조립한다.

    파일 단위(이웃 파일)와 심볼 단위(각 함수를 부르는 곳과 부르는 대상)를
    함께 돌려준다. 화면은 위에 이웃 그림을, 아래에 심볼 목록을 그리는데
    둘을 따로 요청하면 한 번 누를 때 두 번 기다리게 된다.

    같은 파일 안의 호출은 이웃 파일 집계에서 뺀다. 그림에서 자기 자신으로
    돌아오는 화살표는 정보가 없고 칸만 차지한다. 심볼 목록에는 그대로 남긴다.
    한 파일 안에서 무엇이 무엇을 부르는지는 그 파일을 읽을 때 필요한 정보다.

    호출을 수집하지 않고 타입 참조를 셀 수 있는 언어면 이웃 파일을 타입 참조로
    채운다. 심볼 목록의 부르는 것·불리는 곳은 비어 있다. 메서드 단위 호출은
    여전히 분석하지 않는다.

    Args:
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
        file (str): 가운데 둘 파일의 레포 기준 상대 경로.
        repo (Path | None): 레포 루트. 타입 참조를 세려면 파일을 읽어야 해서
            필요하다. 없으면 타입 참조를 세지 않는다.

    Returns:
        dict | None: 아래 키를 가진 딕셔너리. 그 파일에 함수·클래스가
            하나도 없으면 None.
            file (str): 가운데 파일.
            called_by (list[dict]): 이 파일을 부르는 다른 파일.
            calls (list[dict]): 이 파일이 부르는 다른 파일.
            symbols (list[dict]): 이 파일의 심볼. 줄 순서다.
            relation (str | None): 이웃을 무엇으로 이었는지. "calls"는 호출,
                "types"는 타입 참조, None은 잇지 않았다는 뜻이다. None이면
                called_by와 calls가 비어 있는 것은 연결이 없어서가 아니라 재지
                않아서다. 화면이 셋을 구분해 말할 수 있게 싣는다.
            calls_analyzed (bool): relation이 "calls"인지. 앞선 화면 코드와의
                호환을 위해 남긴다.
            language (str): 이 파일의 언어 표시 이름.
    """
    l2 = [c for c in chunks if c.kind in L2_KINDS]
    mine = sorted((c for c in l2 if c.file == file), key=lambda c: c.start_line)
    if not mine:
        return None

    mine_ids = {c.id for c in mine}

    # 들어오는 방향은 저장돼 있지 않다. calls는 나가는 방향만 담으므로
    # 전체를 한 번 훑어 거꾸로 모은다.
    callers: dict[str, list[str]] = {cid: [] for cid in mine_ids}
    called_by = Counter()
    for c in l2:
        for target in c.calls:
            if target in mine_ids:
                callers[target].append(c.id)
                if c.file != file:
                    called_by[c.file] += 1

    calls = Counter(
        file_of(t) for c in mine for t in c.calls if file_of(t) != file
    )

    symbols = [
        {
            "id": c.id,
            "symbol": c.symbol,
            "kind": c.kind,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "summary": c.summary or "",
            "calls": list(c.calls),
            "called_by": sorted(callers[c.id]),
        }
        for c in mine
    ]

    spec = spec_for(file)

    relation = None
    if spec and spec.collect_calls:
        relation = "calls"
    elif spec and spec.collect_type_refs and spec.type_named_files and repo is not None:
        relation = "types"
        called_by, calls = type_neighbors(repo, chunks, file, spec)

    return {
        "file": file,
        "called_by": neighbor_files(called_by),
        "calls": neighbor_files(calls),
        "symbols": symbols,
        "relation": relation,
        "calls_analyzed": relation == "calls",
        "language": spec.label if spec else "",
    }
