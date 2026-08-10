from dataclasses import dataclass, field


@dataclass
class Chunk:
    # 정체
    file: str          # "app/services/auth.py"
    symbol: str        # "Auth.login"  ← 클래스 소속 포함
    kind: str          # "function" | "class" | "method"
    
    # 위치
    start_line: int
    end_line: int
    
    # 내용
    code: str
    
    # 관계
    parent: str | None = None      # "Auth"  (최상단이면 None)
    calls: list[str] = field(default_factory=list)
    
    # 나중에 채워짐
    summary: str | None = None

    @property
    def id(self) -> str:
        return f"{self.file}::{self.symbol}"

@dataclass
class Symbol:
    name: str
    kind: str
    start_line: int
    end_line: int
    parent: str | None = None