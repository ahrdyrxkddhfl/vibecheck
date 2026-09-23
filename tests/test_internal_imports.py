"""import가 레포 안을 가리키는지 가르는 동작을 지킨다.

Java에서 자기 패키지가 외부 의존성 목록에 올라가던 문제를 막는다. 판별은
이름을 앞에서부터 잘라 파일 이름과 대조하는데, static 멤버나 중첩 클래스가
끝에 붙은 import는 그대로는 어떤 파일과도 만나지 않았다. 대조 전에 언어
설정(import_target)으로 줄여 이 문제를 푼다.

청크는 SimpleNamespace로 흉내 낸다. 두 함수가 청크에서 읽는 것은 file과
imports뿐이다.
"""

from types import SimpleNamespace

import pytest

from vibecheck.core import java
from vibecheck.core.languages import PYTHON
from vibecheck.core.overview import build_import_edges, split_dependencies

JAVA_FILE = "src/main/java/com/claimtrace/controller/ClaimController.java"
CLAIM_FILE = "src/main/java/com/claimtrace/domain/Claim.java"
ERROR_FILE = "src/main/java/com/claimtrace/domain/ErrorCode.java"

JAVA_MODULES = {
    "ClaimController": JAVA_FILE,
    "Claim": CLAIM_FILE,
    "ErrorCode": ERROR_FILE,
}
"""build_module_map이 Java 파일에 붙이는 이름 그대로다. 패키지 없이 클래스 이름만 받는다."""


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("com.claimtrace.domain.Claim", "com.claimtrace.domain.Claim"),
        ("com.claimtrace.domain.Claim.Status", "com.claimtrace.domain.Claim"),
        ("com.claimtrace.domain.ErrorCode.NOT_FOUND", "com.claimtrace.domain.ErrorCode"),
        ("org.junit.jupiter.api.Assertions.assertEquals", "org.junit.jupiter.api.Assertions"),
        ("com.claimtrace.service", "com.claimtrace.service"),
    ],
)
def test_java_import_target_keeps_up_to_first_class(name, expected):
    """첫 클래스 뒤의 중첩 클래스와 멤버를 떼고, 클래스가 없는 패키지 이름은 둔다.

    Args:
        name (str): extract_imports가 남긴 import 이름.
        expected (str): 줄인 결과.
    """
    assert java.import_target(name) == expected


def test_python_import_target_keeps_name():
    """파이썬은 import 이름이 곧 모듈 이름이라 바꾸지 않는다."""
    assert PYTHON.import_target("vibecheck.core.parser") == "vibecheck.core.parser"


def test_java_own_classes_stay_out_of_external_dependencies():
    """중첩 클래스와 static 멤버 import가 자기 패키지를 외부 의존성으로 올리지 않는다.

    고치기 전에는 세 내부 import 중 둘이 외부로 판정되어 서드파티 목록에
    com.claimtrace가 올라갔다.
    """
    chunk = SimpleNamespace(
        file=JAVA_FILE,
        imports=[
            "com.claimtrace.domain.Claim",
            "com.claimtrace.domain.Claim.Status",
            "com.claimtrace.domain.ErrorCode.NOT_FOUND",
            "org.junit.jupiter.api.Assertions.assertEquals",
            "java.util.List",
        ],
    )

    third_party, stdlib, internal_count = split_dependencies(
        [chunk], set(JAVA_MODULES)
    )

    assert third_party == ["org.junit"]
    assert stdlib == ["java.util"]
    assert internal_count == 3


def test_java_nested_and_static_imports_become_edges():
    """중첩 클래스와 static 멤버 import도 그 클래스 파일로 가는 간선이 된다."""
    chunk = SimpleNamespace(
        file=JAVA_FILE,
        imports=[
            "com.claimtrace.domain.Claim.Status",
            "com.claimtrace.domain.ErrorCode.NOT_FOUND",
        ],
    )

    edges = build_import_edges([chunk], JAVA_MODULES)

    assert edges == [(JAVA_FILE, CLAIM_FILE), (JAVA_FILE, ERROR_FILE)]


def test_python_matching_unchanged():
    """파이썬 import는 이전과 같은 방식으로 가른다."""
    chunk = SimpleNamespace(
        file="vibecheck/cli.py",
        imports=["httpx", "vibecheck.core.parser"],
    )

    third_party, _, internal_count = split_dependencies(
        [chunk], {"vibecheck.core.parser"}
    )

    assert "httpx" in third_party
    assert internal_count == 1
