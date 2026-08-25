"""프로젝트 전역에서 사용하는 데이터 구조 정의.

파서는 Symbol을 만들고 청커가 이를 Chunk로 변환한다.
두 구조를 분리한 이유는 책임이 다르기 때문이다.
Symbol은 "어디에 무엇이 있는가"만 알고, Chunk는 실제 코드 본문과
검색·요약에 필요한 메타데이터까지 갖는다.
"""

from typing import Literal
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
        kind (str): "file", "class", "method", "function" 중 하나.
            "file"은 파일 전체를 하나로 묶은 개요 청크(L1)이며,
            함수 단위로는 담기지 않는 import 정보와 심볼 목록을 검색 대상으로 만든다.
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

@dataclass
class ClaimCheck:
    """사용자 답변에서 뽑아낸 주장 하나와 그에 대한 코드 대조 결과.

    verdict와 hedged를 분리해서 갖는 이유:
    "코드에 근거가 없다"는 사실 판정이고, "그걸 단정했느냐"는 태도 판정이다.
    둘은 독립적이며 채점에서 정반대로 작동한다. 근거 없는 주장을 단정하면
    감점이지만, 같은 주장을 "추측이다"라고 밝히면 오히려 가점이다.
    한 필드에 뭉뚱그리면 이 구분이 사라진다.

    Attributes:
        claim: 사용자 답변에서 추출한 주장 한 개. 원문 그대로가 아니라
            한 문장으로 정리된 형태.
        verdict: 근거 청크와 대조한 결과.
            - "confirmed": 근거 청크가 이 주장을 지지함
            - "contradicted": 근거 청크가 이 주장과 어긋남
            - "unverifiable": 근거 청크에 관련 내용이 없음
        hedged: 사용자가 이 주장에 유보 표현을 붙였는지 여부.
            ("~일 수도 있다", "코드에 근거는 없다" 등)
        evidence: 판정 근거가 된 위치. "파일::심볼" 형식.
            verdict가 "unverifiable"이면 None.
        note: 그렇게 판정한 이유 한 줄.
    """

    claim: str
    verdict: Literal["confirmed", "contradicted", "unverifiable"]
    hedged: bool
    evidence: str | None = None
    note: str = ""


@dataclass
class AnswerFeedback:
    """면접 답변 한 건에 대한 채점 결과.

    점수를 세 축으로 쪼개 갖는 이유:
    총점 하나만 남기면 나중에 학습 진단에서 "무엇이 약한가"를 말할 수 없다.
    "구체성은 되는데 추측을 단정한다"와 "태도는 좋은데 일반론만 한다"는
    처방이 전혀 다르며, 총점으로는 두 경우가 같은 숫자로 보인다.

    세 축에 가중치를 두지 않은 것은 의도적이다. calibration이 가장 중요하다고
    보지만, 가중치를 먼저 넣으면 채점기의 변별력 부족과 가중치 부족을
    구분할 수 없게 된다. 변별이 안 되는 것이 확인된 뒤에 손댄다.

    Attributes:
        question: 채점 대상이 된 질문.
        user_answer: 사용자가 작성한 답변 원문.
        claims: 답변에서 추출한 주장별 대조 결과.
        specificity: 구체적 근거 (0-2). 파일·함수·동작을 짚었는가.
        calibration: 확신과 추측의 구분 (0-2). 코드에 없는 것을 단정하지
            않았는가. 세 축 중 면접 통과 여부를 가장 크게 가르는 항목.
        groundedness: 코드를 읽은 흔적 (0-2). 일반론이 아니라 이 레포
            얘기인가.
        verdict_line: 한 줄 총평.
        revision: 다시 답한다면 무엇을 어떻게 고칠지. 한두 문장.
        evidence_chunks: 채점에 사용한 근거 청크의 위치 목록.
            사용자가 "코드에서 확인하기"로 넘어갈 때의 출발점이 된다.
    """

    question: str
    user_answer: str
    claims: list[ClaimCheck] = field(default_factory=list)
    specificity: int = 0
    calibration: int = 0
    groundedness: int = 0
    verdict_line: str = ""
    revision: str = ""
    evidence_chunks: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """세 축의 합 (0-6).

        표시용이자 기록용이다. 진단에는 축별 점수를 쓰고,
        총점은 "이번 답변이 나아졌는가"를 한눈에 볼 때만 쓴다.
        """
        return self.specificity + self.calibration + self.groundedness

    @property
    def risky_claims(self) -> list[ClaimCheck]:
        """근거 없이 단정한 주장들.

        면접에서 무너지는 지점이 정확히 여기다. 피드백 출력에서
        가장 먼저 보여줘야 하므로 미리 뽑아둔다.
        """
        return [
            c for c in self.claims
            if c.verdict in ("unverifiable", "contradicted") and not c.hedged
        ]