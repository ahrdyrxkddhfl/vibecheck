"""청크를 벡터DB에 저장하고 의미 기반으로 검색한다.

자연어 질문과 코드를 연결하기 위해 벡터 검색을 사용한다.
사용자는 '로그인 어떻게 처리 돼?'처럼 묻지만 코드에는 verify_token 같은
식별자만 있어 문자열 매칭으로는 연결되지 않는다.
텍스트를 의미 공간의 벡터로 변환하면 표현이 달라도 의미가 가까운 항목을 찾을 수 있다.
"""
import os
import threading
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from vibecheck.models import Chunk

COLLECTION_NAME = "chunks"

SQLITE_FILE = "chroma.sqlite3"
"""Chroma가 저장소 디렉터리에 두는 SQLite 파일. 수정 시각으로 바깥의 쓰기를 알아챈다."""

_CLIENTS: dict[str, tuple[int | None, "chromadb.ClientAPI"]] = {}
"""경로별로 하나씩 두는 Chroma 클라이언트와, 그 클라이언트가 본 저장소의 수정 시각."""

_CLIENTS_LOCK = threading.Lock()
"""클라이언트를 만들 때 채우는 자물쇠."""


def store_stamp(persist_dir: str) -> int | None:
    """저장소 SQLite 파일의 수정 시각을 읽는다.

    Args:
        persist_dir (str): 벡터 저장소 디렉터리.

    Returns:
        int | None: 나노초 단위 수정 시각. 파일이 아직 없으면 None.
    """
    try:
        return (Path(persist_dir) / SQLITE_FILE).stat().st_mtime_ns
    except OSError:
        return None


def get_client(persist_dir: str) -> "chromadb.ClientAPI":
    """경로에 해당하는 Chroma 클라이언트를 돌려준다. 없거나 낡았으면 새로 연다.

    PersistentClient를 매번 새로 만들면 안 된다. Chroma는 경로를 키로
    시스템을 공유하는 클래스 단위 등록부를 들고 있는데 스레드 안전하지
    않다. 한쪽이 만드는 도중 다른 쪽이 "이미 있다"고 보고 정리 코드를
    돌려 상대의 것을 꺼버린다.

    실제로 웹에서 두 API를 동시에 부르면 양쪽이 다 죽었다. 한쪽은
    KeyError, 다른 쪽은 bindings 속성이 사라졌다는 오류였다.
    스레드 둘로 open_index를 동시에 부르면 그대로 재현된다.

    그렇다고 한 번 연 것을 계속 쓰면, 서버를 켠 채 다른 프로세스가 whyd index로
    다시 인덱싱했을 때 서버의 클라이언트는 그 변화를 모른다. 이미 지워진 청크를
    돌려주거나 "Error finding id"로 실패했다. 같은 경로로 PersistentClient를 새로
    만들어도 등록부가 같은 시스템을 돌려줘 소용없다(chromadb 1.5.9에서 확인,
    vibecheck-tools/probe_chroma_reload.py).

    그래서 연 직후 SQLite 파일의 수정 시각을 함께 기억하고, 꺼낼 때마다 비교한다.
    달라졌으면 옛 클라이언트를 close()해 등록부에서 시스템을 내린 뒤 새로 연다.
    다른 경로의 클라이언트는 건드리지 않는다. 등록부를 통째로 비우는 방법
    (clear_system_cache)은 옛 시스템을 멈추지 않고 남겨, 나중에 같은 이름으로
    닫을 때 새 시스템을 멈출 수 있어 택하지 않았다.

    수정 시각은 연 뒤에 읽는다. 한 프로세스가 저장소를 처음 열 때 SQLite에 한 번
    쓰기 때문이다. 그 뒤의 읽기(검색, 개수 세기)로는 바뀌지 않는다.

    새로 열 때, 같은 경로의 옛 클라이언트로 진행 중이던 요청은 실패할 수 있다.
    다시 인덱싱과 질문이 정확히 겹칠 때뿐이고, 웹은 그 실패를 다시 시도하라는
    안내로 바꾼다(web.errors).

    만드는 구간만 자물쇠로 막는다. 이미 있는 것을 꺼내 쓰는 것은
    막을 필요가 없고, 막으면 검색이 줄을 서게 된다.

    Args:
        persist_dir (str): 벡터 저장소 디렉토리.

    Returns:
        chromadb.ClientAPI: 그 경로의 클라이언트. 저장소가 바뀌지 않았으면 같은 것이다.
    """
    cached = _CLIENTS.get(persist_dir)
    if cached is not None and cached[0] == store_stamp(persist_dir):
        return cached[1]

    with _CLIENTS_LOCK:
        # 자물쇠를 기다리는 사이 다른 스레드가 새로 열었을 수 있다.
        cached = _CLIENTS.get(persist_dir)
        if cached is not None and cached[0] == store_stamp(persist_dir):
            return cached[1]

        if cached is not None:
            cached[1].close()

        client = chromadb.PersistentClient(path=persist_dir)
        _CLIENTS[persist_dir] = (store_stamp(persist_dir), client)
        return client


def remember_own_write(persist_dir: str) -> None:
    """이 프로세스가 저장소에 쓴 뒤, 기억해 둔 수정 시각을 지금 값으로 맞춘다.

    그러지 않으면 자기가 쓴 것을 다른 프로세스가 바꾼 것으로 보고, 다음에 꺼낼 때
    쓰고 있던 클라이언트를 닫는다. 지금 whyd index는 저장소를 한 번 열어 add와
    prune을 하므로 그 일이 생기지 않지만, 흐름이 바뀌어도 안전하게 둔다.

    Args:
        persist_dir (str): 벡터 저장소 디렉터리.
    """
    with _CLIENTS_LOCK:
        cached = _CLIENTS.get(persist_dir)
        if cached is not None:
            _CLIENTS[persist_dir] = (store_stamp(persist_dir), cached[1])


EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
"""임베딩 모델 이름.

기본 모델(all-MiniLM-L6-v2)은 영어로 학습되어 한국어 텍스트를
제대로 벡터화하지 못한다. 한국어 요약을 임베딩하면 서로 다른 의미의
문장이 벡터 공간에서 뭉쳐 검색이 사실상 무작위에 가까워진다.
다국어 모델은 영어 전용 모델보다 영어 성능이 약간 낮지만, 한국어
질의를 지원해야 하므로 이 절충을 택한다.
"""


def build_embedding_text(chunk: Chunk) -> str:
    """청크를 임베딩할 텍스트로 변환한다.

    요약과 코드 원문을 함께 넣는 이유는 질문 유형이 두 가지이기 때문이다.
    '인증 어떻게 처리해?' 같은 자연어 질문은 요약이 받아내고.
    'child_by_field_name 쓰는 데 어디야?' 같은 식별자 질문은 코드 원문이 받아낸다.
    한쪽만 넣으면 다른 유형의 질문을 놓친다.

    경로와 심볼명을 앞에 두는 이유는 이들이 가장 압축된 정보이기 때문이다.
    파일 단위나 심볼 이름으로 좁혀 묻는 질문에 직접 대응한다.

    Args:
        chunk (Chunk): 변환할 청크.

    Returns:
        str: 임베딩에 사용할 텍스트.
    """
    parts = [chunk.file, chunk.symbol, chunk.kind]
    if chunk.summary:
        parts.append(chunk.summary)
    parts.append(chunk.code)
    return "\n".join(parts)

def quiet_model_loading(model_name: str) -> None:
    """임베딩 모델을 불러올 때 나오는 경고와 진행 막대를 끈다.

    모델을 불러올 때마다 HF Hub의 토큰 경고와 "Loading weights" 진행 막대가
    whyd 출력 사이에 끼어, 처음 보는 사람은 무언가 잘못된 것으로 읽는다.
    토큰이 없어도 모델은 받아지므로, 경고는 사용자가 할 일이 없는 문구다.

    진행 막대는 모델이 캐시에 있을 때만 끈다. 막대를 끄는 스위치가 다운로드
    막대까지 함께 끄기 때문이다. 빈 캐시로 재보니 458MB를 받는 동안 화면에
    아무것도 나오지 않았다. 처음 쓰는 사람에게 그것은 멈춘 화면이다.

    환경변수가 아니라 함수로 끄는 이유는 순서다. 환경변수는 huggingface_hub를
    import할 때 한 번 읽히는데, 캐시를 확인하려면 그보다 먼저 import해야 한다.

    사용자가 HF_HUB_VERBOSITY나 HF_HUB_DISABLE_PROGRESS_BARS를 직접 정했으면
    그 설정을 따른다. 여기서 바꾼 설정은 프로세스 전역에 걸린다.

    Args:
        model_name (str): sentence-transformers 모델 이름. 조직 이름이 없으면
            sentence-transformers가 하듯이 앞에 붙여서 캐시를 찾는다.
    """
    try:
        from huggingface_hub import try_to_load_from_cache
        from huggingface_hub.utils import disable_progress_bars, logging
    except ImportError:
        # sentence-transformers를 거쳐 설치되는 패키지라 직접 의존하지 않는다.
        # 없으면 출력이 시끄러울 뿐 동작에는 문제가 없다.
        return

    if "HF_HUB_VERBOSITY" not in os.environ:
        logging.set_verbosity_error()

    if "HF_HUB_DISABLE_PROGRESS_BARS" in os.environ:
        return

    repo_id = model_name if "/" in model_name else f"sentence-transformers/{model_name}"

    # 설정 파일이 아니라 가중치 파일로 확인한다. 다운로드가 가중치를 받다가
    # 끊겼다면 설정 파일은 캐시에 있으므로, 설정 파일로 확인하면 다시 받는 동안
    # 막대가 꺼진다. 가중치 파일 이름이 다른 모델이면 캐시가 없다고 보고 막대를
    # 남기는데, 시끄러운 쪽으로 틀리는 것은 괜찮다.
    cached = try_to_load_from_cache(repo_id, "model.safetensors")
    if isinstance(cached, str):
        disable_progress_bars()

class VectorStore:
    """청크의 벡터 저장과 검색을 담당한다.

    Attributes:
        persist_dir (str): 저장소 디렉터리. 쓴 뒤 수정 시각을 맞출 때 쓴다.
        client: Chroma 클라이언트.
        collection: 청크가 저장되는 컬렉션.
    """

    def __init__(self, persist_dir: str = ".vibecheck/chroma"):
        """저장소를 초기화한다.

        디스크에 영속화하는 이유는 인덱싱이 비싼 작업이기 때문이다.
        파싱과 LLM 요약을 거친 결과를 메모리에만 두면 프로세스가 끝날
        때마다 전부 다시 만들어야 한다.

        임베딩 함수를 명시적으로 지정한다. Chroma의 기본값은 영어 전용
        모델이라 한국어 요약을 제대로 벡터화하지 못하므로 다국어 모델로
        대체한다.

        컬렉션이 이미 존재하면 저장된 설정을 그대로 사용하므로, 여기서
        모델을 바꿔도 기존 인덱스에는 적용되지 않는다. 모델 변경 시에는
        저장 디렉토리를 삭제하고 재인덱싱해야 한다. 서로 다른 모델이
        만든 벡터는 차원과 의미 공간이 달라 함께 비교할 수 없다.

        Args:
            persist_dir (str): 인덱스를 저장할 디렉토리 경로.
        """
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        quiet_model_loading(EMBEDDING_MODEL)
        self.persist_dir = persist_dir
        self.client = get_client(persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL
            ),
        )

    def add(self, chunks: list[Chunk]) -> None:
        """청크 목록을 저장소에 추가한다.

        upsert를 사용해 같은 id의 청크가 있으면 덮어쓴다. 재인덱싱 시 중복 저장을 막고,
        코드가 수정된 청크는 자연스럽게 갱신된다.

        메타데이터에 코드 본문을 넣지 않는 이유는 벡터DB의 역할이 '무엇이 관련 있는가'를 찾는 데
        한정되기 때문이다. 상세 정보는 관계형 DB에서 id로 조회한다.

        다만 imports와 calls는 예외로 저장한다. 코드 본문에서 복원할 수 없기 때문이다.
        청크는 함수 본문만 담아 파일 상단의 import가 들어 있지 않고,
        호출 관계는 레포 전체를 훑어야 나오므로 청크 하나를 다시 읽어서는 얻을 수 없다.

        Args:
            chunks (list[Chunk]): 저장할 청크 목록.
        """
        if not chunks:
            return

        self.collection.upsert(
            ids=[c.id for c in chunks],
            documents=[build_embedding_text(c) for c in chunks],
            metadatas=[
                {
                    "file": c.file,
                    "symbol": c.symbol,
                    "kind": c.kind,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "summary": c.summary or "",
                    # Chroma 메타데이터는 스칼라만 받으므로 쉼표로 이어 저장한다.
                    # 인덱스에서 청크를 복원할 때 의존성 정보를 잃지 않기 위함이다.
                    "imports": ",".join(c.imports),
                    # 코드 본문에서 복원할 수 없는 정보다.
                    # imports와 달리 쉼표로 잇지 않는다. 청크 식별자는
                    # 파일 경로를 담고 있어 쉼표가 들어갈 수 있고, 그러면
                    # 복원이 조용히 깨진다. 경로에 개행은 들어가지 않는다.
                    "calls": "\n".join(c.calls),
                }
                for c in chunks
            ],
        )
        remember_own_write(self.persist_dir)

    def prune(self, valid_ids: list[str]) -> int:
        """인덱싱 결과에 없는 청크를 저장소에서 지운다.

        add는 upsert만 하므로 있는 것을 갱신할 뿐 사라진 것을 지우지 않는다.
        그 결과 파일을 삭제하거나 수집 대상에서 빼도 그 파일의 청크가
        저장소에 영구히 남아 검색 결과에 계속 잡힌다.
        실제로 실험용 사본을 수집에서 제외한 뒤에도 답변 근거에
        사본이 그대로 인용되는 것을 확인했다.

        파일 단위가 아니라 id 차집합으로 지우는 이유는 삭제된 파일 때문이다.
        수집 목록에서 빠진 파일은 그 파일을 기준으로 지울 기회 자체가 없다.
        "이번 인덱싱이 만든 청크 전체"를 인덱스의 정답으로 보고
        정답에 없는 id를 지우면 삭제와 제외를 한 번에 덮는다.

        호출자는 반드시 레포 전체를 인덱싱한 결과를 넘겨야 한다.
        일부 파일만 인덱싱한 결과를 넘기면 나머지가 전부 지워진다.

        Args:
            valid_ids (list[str]): 남겨둘 청크 id 목록.
                레포 전체 인덱싱 결과여야 한다.

        Returns:
            int: 삭제한 청크 수.
        """
        # 빈 목록은 전체 삭제와 같아 사고로 이어지므로 아무것도 하지 않는다.
        # 인덱싱이 실패해 결과가 비었을 때 인덱스까지 날리지 않기 위함이다.
        if not valid_ids:
            return 0

        stored = set(self.collection.get(include=[])["ids"])
        stale = list(stored - set(valid_ids))

        if stale:
            self.collection.delete(ids=stale)
            remember_own_write(self.persist_dir)

        return len(stale)

    def search(
        self, query: str, top_k: int = 5, kinds: list[str] | None = None
    ) -> list[dict]:
        """질의와 의미적으로 가까운 청크를 찾는다.

        결과는 항상 top_k개가 반환되며, 관련성이 낮은 항목도 포함될 수 있다.
        벡터 검색은 '일치하는 것'이 아니라 '가장 가까운 것'을 돌려주기 때문이다.
        따라서 반환된 거리 값을 함께 확인해야 한다.

        Args:
            query (str): 자연어 질의.
            top_k (int): 반환할 최대 개수.
            kinds (list[str] | None): 이 종류의 청크만 찾는다. None이면 전부.
                함수·클래스 청크가 수적으로 압도해 문서와 설정 파일이
                상위에 오르지 못하는 것을 막기 위한 것이다.
        
        Returns:
            list[dict]: id, 메타데이터, 거리를 담은 결과 목록.
                거리가 작을수록 유사도가 높다.
        """
        # Chroma는 조건이 하나면 $in을 그대로 받지만, 값이 하나뿐일 때도
        # 같은 형태로 넘겨 분기를 만들지 않는다.
        where = {"kind": {"$in": kinds}} if kinds else None

        result = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )

        return [
            {
                "id": result["ids"][0][i],
                "distance": result["distances"][0][i],
                **result["metadatas"][0][i],
            }
            for i in range(len(result["ids"][0]))
        ]

    def count(self) -> int:
        """저장된 청크 수를 반환한다.

        Returns:
            int: 컬렉션에 저장된 항목 수.
        """
        return self.collection.count()