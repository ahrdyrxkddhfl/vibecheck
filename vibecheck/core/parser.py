import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from vibecheck.models import Symbol

PY_LANGUAGE = Language(tspython.language())

TARGET_TYPES = {"function_definition", "class_definition"}


def parse_file(path: str):
    with open(path, "rb") as f:
        source = f.read()
    parser = Parser(PY_LANGUAGE)
    return parser.parse(source), source


def walk(node, source, parent=None, results=None):
    if results is None:
        results = []

    next_parent = parent

    if node.type in TARGET_TYPES:
        name_node = node.child_by_field_name("name")
        name = source[name_node.start_byte:name_node.end_byte].decode()

        if node.type == "class_definition":
            kind = "class"
        elif parent is not None:
            kind = "method"
        else:
            kind = "function"

        results.append(Symbol(
            name=name,
            kind=kind,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            parent=parent,
        ))

        next_parent = name

    for child in node.children:
        walk(child, source, next_parent, results)

    return results

# 실행부(계속 수정 중...)
if __name__ == "__main__":
    tree, source = parse_file("sample.py")
    for s in walk(tree.root_node, source):
        owner = f"{s.parent}." if s.parent else ""
        print(f"{s.kind:9} {owner}{s.name:12} ({s.start_line}-{s.end_line})")
        