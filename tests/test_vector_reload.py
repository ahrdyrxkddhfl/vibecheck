"""서버를 켠 채 다시 인덱싱해도 벡터 검색이 새 인덱스를 보는지 지킨다.

2026-09-23에 서버를 켠 채 whyd index를 돌리자, 서버의 질문이 "Error finding id"로
실패했다. 서버가 한 번 연 Chroma 연결을 계속 쓰는데 그 연결은 다른 프로세스의
쓰기를 모르고, 같은 경로로 새로 만들어도 Chroma가 같은 시스템을 돌려준다.

다시 인덱싱은 다른 프로세스에서 한다. whyd index가 그렇게 돈다. 임베딩 모델 없이
벡터를 직접 넣어 빠르게 돈다.
"""

import subprocess
import sys

import pytest

from vibecheck.store import vector

WRITER = r'''
import sys, chromadb
path, step = sys.argv[1], sys.argv[2]
col = chromadb.PersistentClient(path=path).get_or_create_collection(
    "chunks", metadata={"hnsw:space": "cosine"})
if step == "init":
    col.upsert(ids=[f"old{i}" for i in range(20)],
               embeddings=[[float(i), 1.0, 0.5] for i in range(20)])
else:
    col.delete(ids=[f"old{i}" for i in range(20)])
    col.upsert(ids=[f"new{i}" for i in range(20)],
               embeddings=[[1.0, float(i), 0.5] for i in range(20)])
'''


def write_elsewhere(path, step: str) -> None:
    """다른 프로세스에서 저장소에 쓴다. whyd index를 흉내 낸다.

    Args:
        path (Path): 저장소 경로.
        step (str): "init"이면 처음 넣기, 아니면 옛 청크를 지우고 새로 넣기.
    """
    subprocess.run([sys.executable, "-c", WRITER, str(path), step], check=True)


def first_id(client) -> str:
    """검색 결과 첫 id를 돌려준다.

    Args:
        client: Chroma 클라이언트.

    Returns:
        str: 가장 가까운 청크의 id.
    """
    col = client.get_or_create_collection("chunks", metadata={"hnsw:space": "cosine"})
    return col.query(query_embeddings=[[1.0, 2.0, 0.5]], n_results=1)["ids"][0][0]


@pytest.fixture(autouse=True)
def fresh_clients(monkeypatch):
    """테스트마다 클라이언트 캐시를 비운다. 다른 테스트가 연 것과 섞이지 않게.

    Args:
        monkeypatch (pytest.MonkeyPatch): 모듈 전역을 바꿔 끼운다.
    """
    monkeypatch.setattr(vector, "_CLIENTS", {})


def test_client_is_reused_while_store_is_unchanged(tmp_path):
    """저장소가 그대로면 같은 클라이언트를 돌려준다. 읽기로는 새로 열지 않는다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    write_elsewhere(tmp_path, "init")
    client = vector.get_client(str(tmp_path))
    first_id(client)
    first_id(client)

    assert vector.get_client(str(tmp_path)) is client


def test_client_sees_reindex_from_another_process(tmp_path):
    """다른 프로세스가 다시 인덱싱하면 새로 열어 새 청크를 찾는다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    write_elsewhere(tmp_path, "init")
    before = vector.get_client(str(tmp_path))
    assert first_id(before).startswith("old")

    write_elsewhere(tmp_path, "reindex")
    after = vector.get_client(str(tmp_path))

    assert after is not before
    assert first_id(after).startswith("new")


def test_other_repo_client_survives_reopen(tmp_path):
    """한 레포를 새로 열어도 같은 서버가 연 다른 레포의 연결은 그대로 쓸 수 있다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    repo_a, repo_b = tmp_path / "a", tmp_path / "b"
    write_elsewhere(repo_a, "init")
    write_elsewhere(repo_b, "init")
    client_a = vector.get_client(str(repo_a))
    vector.get_client(str(repo_b))

    write_elsewhere(repo_b, "reindex")
    vector.get_client(str(repo_b))

    assert vector.get_client(str(repo_a)) is client_a
    assert first_id(client_a).startswith("old")


def test_own_write_does_not_reopen(tmp_path):
    """이 프로세스가 쓴 뒤 시각을 맞추면, 자기 쓰기를 바깥의 변화로 보지 않는다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    write_elsewhere(tmp_path, "init")
    client = vector.get_client(str(tmp_path))
    col = client.get_or_create_collection("chunks", metadata={"hnsw:space": "cosine"})
    col.upsert(ids=["mine"], embeddings=[[0.0, 0.0, 1.0]])
    vector.remember_own_write(str(tmp_path))

    assert vector.get_client(str(tmp_path)) is client
