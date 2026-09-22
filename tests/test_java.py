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


def test_답변이_짚은_java_파일을_잡는다():
    """채점이 답변 속 .java 경로를 파일 근거로 가져오려면 먼저 잡혀야 한다.

    경로 무늬가 .py만 알던 때는 Java 답변이 파일을 정확히 짚어도 근거를
    가져오지 못했다. 한글 조사가 바로 붙는 경우도 함께 본다.
    """
    from vibecheck.services.practice import PATH_PATTERN

    answer = "RuleEvaluator.java가 service/ClaimService.java를 부르고 cli.py도 본다"
    assert PATH_PATTERN.findall(answer) == [
        "RuleEvaluator.java",
        "service/ClaimService.java",
        "cli.py",
    ]


def test_클래스_이름만_써도_java_파일을_가져온다():
    """Java는 공개 클래스 이름이 파일 이름이라 확장자 없이 짚어도 파일이 정해진다.

    이름이 두 파일에 걸리면(다른 패키지의 같은 이름) 짐작하지 않고 건너뛴다.
    파이썬은 그런 규칙이 없어 모듈 이름만으로는 가져오지 않는다.
    레포에 없는 대문자 낱말은 걸리지 않는다. 나온 자리 순서를 지킨다.
    """
    from vibecheck.models import Chunk
    from vibecheck.services.practice import find_mentioned_files

    def file_chunk(path):
        return Chunk(file=path, symbol=path, kind="file", start_line=1, end_line=1, code="")

    chunks = [
        file_chunk("src/service/RuleEvaluator.java"),
        file_chunk("src/domain/Claim.java"),
        file_chunk("src/dto/Claim.java"),
        file_chunk("src/Review.java"),
        file_chunk("vibecheck/Practice.py"),
    ]
    answer = (
        "Spring API에서 Review.approve를 부르고, RuleEvaluator가 조건을 읽으며, "
        "Claim은 두 곳에 있고 Practice는 파이썬이다. src/domain/Claim.java도 본다."
    )

    assert [c.file for c in find_mentioned_files(answer, chunks)] == [
        "src/Review.java",
        "src/service/RuleEvaluator.java",
        "src/domain/Claim.java",
    ]


def test_관계도는_java_파일을_타입_참조로_잇는다(tmp_path):
    """import 없이 쓰는 같은 패키지 클래스와 정적 멤버 호출도 연결로 잡는다.

    Java는 호출을 수집하지 않으므로 관계도가 비어 있었다. 코드에 나온 클래스
    이름으로 파일을 잇는다. 이름이 두 파일에 걸리는 클래스는 짐작하지 않고,
    주석에만 나온 이름은 세지 않는다.
    """
    from vibecheck.models import Chunk
    from vibecheck.services.relations import file_relations

    files = {
        "a/Service.java": (
            "class Service {\n"
            "  private Repo repo;            // 같은 패키지, import 없음\n"
            "  void run() { Codes.check(); } // 정적 멤버\n"
            "  /* Ghost 는 주석이라 세지 않는다 */\n"
            "  Dup dup;\n"
            "}\n"
        ),
        "a/Repo.java": "class Repo {}\n",
        "a/Codes.java": "class Codes { static void check() {} }\n",
        "a/Ghost.java": "class Ghost {}\n",
        "a/Dup.java": "class Dup {}\n",
        "b/Dup.java": "class Dup {}\n",
        "a/Controller.java": "class Controller { Service s = new Service(); }\n",
    }
    chunks = []
    for rel, code in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")
        name = path.stem
        chunks.append(Chunk(file=rel, symbol=rel, kind="file", start_line=1, end_line=1, code=""))
        chunks.append(Chunk(file=rel, symbol=name, kind="class", start_line=1, end_line=1, code=""))

    rel = file_relations(chunks, "a/Service.java", tmp_path)

    assert rel["relation"] == "types"
    assert sorted(n["file"] for n in rel["calls"]) == ["a/Codes.java", "a/Repo.java"]
    assert [n["file"] for n in rel["called_by"]] == ["a/Controller.java"]
