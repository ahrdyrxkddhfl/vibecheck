"""인덱싱 뒤 바뀐 파일을 가리는 changed_files의 테스트.

틀린 줄을 코드라고 넘기는 버그는 겉으로 드러나지 않는다. 답변은 그럴듯하게
나오고 경고도 없다. 그래서 가장 흔한 경우인 한 줄 밀림을 여기서 못 박아둔다.
"""

from vibecheck.services.index_access import changed_files
from vibecheck.store.manifest import file_hash


def test_one_line_shift_is_detected(tmp_path):
    """한 줄만 끼어들어도 잡는다. 첫 줄 검사로는 놓치던 경우다."""
    src = tmp_path / "mod.py"
    src.write_text("import os\n\n\ndef a():\n    pass\n", encoding="utf-8")
    known = {"mod.py": file_hash(str(src))}

    src.write_text("# 끼어든 줄\nimport os\n\n\ndef a():\n    pass\n", encoding="utf-8")

    assert changed_files(tmp_path, known) == {"mod.py"}


def test_unchanged_file_is_not_flagged(tmp_path):
    """그대로인 파일은 건드리지 않는다. 멀쩡한 청크를 버리면 답할 재료가 준다."""
    src = tmp_path / "mod.py"
    src.write_text("def a():\n    pass\n", encoding="utf-8")

    assert changed_files(tmp_path, {"mod.py": file_hash(str(src))}) == set()


def test_missing_file_is_flagged(tmp_path):
    """사라진 파일도 바뀐 것으로 본다."""
    assert changed_files(tmp_path, {"gone.py": "0" * 64}) == {"gone.py"}


def test_files_without_hash_are_not_judged(tmp_path):
    """장부에 없는 파일은 판단하지 않는다. README처럼 해시가 없는 파일이다."""
    (tmp_path / "README.md").write_text("# 제목\n", encoding="utf-8")

    assert changed_files(tmp_path, {}) == set()
