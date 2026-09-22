"""수집 계층이 무엇을 걷고 무엇을 버리는지 확인한다.

버린 것을 세는 기능은 화면과 리포트가 "레포 전체를 분석했다"고
잘못 말하지 않게 하려고 만들었다. 세는 규칙이 조용히 바뀌면
그 거짓말이 그대로 돌아오므로 규칙 자체를 시험한다.
"""

from vibecheck.core.collector import (
    collect_source_files,
    format_skipped,
    group_by_extension,
)


def test_대상이_아닌_확장자는_버리고_경로를_남긴다(tmp_path):
    """지원 언어만 걷되 버린 것의 경로를 잃지 않는지 확인한다.

    개수만 세면 나중에 뺄 수 없다. README처럼 수집 대상이 아니면서
    다른 경로로 인덱싱되는 파일을 보고에서 골라내려면 경로가 필요하다.
    """
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.py").write_text("y = 2")
    (tmp_path / "main.go").write_text("package main")

    result = collect_source_files(str(tmp_path))

    assert [p.name for p in result.files] == ["a.py", "b.py"]
    assert [p.name for p in result.skipped_other] == ["main.go"]


def test_제외_디렉터리는_세지_않는다(tmp_path):
    """의존성 폴더의 수천 개를 보고하면 정작 봐야 할 소수가 묻힌다."""
    (tmp_path / "a.py").write_text("x = 1")
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "lib.py").write_text("z = 3")
    (venv / "note.txt").write_text("t")

    result = collect_source_files(str(tmp_path))

    assert [p.name for p in result.files] == ["a.py"]
    assert result.skipped_other == []


def test_이미_인덱싱된_파일은_제외_보고에서_뺀다(tmp_path):
    """조용한 누락을 고치려다 거짓 보고를 만들지 않는지 확인한다.

    README는 확장자 필터에 걸리지만 별도 경로로 청크가 되어
    실제로는 검색된다. 제외됐다고 말하면 틀린 말이 된다.
    """
    (tmp_path / "readme.md").write_text("# hi")
    (tmp_path / "guide.md").write_text("# doc")

    result = collect_source_files(str(tmp_path))
    counts = group_by_extension(result.skipped_other, str(tmp_path), {"readme.md"})

    assert counts == {".md": 1}


def test_확장자가_많으면_뒤를_접는다():
    """28종이 한 줄로 쏟아지면 사용자가 봐야 할 항목이 묻힌다."""
    counts = {".a": 9, ".b": 8, ".c": 7, ".d": 6, ".e": 5, ".f": 4, ".g": 3}

    line = format_skipped(counts, top=5)

    assert line.startswith("제외 42개: .a 9, .b 8, .c 7, .d 6, .e 5")
    assert line.endswith("그 외 2종 7개")


def test_한_종류만_남으면_접지_않는다():
    """접는 쪽이 더 길고 정보는 적은 경우다."""
    counts = {".a": 9, ".b": 8, ".c": 7, ".d": 6, ".e": 5, ".f": 4}

    line = format_skipped(counts, top=5)

    assert line.endswith(".f 4")