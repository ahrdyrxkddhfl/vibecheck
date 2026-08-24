"""청크를 벡터DB에 저장하고 의미 기반으로 검색한다.

자연어 질문과 코드를 연결하기 위해 벡터 검색을 사용한다.
사용자는 '로그인 어떻게 처리 돼?'처럼 묻지만 코드에는 verify_token 같은
식별자만 있어 문자열 매칭으로는 연결되지 않는다.
텍스트를 의미 공간의 벡터로 변환하면 표현이 달라도 의미가 가까운 항목을 찾을 수 있다.
"""

from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from vibecheck.models import Chunk

COLLECTION_NAME = "chunks"

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

class VectorStore:
    """청크의 벡터 저장과 검색을 담당한다.

    Attributes:
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
        self.client = chromadb.PersistentClient(path=persist_dir)
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

        다만 imports는 예외로 저장한다. 코드 본문에서 복원할 수 없기 때문이다.
        청크는 함수 본문만 담아 파일 상단의 import가 들어 있지 않다.

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
                }
                for c in chunks
            ],
        )

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """질의와 의미적으로 가까운 청크를 찾는다.

        결과는 항상 top_k개가 반환되며, 관련성이 낮은 항목도 포함될 수 있다.
        벡터 검색은 '일치하는 것'이 아니라 '가장 가까운 것'을 돌려주기 때문이다.
        따라서 반환된 거리 값을 함께 확인해야 한다.

        Args:
            query (str): 자연어 질의.
            top_k (int): 반환할 최대 개수.
        
        Returns:
            list[dict]: id, 메타데이터, 거리를 담은 결과 목록.
                거리가 작을수록 유사도가 높다.
        """
        result = self.collection.query(
            query_texts=[query],
            n_results=top_k,
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