"""저장된 인덱스를 꺼내오는 공통 경로.

ask, report, interview, practice가 모두 같은 일을 한다.
인덱스 경로를 계산하고, 없으면 안내하고 멈추고, 있으면 코드 본문이 채워진
청크 목록을 복원한다. 각 명령이 이 절차를 따로 갖고 있으면 인덱스 구조를
바꿀 때 네 곳을 고쳐야 하고, 한 곳을 빠뜨리면 그 명령만 조용히 다르게
동작한다.

CLI가 아니라 services에 두는 이유는 웹으로 옮길 때 그대로 쓰기 위해서다.
FastAPI 핸들러도 같은 절차가 필요하고, 그때 typer에 묶여 있으면 못 쓴다.
"""

import json
from pathlib import Path

from vibecheck.models import Chunk
from vibecheck.store.manifest import Manifest, file_hash

INDEX_DIRNAME = ".vibecheck"


class IndexNotFound(Exception):
    """대상 레포에 인덱스가 없을 때 발생한다.

    예외로 만든 이유는 호출자마다 대응이 다르기 때문이다.
    CLI는 안내 메시지를 찍고 종료하지만, 웹은 404를 반환하거나
    인덱싱을 제안하는 화면을 띄운다. 이 계층에서 화면 출력을 결정하면
    웹에서 다시 쓸 수 없다.
    """


class IndexEmpty(Exception):
    """인덱스는 있으나 복원된 청크가 하나도 없을 때 발생한다.

    인덱싱 이후 소스가 전부 바뀌었거나 인덱싱이 중간에 실패한 경우다.
    IndexNotFound와 구분하는 이유는 사용자에게 할 말이 다르기 때문이다.
    전자는 "인덱싱하세요"이고 후자는 "다시 인덱싱하세요"다.
    """


def index_paths(repo: Path) -> tuple[str, str]:
    """레포 경로로부터 캐시 장부와 벡터 저장소 경로를 만든다.

    두 경로를 한곳에서 계산하는 이유는 요약 캐시와 벡터 인덱스가 짝을 이루기 때문이다.
    한쪽만 남으면 캐시는 있는데 검색이 안 되거나 그 반대가 되어,
    실패가 조용히 진행된다.

    Args:
        repo (Path): 대상 레포 루트.

    Returns:
        tuple[str, str]: (캐시 장부 디렉토리, 벡터 저장소 디렉토리).
    """
    base = repo / INDEX_DIRNAME
    return str(base), str(base / "chroma")


def load_index_meta(persist_dir: str) -> dict:
    """장부에 기록된 인덱싱 조건을 읽는다.

    리포트와 면접 질문은 인덱싱 때와 같은 파일 목록으로 계산되어야 한다.
    사용자가 --exclude를 다시 치게 하면 빼먹었을 때 인덱스와 어긋난 숫자가
    조용히 나오고, 웹에서는 아예 전달할 방법이 없다.

    실패해도 예외를 올리지 않는다.
    조건을 모르면 기본값으로 계산될 뿐이고, 그것 때문에 인덱스를 못 여는 것은
    잃는 것이 더 크다. 1판 장부에는 이 절이 아예 없다.

    Args:
        persist_dir (str): 캐시 장부가 있는 디렉토리.

    Returns:
        dict: exclude_dirs, file_count, indexed_at을 담은 딕셔너리.
            읽지 못했으면 빈 딕셔너리.
    """
    path = Path(persist_dir) / "manifest.json"
    if not path.exists():
        return {}

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    meta = raw.get("index") if isinstance(raw, dict) else None
    return meta if isinstance(meta, dict) else {}


def changed_files(repo: Path, known_hashes: dict[str, str]) -> set[str]:
    """인덱싱 때와 내용이 달라진 파일을 찾는다.

    청크는 줄 범위만 저장하고 코드는 지금 파일에서 다시 읽는다. 그래서 인덱싱 뒤
    위쪽에 줄이 끼어들면 아래 청크들이 밀린 줄을 담는다. 파일이 짧아지는 경우만
    잡던 때는 이것을 몰랐다. 독스트링을 네 줄 늘린 models.py에서 청크 다섯 개가
    네 줄 위를 코드로 담고 있었고, 건너뛰었다고 보고된 청크는 0개였다.

    첫 줄이 그 심볼의 정의인지 보는 식으로도 잡을 수 있지만 빈틈이 있다.
    한 줄만 밀리면 첫 줄이 함수 사이의 빈 줄이 되어 정상처럼 보인다.
    인덱싱 때 장부에 적어둔 해시와 비교하면 어디가 얼마나 밀렸든 빠짐없이 잡힌다.

    장부에 없는 파일은 판단하지 않는다. README나 pyproject.toml처럼 요약 캐시를
    쓰지 않는 파일은 해시가 없고, 이 경우는 예전처럼 줄 수로만 거른다.

    Args:
        repo (Path): 대상 레포 루트.
        known_hashes (dict[str, str]): 레포 기준 상대 경로별 인덱싱 당시 해시.

    Returns:
        set[str]: 내용이 달라졌거나 읽을 수 없는 파일의 상대 경로.
    """
    changed = set()

    for rel, expected in known_hashes.items():
        try:
            if file_hash(str(repo / rel)) != expected:
                changed.add(rel)
        except OSError:
            # 사라진 파일이다. 아래에서 어차피 건너뛰지만 여기서도 같은 판정을 낸다.
            changed.add(rel)

    return changed


def load_chunks(
    repo: Path, persist_dir: str, changed: set[str] | None = None
) -> tuple[list[Chunk], int]:
    """저장된 인덱스로부터 코드 본문이 채워진 청크 목록을 복원한다.

    벡터 저장소에는 임베딩 텍스트와 메타데이터만 있고 코드 원문이 없다.
    답변 생성에는 원문이 필요하므로 소스 파일에서 줄 범위를 다시 읽는다.

    파일이 사라졌거나 줄 수가 줄었거나 내용이 바뀌었으면 그 청크를 건너뛴다.
    바뀐 파일의 청크는 틀린 줄을 담고 있을 수 있어, 틀린 코드를 근거로 답하느니
    빼는 편이 낫다. 여기서 멈추면 질문 자체가 불가능해지므로 남은 청크로 답한다. 다만 건너뛴 수를 함께 반환해
    호출자가 사용자에게 알릴 수 있게 한다. 이 계층에서 경고를 직접 찍지
    않는 이유는 웹에서 터미널 출력을 쓸 수 없기 때문이다.

    Args:
        repo (Path): 대상 레포 루트.
        persist_dir (str): 벡터 저장소 경로.
        changed (set[str] | None): 인덱싱 뒤 내용이 바뀐 파일의 상대 경로.
            이 파일들의 청크는 통째로 건너뛴다. None이면 줄 수로만 거른다.

    Returns:
        tuple[list[Chunk], int]: (복원된 청크 목록, 건너뛴 청크 수).
    """
    # 클라이언트를 직접 만들지 않는다. Chroma의 등록부가 스레드 안전하지
    # 않아 웹에서 두 API를 동시에 부르면 양쪽이 다 죽는다.
    from vibecheck.store.vector import get_client

    col = get_client(persist_dir).get_collection("chunks")
    got = col.get()

    chunks = []
    stale = 0

    changed = changed or set()

    for meta in got["metadatas"]:
        if meta["file"] in changed:
            stale += 1
            continue

        path = repo / meta["file"]
        try:
            src_lines = path.read_text(encoding="utf-8").split("\n")
        except OSError:
            stale += 1
            continue

        if meta["end_line"] > len(src_lines):
            stale += 1
            continue

        chunks.append(
            Chunk(
                file=meta["file"],
                symbol=meta["symbol"],
                kind=meta["kind"],
                start_line=meta["start_line"],
                end_line=meta["end_line"],
                code="\n".join(src_lines[meta["start_line"] - 1 : meta["end_line"]]),
                summary=meta["summary"],
                imports=meta.get("imports", "").split(",") if meta.get("imports") else [],
                calls=meta.get("calls", "").split("\n") if meta.get("calls") else [],
            )
        )

    return chunks, stale


def open_index(repo: Path) -> tuple[list[Chunk], str, int, dict]:
    """인덱스를 열어 청크와 벡터 저장소 경로를 함께 반환한다.

    네 명령이 반복하던 절차를 하나로 묶은 것이다.
    경로 계산, 존재 확인, 복원, 빈 인덱스 확인이 항상 같은 순서로 일어난다.

    자동 인덱싱은 하지 않는다. 질문 한 번에 요금과 수 분이 나가는 것을
    사용자가 모르는 채로 겪게 해서는 안 된다.

    인덱싱 조건을 함께 돌려주는 이유는 호출자가 같은 파일 목록으로
    계산해야 하기 때문이다. 청크만으로는 "무엇을 제외하고 인덱싱했는지"를
    복원할 수 없고, 그것을 모르면 리포트의 통계가 인덱스와 어긋난다.

    Args:
        repo (Path): 대상 레포 루트. 호출 전에 resolve된 상태여야 한다.

    Returns:
        tuple[list[Chunk], str, int, dict]: (청크 목록, 벡터 저장소 경로,
            건너뛴 청크 수, 인덱싱 조건). 조건은 장부에서 읽으며,
            1판 장부이거나 읽지 못했으면 빈 딕셔너리다.

    Raises:
        IndexNotFound: 벡터 저장소가 없을 때.
        IndexEmpty: 복원된 청크가 하나도 없을 때.
    """
    persist_base, chroma_dir = index_paths(repo)

    if not Path(chroma_dir).exists():
        raise IndexNotFound(str(repo))

    # 장부는 요약 캐시용이지만 파일마다 인덱싱 당시 해시를 갖고 있어,
    # 청크가 지금 파일과 맞는지 가리는 데 그대로 쓸 수 있다.
    manifest = Manifest(persist_base)
    hashes = {
        rel: entry["hash"]
        for rel, entry in manifest.data.items()
        if isinstance(entry, dict) and entry.get("hash")
    }

    chunks, stale = load_chunks(repo, chroma_dir, changed_files(repo, hashes))
    if not chunks:
        raise IndexEmpty(str(repo))

    return chunks, chroma_dir, stale, load_index_meta(persist_base)