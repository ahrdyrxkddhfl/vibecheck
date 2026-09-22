"""Java 지원의 핵심 규칙을 지킨다.

Javadoc이 청크 범위에 들어오는지, 오버로딩한 메서드의 id가 갈라지는지,
파일 설명과 import가 제대로 뽑히는지 본다. 셋 다 claim-trace를 인덱싱하며
처음 확인한 것이고, 어긋나면 에러 없이 조용히 결과만 나빠지는 종류다.
"""

from vibecheck.core import java
from vibecheck.core.chunker import to_chunks
from vibecheck.core.languages import JAVA, spec_for
from vibecheck.core.parser import parse_file, walk

SOURCE = """package com.example;

import java.util.List;
import static org.junit.Assert.assertEquals;
import com.example.domain.*;

/**
 * 청구를 심사한다.
 *
 * <p>두 번째 문단.
 */
public class Reviewer {

    /** 기본 생성자. */
    public Reviewer() {}

    /**
     * 금액으로 심사한다.
     */
    public int review(int amount) { return amount; }

    public int review(String memo) { return 0; }
}
"""


def parse(tmp_path):
    """예제 소스를 파일로 쓰고 Java 설정으로 파싱한다.

    Args:
        tmp_path: pytest가 주는 임시 폴더.

    Returns:
        tuple: (문법 트리, 소스 바이트, 심볼 목록).
    """
    path = tmp_path / "Reviewer.java"
    path.write_text(SOURCE, encoding="utf-8")

    spec = spec_for(path)
    assert spec is JAVA

    tree, source = parse_file(str(path), spec.language)
    symbols = walk(
        tree.root_node,
        source,
        class_types=spec.class_types,
        function_types=spec.function_types,
        doc_comment=spec.doc_comment,
    )
    return tree, source, symbols


def test_javadoc이_심볼_범위에_들어온다(tmp_path):
    """선언 앞의 Javadoc까지 잘라야 설명이 청크에 남는다."""
    _, source, symbols = parse(tmp_path)
    chunks = {c.symbol: c for c in to_chunks(symbols, source, "Reviewer.java")}

    assert chunks["Reviewer"].code.startswith("/**\n * 청구를 심사한다.")
    assert chunks["Reviewer.review"].code.lstrip().startswith("/**")
    # Javadoc이 없는 메서드는 선언 줄에서 시작한다.
    assert chunks["Reviewer.review#2"].code.lstrip().startswith("public int review(String")


def test_오버로딩한_메서드는_id가_갈라진다(tmp_path):
    """같은 이름이 두 번 나오면 두 번째부터 순번을 붙인다."""
    _, source, symbols = parse(tmp_path)
    chunks = to_chunks(symbols, source, "Reviewer.java")
    ids = [c.id for c in chunks]

    assert len(ids) == len(set(ids))
    assert "Reviewer.java::Reviewer.review" in ids
    assert "Reviewer.java::Reviewer.review#2" in ids
    # 생성자는 클래스 이름과 같아도 부모가 붙어 클래스 청크와 겹치지 않는다.
    assert "Reviewer.java::Reviewer.Reviewer" in ids


def test_파일_설명과_import를_뽑는다(tmp_path):
    """최상위 타입의 Javadoc이 파일 설명이 되고, import는 이름만 남는다."""
    tree, source, _ = parse(tmp_path)

    doc = java.extract_file_doc(tree.root_node, source)
    assert doc.splitlines()[0] == "청구를 심사한다."
    assert "*" not in doc

    assert java.extract_imports(tree.root_node, source) == [
        "java.util.List",
        "org.junit.Assert.assertEquals",
        "com.example.domain",
    ]
