"""소스 코드를 파싱해 함수·클래스 심볼을 추출한다.

tree-sitter로 소스를 문법 트리(AST)로 변환한 뒤, 트리를 순회하며
함수와 클래스 정의를 찾아 Symbol 객체로 반환한다.

정규식 대신 tree-sitter를 사용하는 이유는 심볼의 정확한 시작·끝 범위와
소속 관계가 필요하기 때문이다. 정규식은 문자 패턴만 볼 수 있어
"이 함수가 어디서 끝나는가"와 "어느 클래스에 속하는가"를 판단할 수 없다.
"""

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from vibecheck.models import Symbol

PY_LANGUAGE = Language(tspython.language())

TARGET_TYPES = {"function_definition", "class_definition"}
"""추출 대상 노드 타입. 그 외 노드는 순회만 하고 수집하지 않는다."""


def parse_file(path: str) -> tuple[object, bytes]:
    """파일을 읽어 문법 트리로 변환한다.

    tree-sitter는 bytes 단위로 동작하므로 파일을 반드시 바이너리 모드로
    읽는다. str로 읽으면 파싱 자체가 실패하고, 한글 주석이 포함된 경우
    바이트 오프셋이 문자 인덱스와 어긋나 잘못된 위치를 가리키게 된다.

    Args:
        path (str): 파싱할 소스 파일 경로.

    Returns:
        tuple[Tree, bytes]: 문법 트리와 원본 소스 바이트.
            소스를 함께 반환하는 이유는 노드에서 실제 텍스트를 꺼낼 때
            바이트 오프셋으로 슬라이싱해야 하기 때문이다.
    """
    with open(path, "rb") as f:
        source = f.read()
    parser = Parser(PY_LANGUAGE)
    return parser.parse(source), source


def walk(
    node: Node,
    source: bytes,
    parent: str | None = None,
    results: list[Symbol] | None = None,
) -> list[Symbol]:
    """문법 트리를 재귀 순회하며 심볼을 수집한다.

    함수와 클래스는 트리의 임의 깊이에 존재할 수 있다. 최상단 함수도 있고
    클래스 안의 메서드도 있으며 중첩 클래스도 가능하다. 따라서 깊이를
    가정하지 않고 재귀로 전체를 훑는다.

    소속 관계는 부모 이름을 자식에게 물려주는 방식으로 추적한다.
    class_definition 노드를 만나면 그 이름을 하위 노드에 전달하므로,
    메서드는 자신이 어느 클래스에 속하는지 알 수 있다.

    Args:
        node (Node): 현재 순회 중인 노드.
        source (bytes): 원본 소스. 노드 이름을 꺼낼 때 사용한다.
        parent (str | None): 상위 클래스 이름. 최상단이면 None.
        results (list[Symbol] | None): 수집 결과 누적 리스트.
            재귀 호출 간 공유되며, 최초 호출 시 None이면 새로 생성한다.

    Returns:
        list[Symbol]: 파일 내 모든 함수·클래스 심볼. 소스 등장 순서를 따른다.
    """
    if results is None:
        results = []

    # 기본값은 현재 부모를 그대로 통과시킨다.
    # class -> block -> function 구조에서 중간의 block 노드가
    # 부모 정보를 끊어먹지 않도록 하기 위함이다.
    next_parent = parent

    if node.type in TARGET_TYPES:
        name_node = node.child_by_field_name("name")
        name = source[name_node.start_byte : name_node.end_byte].decode()

        if node.type == "class_definition":
            kind = "class"
        elif parent is not None:
            kind = "method"
        else:
            kind = "function"

        results.append(
            Symbol(
                name=name,
                kind=kind,
                # tree-sitter는 0-based, 에디터는 1-based이므로 보정한다.
                # 이 보정이 없으면 사용자에게 안내하는 라인 번호가
                # 실제보다 한 줄씩 밀린다.
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                parent=parent,
            )
        )

        # 이 노드 자신이 심볼일 때만 자식에게 새 부모를 물려준다.
        next_parent = name

    for child in node.children:
        walk(child, source, next_parent, results)

    return results

# ===================
# 실행부(계속 수정 중...)
# ===================
if __name__ == "__main__":
    tree, source = parse_file("sample.py")
    for s in walk(tree.root_node, source):
        owner = f"{s.parent}." if s.parent else ""
        print(f"{s.kind:9} {owner}{s.name:12} ({s.start_line}-{s.end_line})")
        