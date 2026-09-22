"""끊긴 인덱싱이 요약을 잃지 않되 인덱스 기록은 흔들지 않는지 확인한다.

장부는 요약 캐시이면서 벡터 저장소가 어떤 해시의 파일로 만들어졌는지의
기록이다. 도중의 저장이 기록까지 바꾸면, 끊긴 뒤 옛 청크를 새 파일의 줄
범위로 읽는 버그(인덱싱 뒤 줄이 밀린 파일을 조용히 잘못 보여주던 것)가
되살아난다.
"""

import json

from vibecheck.models import Chunk
from vibecheck.store.manifest import Manifest, file_hash


def make_chunks(summary: str | None = None) -> list[Chunk]:
    """a.py의 함수 청크 하나를 만든다.

    Args:
        summary (str | None): 채워둘 요약.

    Returns:
        list[Chunk]: 청크 하나짜리 목록.
    """
    return [
        Chunk(
            file="a.py",
            symbol="f",
            kind="function",
            start_line=1,
            end_line=2,
            code="def f():\n    return 1",
            summary=summary,
        )
    ]


def test_끊긴_인덱싱의_요약을_다음에_재사용한다(tmp_path):
    """update 뒤 저장만 하고 commit 없이 끝나도, 다음 실행이 그 요약을 쓴다."""
    src = tmp_path / "a.py"
    src.write_text("def f():\n    return 1\n")
    store = tmp_path / ".vibecheck"

    first = Manifest(persist_dir=str(store))
    first.update(make_chunks("요약"), str(src))
    first.save()

    again = Manifest(persist_dir=str(store))
    fresh = make_chunks()
    assert again.apply(fresh, str(src)) == 1
    assert fresh[0].summary == "요약"


def test_끊긴_뒤에도_인덱스_기록은_옛_해시다(tmp_path):
    """파일을 고치고 인덱싱하다 끊겨도 기록(files)은 옛 인덱스의 해시로 남는다."""
    src = tmp_path / "a.py"
    store = tmp_path / ".vibecheck"

    src.write_text("def f():\n    return 1\n")
    done = Manifest(persist_dir=str(store))
    done.update(make_chunks("옛 요약"), str(src))
    done.commit()
    done.save()
    old_hash = file_hash(str(src))

    src.write_text("\n\ndef f():\n    return 2\n")
    cut = Manifest(persist_dir=str(store))
    cut.update(make_chunks("새 요약"), str(src))
    cut.save()

    raw = json.loads((store / "manifest.json").read_text(encoding="utf-8"))
    assert raw["files"]["a.py"]["hash"] == old_hash
    assert raw["pending"]["a.py"]["hash"] == file_hash(str(src))


def test_끝까지_성공하면_기록으로_옮기고_pending을_비운다(tmp_path):
    """commit 뒤의 장부는 pending 없이 예전과 같은 모양이다."""
    src = tmp_path / "a.py"
    src.write_text("def f():\n    return 1\n")
    store = tmp_path / ".vibecheck"

    m = Manifest(persist_dir=str(store))
    m.update(make_chunks("요약"), str(src))
    m.commit()
    m.save()

    raw = json.loads((store / "manifest.json").read_text(encoding="utf-8"))
    assert raw["files"]["a.py"]["hash"] == file_hash(str(src))
    assert "pending" not in raw
    assert not (store / "manifest.json.tmp").exists()
