"""프로젝트 전역에서 사용하는 데이터 구조 정의.

파서는 Symbol을 만들고 청커가 이를 Chunk로 변환한다.
두 구조를 분리한 이유는 책임이 다르기 때문이다.
Symbol은 "어디에 무엇이 있는가"만 알고, Chunk는 실제 코드 본문과
검색·요약에 필요한 메타데이터까지 갖는다.
"""

from dataclasses import dataclass, field


@dataclass
class Symbol:
    """소스에서 추출한 함수 또는 클래스의 위치 정보.

    파서의 출력이자 청커의 입력이다. 코드 본문을 담지 않는 이유는
    파싱 단계에서는 위치만 확정하고, 본문 결합은 청킹 단계의 책임으로
    분리했기 때문이다.

    Attributes:
        name (str): 심볼 이름. 소속을 포함하지 않은 단독 이름이다.
        kind (str): "class", "method", "function" 중 하나.
            method는 클래스에 속한 함수, function은 최상단 함수다.
        start_line (int): 시작 행 번호 (1-based).
        end_line (int): 끝 행 번호 (1-based, 포함).
        parent (str | None): 상위 클래스 이름. 최상단 심볼이면 None.
    """

    name: str
    kind: str
    start_line: int
    end_line: int
    parent: str | None = None


@dataclass
class Chunk:
    """검색과 요약의 최소 단위.

    벡터DB에 저장되는 단위이며, 질문이 들어오면 이 단위로 검색해
    LLM에 전달한다. 레포 전체를 한 번에 LLM에 넣을 수 없고 넣더라도
    답변 품질이 떨어지므로, 관련된 조각만 선별해 전달하기 위한 구조다.

    Attributes:
        file (str): 레포 루트 기준 상대 경로.
        symbol (str): 소속을 포함한 전체 이름 (예: "Auth.login").
            단독 이름보다 검색 정확도가 높아 이 형태로 저장한다.
        kind (str): "class", "method", "function" 중 하나.
        start_line (int): 시작 행 번호 (1-based).
        end_line (int): 끝 행 번호 (1-based, 포함).
        code (str): 심볼의 실제 소스 코드 본문.
        parent (str | None): 상위 클래스 이름.
        calls (list[str]): 이 심볼이 호출하는 다른 심볼 이름 목록.
            "이 함수는 어디서 쓰이는가" 같은 질문은 유사도 검색이 아니라
            정확 조회로 답해야 하므로 별도 필드로 관리한다.
        summary (str | None): LLM이 생성한 한 줄 요약.
            파싱 시점에는 None이며 요약 단계에서 채워진다.
            None 여부로 재인덱싱 대상을 선별할 수 있다.
        imports (list[str]): 이 심볼이 속한 파일의 import 문 목록.
            청크는 함수 본문만 담아 파일 상단의 import가 잘리므로,
            요약 시 어떤 라이브러리를 쓰는지 모델이 알 수 없다.
            추측을 막기 위해 파일 단위 정보를 청크에 함께 싣는다.
    """

    file: str
    symbol: str
    kind: str
    start_line: int
    end_line: int
    code: str
    parent: str | None = None
    calls: list[str] = field(default_factory=list)
    summary: str | None = None
    imports: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        """벡터DB 저장용 고유 식별자.

        별도 필드로 저장하지 않고 계산하는 이유는, file이나 symbol이
        변경되었을 때 식별자가 따라 갱신되지 않아 어긋나는 것을 막기
        위해서다.

        Returns:
            str: "파일경로::심볼명" 형식의 식별자.
        """
        return f"{self.file}::{self.symbol}"