"""README 청크가 디스크의 실제 파일을 가리키는지 확인한다."""

from vibecheck.core.chunker import to_readme_chunks
from vibecheck.core.overview import read_readme


def test_소문자_readme를_찾고_실제_이름을_담는다(tmp_path):
    """대소문자를 구분하지 않는 파일시스템은 경로 조회에서만 관대하다.

    후보 이름으로 경로를 조립해 존재만 확인하면 readme.md가 README.md로
    열려 디스크에 없는 이름이 인덱스에 남는다. 제외 파일 보고가
    README를 제외됐다고 잘못 말하고, 대소문자를 구분하는 리눅스에서는
    같은 인덱스로 파일을 열지 못한다.
    """
    (tmp_path / "readme.md").write_text("# 제목\n\n본문\n\n## 절\n\n내용\n")

    chunks = to_readme_chunks(str(tmp_path))

    assert chunks
    assert {c.file for c in chunks} == {"readme.md"}
    assert all(c.symbol.startswith("readme.md#") for c in chunks)


def test_소문자_readme를_개요에서도_읽는다(tmp_path):
    """glob은 패턴 매칭이라 대소문자를 구분한다.

    여기서 놓치면 프로젝트가 무엇인지 담긴 유일한 재료가
    요약 프롬프트에서 통째로 빠진다.
    """
    (tmp_path / "readme.md").write_text("# 제목\n\n본문\n")

    assert read_readme(tmp_path).startswith("# 제목")


def test_readme가_없으면_빈_결과다(tmp_path):
    """없는 것과 못 찾는 것을 가르는 기준선이다."""
    (tmp_path / "a.py").write_text("x = 1")

    assert to_readme_chunks(str(tmp_path)) == []
    assert read_readme(tmp_path) == ""