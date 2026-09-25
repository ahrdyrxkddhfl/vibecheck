"""API 키 없이 인덱싱하는 --no-summary의 약속을 지킨다.

MCP로 Claude에 붙여 쓸 때는 채점과 답변을 Claude가 하므로, 남는 LLM 호출은
인덱싱 때의 청크 요약뿐이다. 이것을 건너뛰면 키 없이 끝까지 쓸 수 있다.

1. 요약 없이 인덱싱해도 청크가 만들어지고 LLM을 부르지 않는다.
2. 이미 요약해 둔 레포를 요약 없이 다시 돌리면 캐시의 요약을 그대로 쓴다.
3. 요약 없이 인덱싱한 뒤 키를 넣고 다시 돌리면 빠진 요약을 새로 만든다.
4. CLI는 --no-summary면 Anthropic 클라이언트를 만들지 않아 키가 없어도 멈추지 않는다.
"""

from pathlib import Path

from typer.testing import CliRunner

from vibecheck import cli
from vibecheck.services.indexer import index_repo

CODE = '''
def load(path):
    return open(path).read()


def count_words(path):
    return len(load(path).split())
'''


class CountingLLM:
    """부른 횟수를 세고 정해진 요약을 돌려주는 가짜 LLM."""

    def __init__(self):
        """부른 횟수를 0으로 시작한다."""
        self.calls = 0

    def complete(self, system, user, max_tokens=200):
        """요약 한 줄을 돌려준다.

        Args:
            system (str): 시스템 프롬프트.
            user (str): 사용자 메시지.
            max_tokens (int): 최대 토큰 수.

        Returns:
            str: 정해진 요약.
        """
        self.calls += 1
        return "파일을 읽어 단어를 센다"


def make_repo(tmp_path: Path) -> Path:
    """함수 두 개짜리 파이썬 파일 하나가 든 레포를 만든다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.

    Returns:
        Path: 레포 경로.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "words.py").write_text(CODE, encoding="utf-8")
    return repo


def symbols(chunks):
    """함수·클래스 청크만 고른다.

    Args:
        chunks (list): 인덱싱된 청크.

    Returns:
        list: 파일 단위와 문서·설정 청크를 뺀 청크.
    """
    return [c for c in chunks if c.kind not in ("file", "doc", "config")]


def test_indexes_without_summaries(tmp_path):
    """요약 없이도 함수 청크가 만들어지고, 요약은 비어 있다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    repo = make_repo(tmp_path)

    chunks = index_repo(str(repo), None, verbose=False, persist_dir=str(repo / ".vibecheck"))

    assert {c.symbol for c in symbols(chunks)} == {"load", "count_words"}
    assert all(c.summary is None for c in symbols(chunks))


def test_reuses_cached_summaries(tmp_path):
    """요약해 둔 레포를 요약 없이 다시 돌리면 캐시의 요약을 그대로 쓴다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    repo = make_repo(tmp_path)
    persist = str(repo / ".vibecheck")
    index_repo(str(repo), CountingLLM(), verbose=False, persist_dir=persist)

    chunks = index_repo(str(repo), None, verbose=False, persist_dir=persist)

    assert all(c.summary == "파일을 읽어 단어를 센다" for c in symbols(chunks))


def test_summarizes_later_when_key_is_given(tmp_path):
    """요약 없이 인덱싱한 뒤 키를 넣고 다시 돌리면 빠진 요약을 만든다.

    요약 없는 인덱싱이 캐시에 빈 요약을 굳혀 두면, 나중에 키를 넣어도 요약이
    영영 비어 있게 된다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    repo = make_repo(tmp_path)
    persist = str(repo / ".vibecheck")
    index_repo(str(repo), None, verbose=False, persist_dir=persist)
    llm = CountingLLM()

    chunks = index_repo(str(repo), llm, verbose=False, persist_dir=persist)

    assert llm.calls == 2
    assert all(c.summary == "파일을 읽어 단어를 센다" for c in symbols(chunks))


def test_cli_no_summary_needs_no_api_key(tmp_path, monkeypatch):
    """--no-summary면 Anthropic 클라이언트를 만들지 않는다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
        monkeypatch (pytest.MonkeyPatch): 클라이언트와 벡터 저장소를 바꿔 끼운다.
    """
    repo = make_repo(tmp_path)

    def no_client(*args, **kwargs):
        """만들어지면 실패하게 한다."""
        raise AssertionError("--no-summary인데 Anthropic 클라이언트를 만들었습니다")

    class FakeStore:
        """임베딩 모델을 내려받지 않도록 벡터 저장소를 흉내 낸다."""

        def __init__(self, persist_dir):
            """저장 위치만 받는다."""

        def add(self, chunks):
            """아무것도 하지 않는다."""

        def prune(self, ids):
            """지운 것이 없다고 답한다."""
            return 0

    monkeypatch.setattr(cli, "AnthropicClient", no_client)
    monkeypatch.setattr(cli, "VectorStore", FakeStore)

    result = CliRunner().invoke(cli.app, ["index", str(repo), "--no-summary"])

    assert result.exit_code == 0, result.output
    assert "요약 건너뜀" in result.output
