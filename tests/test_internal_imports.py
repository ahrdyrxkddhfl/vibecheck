"""import가 레포 안을 가리키는지 가르는 동작을 지킨다.

Java에서 자기 패키지가 외부 의존성 목록에 올라가던 문제를 막는다. 판별은
이름을 앞에서부터 잘라 파일 이름과 대조하는데, static 멤버나 중첩 클래스가
끝에 붙은 import는 그대로는 어떤 파일과도 만나지 않았다. 대조 전에 언어
설정(import_target)으로 줄여 이 문제를 푼다. 패키지 와일드카드(import com.a.*)는
파일 하나를 가리키지 않으므로, 파일들이 선언한 패키지 이름을 모듈 이름 집합에
더해 푼다.

청크는 SimpleNamespace로 흉내 낸다. 두 함수가 청크에서 읽는 것은 file과
imports뿐이다.
"""

from types import SimpleNamespace

import pytest

from vibecheck.core import java
from vibecheck.core.collector import (
    build_module_map,
    build_module_names,
    build_package_names,
)
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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("package com.claimtrace.domain;\n\npublic class Claim {}\n", "com.claimtrace.domain"),
        (
            "/**\n * package com.fake.inside;\n */\npackage com.claimtrace.domain;\n",
            "com.claimtrace.domain",
        ),
        ("@NonNullApi\npackage com.claimtrace.domain;\n", "com.claimtrace.domain"),
        ("public class NoPackage {}\n", None),
    ],
)
def test_declared_package(source, expected):
    """줄 맨 앞의 package 선언만 읽고, Javadoc 속 글이나 애노테이션에 속지 않는다.

    Args:
        source (str): 파일 원문.
        expected (str | None): 읽어야 할 패키지 이름. 선언이 없으면 None.
    """
    assert java.declared_package(source) == expected


def test_build_package_names_reads_only_declared_packages(tmp_path):
    """Java 파일의 선언만 모으고, 선언이 없는 파일과 파이썬 파일은 건너뛴다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    domain = tmp_path / "src/main/java/com/claimtrace/domain"
    domain.mkdir(parents=True)
    (domain / "Claim.java").write_text("package com.claimtrace.domain;\nclass Claim {}\n")
    (domain / "Rule.java").write_text("package com.claimtrace.domain;\nclass Rule {}\n")
    (tmp_path / "Loose.java").write_text("class Loose {}\n")
    (tmp_path / "tool.py").write_text("package = 1\n")

    files = [
        domain / "Claim.java",
        domain / "Rule.java",
        tmp_path / "Loose.java",
        tmp_path / "tool.py",
    ]

    assert build_package_names(files) == {"com.claimtrace.domain"}


def test_java_own_package_wildcard_stays_internal(tmp_path):
    """자기 패키지 와일드카드는 내부로, 외부 와일드카드는 라이브러리로 가른다.

    고치기 전에는 com.claimtrace.service가 어떤 모듈 이름과도 만나지 않아
    서드파티 목록에 com.claimtrace가 올라갔다. 패키지 이름은 build_overview와
    같은 방식으로, 파일의 선언을 읽어 모듈 이름 집합에 더한다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    service = tmp_path / "ClaimService.java"
    service.write_text("package com.claimtrace.service;\nclass ClaimService {}\n")

    chunk = SimpleNamespace(
        file=JAVA_FILE,
        imports=[
            "com.claimtrace.service",
            "org.springframework.web.bind.annotation",
        ],
    )
    module_names = set(JAVA_MODULES) | build_package_names([service])

    third_party, _, internal_count = split_dependencies([chunk], module_names)

    assert third_party == ["org.springframework"]
    assert internal_count == 1


def test_same_class_name_in_two_packages_is_internal_but_gets_no_edge(tmp_path):
    """이름이 겹치는 클래스는 내부로 판정하되, 어느 파일인지 짐작해 잇지 않는다.

    예전에는 대응표에서 뒤의 파일이 앞의 파일을 덮어써, 간선이 수집 순서가 고른
    파일로 갔다. 대응표에서 빼기만 하고 이름 집합까지 대응표의 키로 만들면
    이번에는 그 import가 외부로 판정된다. 둘을 함께 확인한다.

    Args:
        tmp_path (Path): pytest가 주는 임시 폴더.
    """
    files = []
    for rel in ("a/Config.java", "b/Config.java", "c/User.java"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("class X {}\n")
        files.append(path)

    module_map = build_module_map(files, str(tmp_path))
    module_names = build_module_names(files, str(tmp_path))

    assert module_map == {"User": "c/User.java"}
    assert module_names == {"Config", "User"}

    chunk = SimpleNamespace(file="c/User.java", imports=["com.a.Config"])

    third_party, _, internal_count = split_dependencies([chunk], module_names)
    assert third_party == []
    assert internal_count == 1

    assert build_import_edges([chunk], module_map) == []
