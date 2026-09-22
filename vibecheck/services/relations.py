"""파일 하나를 가운데 두고 그 파일의 호출 관계를 조립한다.

관계도 화면이 쓰는 재료다. 처음에는 폴더를 전부 놓고 화살표를 전부 긋는
한 장짜리 그림이었는데, 모두가 쓰는 파일(models.py, prompts)에서 화살표가
사방으로 뻗어 읽을 수 없었다. 한 번에 한 파일의 이웃만 그리면 그림이
거미줄이 될 수 없고, 이웃을 눌러 가운데로 옮기며 따라갈 수 있다.

재료는 인덱싱 때 해석해둔 Chunk.calls다. 검색이 아니라 대조이므로
상위 몇 개를 고르는 일이 없고, 빠지는 것은 이름이 겹쳐 끝내 좁히지 못한
호출뿐이다.

접기는 여기서 하지 않는다. 몇 개를 보여줄지는 화면의 결정이고, 이 계층이
잘라서 넘기면 화면이 "더 보기"를 만들 재료가 없다.
"""

from collections import Counter

from vibecheck.core.languages import spec_for
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


def file_relations(chunks: list[Chunk], file: str) -> dict | None:
    """한 파일을 가운데 둔 호출 관계를 조립한다.

    파일 단위(이웃 파일)와 심볼 단위(각 함수를 부르는 곳과 부르는 대상)를
    함께 돌려준다. 화면은 위에 이웃 그림을, 아래에 심볼 목록을 그리는데
    둘을 따로 요청하면 한 번 누를 때 두 번 기다리게 된다.

    같은 파일 안의 호출은 이웃 파일 집계에서 뺀다. 그림에서 자기 자신으로
    돌아오는 화살표는 정보가 없고 칸만 차지한다. 심볼 목록에는 그대로 남긴다.
    한 파일 안에서 무엇이 무엇을 부르는지는 그 파일을 읽을 때 필요한 정보다.

    Args:
        chunks (list[Chunk]): 인덱싱된 전체 청크 목록.
        file (str): 가운데 둘 파일의 레포 기준 상대 경로.

    Returns:
        dict | None: 아래 키를 가진 딕셔너리. 그 파일에 함수·클래스가
            하나도 없으면 None.
            file (str): 가운데 파일.
            called_by (list[dict]): 이 파일을 부르는 다른 파일.
            calls (list[dict]): 이 파일이 부르는 다른 파일.
            symbols (list[dict]): 이 파일의 심볼. 줄 순서다.
            calls_analyzed (bool): 이 파일의 언어가 호출을 수집하는지.
                False면 called_by와 calls가 비어 있는 것은 연결이 없어서가
                아니라 재지 않아서다. 화면이 둘을 구분해 말할 수 있게 싣는다.
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

    return {
        "file": file,
        "called_by": neighbor_files(called_by),
        "calls": neighbor_files(calls),
        "symbols": symbols,
        "calls_analyzed": bool(spec and spec.collect_calls),
        "language": spec.label if spec else "",
    }
