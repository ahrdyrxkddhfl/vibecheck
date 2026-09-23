"""언어마다 다른 것을 한곳에 모은다.

파서, 수집기, 인덱서는 "파일을 읽어 심볼과 import를 꺼낸다"는 같은 일을 하는데,
그 일을 언어별로 어떻게 하는지만 다르다. 다른 부분을 여기 묶어두면 언어를
더할 때 이 파일에 항목 하나를 추가하는 것으로 끝나고, 수집 범위와 파싱 범위가
따로 적혀 한쪽만 고쳐지는 일이 없다.

parser.py는 이 모듈을 모른다. 이 모듈이 파이썬용 추출 함수를 parser.py에서
가져오므로, 반대 방향까지 이으면 서로를 import하게 된다. 언어를 고르는 일은
이 모듈의 spec_for로 호출자(indexer)가 하고, 파서에는 고른 결과만 넘긴다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language

from vibecheck.core import java
from vibecheck.core.parser import (
    CLASS_TYPES,
    FUNCTION_TYPES,
    PY_LANGUAGE,
    collect_calls,
    dependency_name,
    entry_evidence,
    extract_imports,
    extract_module_docstring,
)
from vibecheck.models import CallSite


def keep_import_name(import_name: str) -> str:
    """import 이름을 그대로 대조 대상으로 쓴다.

    import 이름이 곧 모듈 이름인 언어의 기본값이다. 파이썬의 import
    vibecheck.core.parser는 그 이름 그대로 파일 하나를 가리킨다.

    Args:
        import_name (str): import 이름.

    Returns:
        str: 받은 이름 그대로.
    """
    return import_name


@dataclass(frozen=True)
class LanguageSpec:
    """언어 하나를 읽는 데 필요한 것을 묶는다.

    Attributes:
        name (str): 언어 이름. 구분에 쓴다.
        label (str): 화면에 보일 이름.
        extensions (frozenset[str]): 이 언어로 볼 확장자.
        language (Language): tree-sitter 문법.
        class_types (frozenset[str]): 클래스로 볼 노드 타입. 그 안의 정의는 메서드가 된다.
        function_types (frozenset[str]): 함수로 볼 노드 타입.
        extract_imports (Callable): 루트 노드와 소스를 받아 import 이름 목록을 돌려준다.
        extract_docstring (Callable): 루트 노드와 소스를 받아 파일 설명을 돌려준다.
            없으면 None.
        dependency_of (Callable): 외부 import 이름을 받아 (의존성 목록에 올릴 이름,
            표준 라이브러리인지)를 돌려준다. 라이브러리 이름이 import의 어디에
            있는지가 언어마다 다르다.
        entry_evidence (Callable): 파일 원문을 받아 직접 실행할 수 있다는 근거
            문장을 돌려준다. 없으면 None.
        import_target (Callable): import 이름을 받아 그 import가 가리키는 파일의
            모듈 이름으로 줄인다. 내부 판별과 import 간선이 원래 이름 대신 이 결과로
            대조한다. 저장된 import 이름은 원문 그대로 두고 대조할 때만 줄이므로,
            규칙을 바꿔도 다시 인덱싱할 필요가 없다.
        package_of (Callable | None): 파일 원문을 받아 그 파일이 속한 패키지
            이름을 돌려준다. 없으면 None. 패키지 이름이 파일 경로와 별개로 선언되는
            언어에서만 둔다. 그 이름을 통째로 import할 수 있어서(Java의 import
            com.a.*), 내부 판별에 패키지 이름이 따로 필요하다. 파이썬은 패키지도
            __init__.py라는 파일이라 모듈 이름에 이미 들어 있다.
        doc_comment (bytes | None): 선언 바로 앞에 붙어 그 선언의 설명이 되는
            주석의 시작 표시. 설명이 선언 본문 안에 있는 언어는 None이다.
        type_named_files (bool): 최상위 타입 이름이 곧 파일 이름이라는 것이 언어
            규칙인가. 참이면 채점이 답변의 클래스 이름만으로 그 파일을 근거로
            가져온다. 규칙이 없는 언어에서 이름으로 파일을 짐작하면 틀린 근거가 된다.
        collect_type_refs (Callable | None): 루트 노드와 소스를 받아 코드에 나온 타입
            이름과 횟수를 돌려준다. 호출을 수집하지 않는 언어에서 관계도가 파일을
            잇는 재료다. type_named_files가 참이어야 이름에서 파일이 정해진다.
        collect_calls (Callable | None): 루트 노드와 소스를 받아 호출 목록을 돌려준다.
            None이면 그 언어는 호출 그래프를 만들지 않는다. 호출을 이름만으로
            해석하는 규칙이 언어마다 달라, 규칙이 없는 언어에서 억지로 이으면
            틀린 화살표가 생긴다.
    """

    name: str
    label: str
    extensions: frozenset[str]
    language: Language
    class_types: frozenset[str]
    function_types: frozenset[str]
    extract_imports: Callable[[object, bytes], list[str]]
    extract_docstring: Callable[[object, bytes], str | None]
    dependency_of: Callable[[str], tuple[str, bool]]
    entry_evidence: Callable[[str], str | None]
    import_target: Callable[[str], str] = keep_import_name
    package_of: Callable[[str], str | None] | None = None
    doc_comment: bytes | None = None
    type_named_files: bool = False
    collect_type_refs: Callable[[object, bytes], dict[str, int]] | None = None
    collect_calls: Callable[[object, bytes], list[CallSite]] | None = None


PYTHON = LanguageSpec(
    name="python",
    label="파이썬",
    extensions=frozenset({".py"}),
    language=PY_LANGUAGE,
    class_types=CLASS_TYPES,
    function_types=FUNCTION_TYPES,
    extract_imports=extract_imports,
    extract_docstring=extract_module_docstring,
    dependency_of=dependency_name,
    entry_evidence=entry_evidence,
    collect_calls=collect_calls,
)

JAVA = LanguageSpec(
    name="java",
    label="Java",
    extensions=frozenset({".java"}),
    language=java.JAVA_LANGUAGE,
    class_types=java.CLASS_TYPES,
    function_types=java.FUNCTION_TYPES,
    extract_imports=java.extract_imports,
    extract_docstring=java.extract_file_doc,
    dependency_of=java.dependency_name,
    entry_evidence=java.entry_evidence,
    import_target=java.import_target,
    package_of=java.declared_package,
    doc_comment=java.DOC_COMMENT_PREFIX,
    type_named_files=True,
    collect_type_refs=java.type_references,
)

LANGUAGES: tuple[LanguageSpec, ...] = (PYTHON, JAVA)
"""지원 언어 목록. 확장자가 겹치지 않아야 한다."""


def spec_for(path: str | Path) -> LanguageSpec | None:
    """확장자로 파일의 언어를 고른다.

    Args:
        path (str | Path): 파일 경로.

    Returns:
        LanguageSpec | None: 그 언어의 설정. 지원하지 않는 확장자면 None.
    """
    suffix = Path(path).suffix
    for spec in LANGUAGES:
        if suffix in spec.extensions:
            return spec
    return None


def supported_extensions() -> set[str]:
    """지원 언어의 확장자를 모두 모은다.

    Returns:
        set[str]: 수집 대상 확장자 집합.
    """
    return {ext for spec in LANGUAGES for ext in spec.extensions}
