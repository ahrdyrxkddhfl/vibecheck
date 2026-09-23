"""API 키를 담은 .env를 어디서 읽는지 지킨다.

인자 없는 load_dotenv()는 코드 파일의 위치에서만 .env를 찾아, 패키지로 설치한
사용자가 자기 폴더에 만든 .env를 읽지 못했다. 명령을 실행한 폴더를 먼저 본다.
"""

import os

from vibecheck.llm import anthropic as client


def test_env_in_working_folder_is_read(tmp_path, monkeypatch):
    """명령을 실행한 폴더의 .env에서 키를 읽는다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 작업 폴더로 쓴다.
        monkeypatch (pytest.MonkeyPatch): 작업 폴더와 환경변수를 바꾼다.
    """
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-working-folder\n")
    monkeypatch.chdir(tmp_path)
    # 먼저 값을 넣었다가 지워야, 테스트가 끝난 뒤 원래 값으로 돌려놓는다.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder")
    monkeypatch.delenv("ANTHROPIC_API_KEY")

    client.load_env()

    assert os.environ["ANTHROPIC_API_KEY"] == "from-working-folder"


def test_exported_key_wins_over_env_file(tmp_path, monkeypatch):
    """셸에서 이미 정한 키는 .env가 덮어쓰지 않는다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더. 작업 폴더로 쓴다.
        monkeypatch (pytest.MonkeyPatch): 작업 폴더와 환경변수를 바꾼다.
    """
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=from-file\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "exported")

    client.load_env()

    assert os.environ["ANTHROPIC_API_KEY"] == "exported"
