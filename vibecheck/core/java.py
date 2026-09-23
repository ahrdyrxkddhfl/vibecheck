"""Java 소스에서 심볼, import, 파일 설명을 꺼내는 데 필요한 것을 모은다.

파이썬용은 parser.py에 있다. 순회와 소속 추적(walk)은 언어와 무관해서 그대로
쓰고, 여기에는 노드 이름과 Java에만 있는 규칙만 둔다.

호출 수집은 두지 않는다. 호출을 이름만으로 해석하는 규칙(callgraph.py)은 파이썬
import 방식에 맞춰져 있고, Java는 오버로딩과 인터페이스 주입이 흔해 이름만으로는
어느 구현을 부르는지 좁혀지지 않는다. 틀린 화살표를 그리느니 그리지 않는다.
"""

import re
from collections import Counter

import tree_sitter_java as tsjava
from tree_sitter import Language

JAVA_LANGUAGE = Language(tsjava.language())

CLASS_TYPES = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
    }
)
"""클래스로 볼 노드 타입.

인터페이스, enum, record는 문법상 다른 선언이지만 셋 다 메서드를 담는 타입이다.
검색 몫(KIND_QUOTAS)과 채점 근거 종류(L2_KINDS)가 class라는 이름으로 동작하므로
새 종류를 만들지 않고 class로 묶는다.
"""

FUNCTION_TYPES = frozenset(
    {
        "method_declaration",
        "constructor_declaration",
        "compact_constructor_declaration",
    }
)
"""함수로 볼 노드 타입.

Java에는 클래스 밖 함수가 없어 이 노드들은 모두 타입 안에 있고, walk가 method로
잡는다. 생성자도 메서드로 본다. 사용자가 "이 객체는 어떻게 만들어지나"를 물을 때
답이 거기 있다.
"""

DOC_COMMENT_PREFIX = b"/**"
"""선언 바로 앞에 붙는 문서 주석(Javadoc)의 시작.

파이썬 독스트링은 함수 본문 안에 있어 줄 범위로 자르면 딸려 오지만, Javadoc은
선언 앞의 별도 노드다. claim-trace에서 선언 230개가 전부 바로 윗줄에 Javadoc을
달고 있었다. 범위에 넣지 않으면 작성자가 쓴 설명이 청크에서 통째로 빠진다.
"""


def text(node, source: bytes) -> str:
    """노드가 가리키는 소스 구간을 문자열로 꺼낸다.

    Args:
        node: tree-sitter 노드.
        source (bytes): 원본 소스 바이트.

    Returns:
        str: 그 구간의 문자열.
    """
    return source[node.start_byte : node.end_byte].decode()


def extract_imports(root_node, source: bytes) -> list[str]:
    """파일의 import 선언에서 이름을 수집한다.

    Java의 import는 파일 맨 위에만 올 수 있어 파이썬처럼 try/if 안을 뒤질 필요가
    없다. 최상위 노드만 본다.

    import com.a.B는 com.a.B, import static com.a.B.c는 com.a.B.c를 남긴다.
    원문을 그대로 두고 줄이지 않는다. 내부 모듈 판별(is_internal_import)은
    이름을 앞에서부터 잘라 파일 이름과 대조하므로, 끝에 static 멤버나 중첩
    클래스가 붙은 이름은 그대로는 어떤 파일과도 만나지 않는다. 그 부분을 떼는
    일은 대조하는 쪽이 import_target으로 한다. 여기서 줄이면 저장되는 import가
    바뀌어 규칙을 고칠 때마다 다시 인덱싱해야 한다.

    와일드카드(import com.a.*)는 패키지 이름 com.a만 남긴다. 별표는 모듈 이름이
    아니어서, 붙여두면 어떤 대조에도 걸리지 않는다.

    Args:
        root_node: tree-sitter가 파싱한 루트 노드.
        source (bytes): 원본 소스 바이트.

    Returns:
        list[str]: import 이름 목록. 등장 순서를 유지하되 중복은 제거한다.
    """
    names: list[str] = []

    for child in root_node.children:
        if child.type != "import_declaration":
            continue

        for part in child.named_children:
            if part.type in ("scoped_identifier", "identifier"):
                name = text(part, source)
                if name not in names:
                    names.append(name)
                break

    return names


def clean_doc_comment(raw: str) -> str | None:
    """Javadoc 원문에서 주석 기호를 걷어낸 본문을 돌려준다.

    /** 와 */, 각 줄 앞의 * 를 벗긴다. <p> 같은 태그와 {@code} 는 남긴다.
    파이썬 독스트링도 작성자가 쓴 표기를 그대로 두므로 같은 수준에 맞춘다.

    Args:
        raw (str): /** 로 시작해 */ 로 끝나는 주석 원문.

    Returns:
        str | None: 본문. 비어 있으면 None.
    """
    body = raw.removeprefix("/**").removesuffix("*/")

    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:]
            # "* 설명"의 공백 한 칸은 기호에 딸린 것이라 떼되, 들여쓴 부분은 지킨다.
            if stripped.startswith(" "):
                stripped = stripped[1:]
        lines.append(stripped.rstrip())

    cleaned = "\n".join(lines).strip()
    return cleaned or None


def extract_file_doc(root_node, source: bytes) -> str | None:
    """파일 설명으로 쓸 Javadoc을 꺼낸다.

    파이썬의 모듈 독스트링에 해당하는 것이 Java에는 없다. 대신 최상위 타입 바로
    앞의 Javadoc을 쓴다. Java는 파일 하나에 공개 타입 하나를 두는 것이 규칙이라,
    그 타입의 설명이 곧 파일의 설명이다.

    첫 최상위 타입만 본다. 그 앞에 Javadoc이 없으면 None이다. 뒤따르는 타입의
    설명을 끌어오면 파일 대표가 아닌 것을 파일 설명으로 내세우게 된다.

    Args:
        root_node: tree-sitter가 파싱한 루트 노드.
        source (bytes): 원본 소스 바이트.

    Returns:
        str | None: 주석 기호를 걷어낸 Javadoc 본문. 없으면 None.
    """
    for child in root_node.children:
        if child.type not in CLASS_TYPES:
            continue

        prev = child.prev_sibling
        if prev is None or prev.type != "block_comment":
            return None

        raw = text(prev, source)
        if not raw.startswith(DOC_COMMENT_PREFIX.decode()):
            return None

        return clean_doc_comment(raw)

    return None


STDLIB_PREFIXES = ("java.", "javax.")
"""JDK에 들어 있는 패키지의 시작.

javax 아래에는 JDK 밖에서 오는 것도 일부 있지만(예전의 javax.persistence),
지금은 대부분 jakarta로 옮겨갔다. 표준으로 묶어 외부 의존성 목록에서 빼는
쪽으로 틀리는 편이, java.util이 외부 라이브러리로 올라오는 것보다 낫다.
"""

PACKAGE_PATTERN = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
"""파일의 package 선언.

줄 맨 앞에서만 찾는다. Javadoc 안에 "package x;"라는 글이 있어도 그 줄은
*로 시작해 걸리지 않는다. package-info.java처럼 선언 앞에 애노테이션이
붙어 있어도 선언은 제 줄에 있다.
"""

MAIN_PATTERN = re.compile(r"\bstatic\s+void\s+main\s*\(")
"""직접 실행할 수 있는 클래스의 main 메서드 선언."""


def dependency_name(import_name: str) -> tuple[str, bool]:
    """외부 import를 의존성 목록에 올릴 이름으로 줄인다.

    파이썬처럼 첫 조각만 떼면 org.springframework와 org.junit이 모두
    org가 되어 뜻이 사라진다. Java의 패키지 이름은 도메인을 거꾸로 쓴
    것이라, 앞 두 조각이 대개 라이브러리를 가리킨다(org.springframework,
    tools.jackson, jakarta.persistence).

    대문자로 시작하는 조각부터는 버린다. 거기서부터는 패키지가 아니라 클래스와
    그 멤버다. lombok.Getter처럼 패키지가 한 조각뿐이면 lombok이 남는다.

    Args:
        import_name (str): 내부 모듈이 아닌 것으로 판정된 import 이름.

    Returns:
        tuple[str, bool]: (목록에 올릴 이름, JDK 표준인지).
    """
    parts = import_name.split(".")
    package = []
    for part in parts:
        if part[:1].isupper():
            break
        package.append(part)

    # 첫 조각부터 대문자인 이상한 경우에도 빈 이름을 내지 않는다.
    if not package:
        package = parts[:1]

    return ".".join(package[:2]), import_name.startswith(STDLIB_PREFIXES)


def declared_package(source: str) -> str | None:
    """파일이 속한 패키지 이름을 package 선언에서 읽는다.

    와일드카드 import(import com.a.*)가 레포 안을 가리키는지 가를 재료다.
    모듈 이름 집합에는 클래스 이름만 있어 패키지 이름 com.a와 대조되지 않는다.

    경로에서 짐작하지 않고 선언을 읽는다. src/main/java/com/a/B.java에서
    패키지가 어디서 시작하는지는 경로만으로 정해지지 않는다. 선언은 컴파일러가
    따르는 이름 그 자체라 틀릴 일이 없다.

    Args:
        source (str): 파일 원문.

    Returns:
        str | None: 패키지 이름. 선언이 없으면(기본 패키지) None.
    """
    match = PACKAGE_PATTERN.search(source)
    return match.group(1) if match else None


def import_target(import_name: str) -> str:
    """import 이름을 그것이 가리키는 파일의 이름으로 줄인다.

    Java는 파일 하나에 최상위 타입 하나를 두고 그 이름이 파일 이름이라, import가
    가리키는 파일은 이름 속 첫 클래스다. 그 뒤에 붙은 조각은 같은 파일 안의 것이다.
    import com.a.B.Inner(중첩 클래스)와 import static com.a.B.c(멤버)는 둘 다
    B.java를 가리키므로 com.a.B까지 남긴다. 줄이지 않으면 뒤쪽 조각 때문에
    파일 이름 B와 대조되지 않아, 자기 패키지가 외부 의존성으로 올라간다.

    클래스는 대문자로 시작하는 첫 조각으로 가른다. dependency_name이 패키지와
    클래스를 가를 때 쓰는 관례와 같다.

    대문자 조각이 없으면 받은 이름 그대로 둔다. 와일드카드가 남긴 패키지
    이름(com.a)이 여기에 해당하며, 파일 하나를 가리키지 않는다. 그 이름은
    모듈 이름 집합에 더해 둔 내부 패키지 이름(declared_package)과 대조된다.

    Args:
        import_name (str): extract_imports가 남긴 import 이름.

    Returns:
        str: 첫 클래스까지 줄인 이름. 클래스가 없으면 받은 이름 그대로.
    """
    parts = import_name.split(".")
    for i, part in enumerate(parts):
        if part[:1].isupper():
            return ".".join(parts[: i + 1])
    return import_name


def entry_evidence(source: str) -> str | None:
    """파일 본문에서 직접 실행할 수 있다는 근거를 찾는다.

    main 메서드가 있으면 실행 가능한 클래스다. Spring Boot 애플리케이션이면
    그 사실을 덧붙인다. 테스트 설정 클래스에도 main이 있을 수 있는데, 그
    구분은 파일 이름으로 순위를 매기는 쪽(overview의 NON_ENTRY_HINTS)이 한다.

    Args:
        source (str): 파일 원문.

    Returns:
        str | None: 근거 문장. 찾지 못하면 None.
    """
    if not MAIN_PATTERN.search(source):
        return None

    evidence = "main 메서드가 있어 직접 실행 가능"
    if "@SpringBootApplication" in source:
        evidence += ", @SpringBootApplication"
    return evidence


def type_references(root_node, source: bytes) -> Counter:
    """파일 코드에 나온 타입 이름과 그 횟수를 센다.

    관계도가 Java 파일을 잇는 재료다. 호출은 이름만으로 어느 구현인지 좁혀지지
    않지만, 어떤 타입을 쓰는지는 이름이 곧 파일이라 정해진다. EvidenceService에
    EvidenceRepository 필드가 있으면 EvidenceService가 그 파일을 쓰는 것이다.

    import가 아니라 코드를 본다. 같은 패키지의 클래스는 import 없이 쓰므로
    import만 보면 그 연결이 빠진다. claim-trace에서 import로 잡은 연결 208건은
    모두 여기에도 잡혔고, 여기서만 잡힌 것이 44건 더 있었다. 거의 다 domain
    패키지 엔티티끼리의 연관관계였다.

    두 자리를 센다. 타입이 쓰이는 자리(필드, 매개변수, 제네릭, new)는 문법이
    type_identifier로 표시한다. ErrorCode.NOT_FOUND나 Evidence.fromRule(...)처럼
    클래스 이름으로 정적 멤버를 부르는 자리는 문법상 그냥 이름(identifier)이라,
    메서드 호출과 필드 접근의 앞쪽에 놓인 이름을 따로 센다. 이름이 대문자로
    시작하지 않으면 변수라서 뺀다.

    주석과 문자열 안의 이름은 세지 않는다. 트리에서 그 자리는 이름 노드가 아니다.

    Args:
        root_node: tree-sitter가 파싱한 루트 노드.
        source (bytes): 원본 소스 바이트.

    Returns:
        Counter: 타입 이름 -> 나온 횟수.
    """
    counts: Counter = Counter()

    def walk(node) -> None:
        """트리를 훑으며 타입 이름을 센다."""
        if node.type == "type_identifier":
            counts[text(node, source)] += 1
        elif node.type == "identifier":
            parent = node.parent
            if (
                parent is not None
                and parent.type in ("method_invocation", "field_access")
                and parent.child_by_field_name("object") == node
            ):
                name = text(node, source)
                if name[:1].isupper():
                    counts[name] += 1

        for child in node.children:
            walk(child)

    walk(root_node)
    return counts
