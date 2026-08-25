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

def extract_imports(root_node, source: bytes) -> list[str]:
    """파일 최상단의 import문에서 모듈 이름을 수집한다.

    청크는 함수, 클래스 본문만 담기 때문에 파일 상단의 import가 잘려나간다.
    그 결과 요약 단계에서 모델이 어떤 라이브러리를 쓰는지 알 수 없어 추측으로 채우는 문제가 발생한다.
    실제로 tree-sitter를 쓰는 파서가 "파이썬 파서"로 요약되어 검색에서 누락되는 사례가 확인되었다.

    원문이 아니라 모듈 이름만 남긴다.
    이 값을 쓰는 세 곳(요약 프롬프트, 파일 개요 텍스트, 의존성 목록)이 모두 이름만 필요하고,
    특히 의존성 목록은 이름이어야 내부 모듈과 외부 라이브러리를 가를 수 있다.
    "from typing import Any" 같은 원문은 점으로 쪼개도 모듈 경로가 나오지 않아 대조가 불가능하다.

    별칭(as)은 버리고 원래 이름을 남긴다.
    import numpy as np에서 알고 싶은 것은 numpy를 쓴다는 사실이지 np라는 이름이 아니다.

    파일 상단의 import만 훑되, try/if 블록 안까지는 들어간다.
    선택적 의존성은 관례적으로 try: import x / except ImportError: 형태로 쓰이는데,
    실제로 python-magic을 이렇게 쓰는 레포에서 서드파티 의존성이 통째로
    비어 나오는 것을 확인했다. 문법적으로는 한 겹 안이지만 의미적으로는
    파일 수준 선언이므로 상단 import와 같이 취급한다.

    함수 정의 안으로는 여전히 들어가지 않는다.
    지역 import는 순환 참조를 피하려는 것일 때가 많아 파일의 의존성으로
    보기 어렵고, "이 파일이 무엇에 기대는가"라는 질문의 답이 아니다.

    Args:
        root_node: tree-sitter가 파싱한 루트 노드.
        source (bytes): 원본 소스 바이트.

    Returns:
        list[str]: 모듈 이름 목록. 등장 순서를 유지하되 중복은 제거한다.
    """
    def text(node) -> str:
        """노드가 가리키는 소스 구간을 문자열로 꺼낸다."""
        return source[node.start_byte : node.end_byte].decode()

    names: list[str] = []

    def scan(nodes) -> None:
        """같은 층의 노드들에서 import를 거두고, 감싸개는 한 겹 펼친다.

        try/if는 자기 자신이 import가 아니라 import를 담는 그릇이다.
        그릇을 풀지 않으면 안에 든 것이 통째로 보이지 않는다.

        Args:
            nodes: 훑을 노드 목록.
        """
        for child in nodes:
            # 감싸개는 안을 들여다본다. block은 try/if가 본문을 담는 층이다.
            if child.type in ("try_statement", "if_statement"):
                for kid in child.children:
                    if kid.type == "block":
                        scan(kid.children)
                    elif kid.type in ("except_clause", "else_clause", "elif_clause"):
                        # 폴백 경로에서 대안 라이브러리를 import하는 경우가 있다.
                        for g in kid.children:
                            if g.type == "block":
                                scan(g.children)
                continue

            if child.type == "import_statement":
                # import a.b, c as d -> a.b, c
                for item in child.named_children:
                    if item.type == "aliased_import":
                        target = item.child_by_field_name("name")
                        if target is not None:
                            names.append(text(target))
                    elif item.type == "dotted_name":
                        names.append(text(item))

            elif child.type == "import_from_statement":
                # from a.b import c -> a.b
                # from . import c -> .
                module = child.child_by_field_name("module_name")
                if module is not None:
                    names.append(text(module))

    scan(root_node.children)

    # 같은 모듈에서 여러 이름을 가져오면 중복되므로 순서를 지키며 제거한다.
    seen = set()
    unique = []
    for name in names:
        if name not in seen:
            seen.add(name)
            unique.append(name)

    return unique
# ===================
# 실행부(계속 수정 중...)
# ===================
if __name__ == "__main__":
    tree, source = parse_file("tests/fixtures/sample.py")
    for s in walk(tree.root_node, source):
        owner = f"{s.parent}." if s.parent else ""
        print(f"{s.kind:9} {owner}{s.name:12} ({s.start_line}-{s.end_line})")
        