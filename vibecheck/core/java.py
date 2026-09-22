"""Java 소스에서 심볼, import, 파일 설명을 꺼내는 데 필요한 것을 모은다.

파이썬용은 parser.py에 있다. 순회와 소속 추적(walk)은 언어와 무관해서 그대로
쓰고, 여기에는 노드 이름과 Java에만 있는 규칙만 둔다.

호출 수집은 두지 않는다. 호출을 이름만으로 해석하는 규칙(callgraph.py)은 파이썬
import 방식에 맞춰져 있고, Java는 오버로딩과 인터페이스 주입이 흔해 이름만으로는
어느 구현을 부르는지 좁혀지지 않는다. 틀린 화살표를 그리느니 그리지 않는다.
"""

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
    내부 모듈 판별(is_internal_import)이 이름을 뒤에서부터 잘라 파일 이름과
    대조하므로 원문 그대로여야 한다.

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
