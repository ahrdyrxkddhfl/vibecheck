# VibeCheck

> 🚧 개발 중 (WIP)

AI로 짠 코드, 돌아가긴 하는데 설명은 못 하겠을 때.

**VibeCheck**는 레포를 인덱싱해서 그 코드에 대해 자연어로 묻고 답할 수 있게 해주는 CLI 도구입니다.
독스트링도 주석도 없는 레포를 주 대상으로 합니다.

```
$ whyd ask "사용자 인증은 어디서 처리돼?"

→ auth/middleware.py::verify_token (12-38)
  요청 헤더의 Bearer 토큰을 검증하고 실패 시 401을 반환합니다.
  ...
```

## 어떻게 동작하나

```
레포 → [수집] → [tree-sitter 파싱] → [청킹] → [LLM 요약] → [임베딩·벡터DB] → Q&A
```

- **tree-sitter로 파싱** — 정규식으로는 함수의 시작·끝 범위나 클래스 소속을 알아낼 수 없습니다
- **코드가 아니라 요약문을 임베딩** — 사용자는 "로그인"이라 묻지만 코드엔 `verify_token`만 있습니다. 그 간극을 요약이 메웁니다
- **답변에 근거 청크를 함께 표시** — 모델 말만 믿지 않고 원본 코드로 확인할 수 있게
- **해시 기반 캐싱** — 바뀐 파일만 다시 요약합니다

## 설치

```bash
git clone https://github.com/ahrdyrxkddhfl/vibecheck.git
cd vibecheck

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

API 키 설정:

```bash
cp .env.example .env
# .env 파일에 ANTHROPIC_API_KEY 입력
```

## 사용법

> CLI 명령 연결은 작업 중입니다. 현재는 모듈을 직접 호출합니다.

**인덱싱**

```python
from vibecheck.services.indexer import index_repo
from vibecheck.llm.anthropic import AnthropicClient
from vibecheck.store.vector import VectorStore

chunks = index_repo("경로/to/repo", AnthropicClient())
VectorStore().add(chunks)
```

**질문하기**

```python
from vibecheck.services.qa import answer

print(answer("파일 수집은 어디서 하나요?"))
```

## 요구 사항

- Python 3.11+
- Anthropic API 키

## 기술 스택

| 용도 | 사용 |
|---|---|
| 파싱 | tree-sitter |
| LLM | Anthropic (요약: Haiku / 답변: Sonnet) |
| 벡터 검색 | ChromaDB |
| 임베딩 | `paraphrase-multilingual-MiniLM-L12-v2` |
| CLI | Typer + Rich |

## 알려진 한계

독스트링이 없는 코드에서도 **무엇을 하는 코드인지**는 대체로 복원됩니다.
하지만 **왜 그렇게 짰는지**, 특히 검토했다가 버린 대안 같은 건 코드에 흔적이 남지 않아 복원할 수 없습니다.
이 경우 VibeCheck는 추측하지 않고 "코드에서 확인할 수 없다"고 답합니다.

## 로드맵

- [ ] CLI 명령 연결
- [ ] 레포 리포트 생성
- [ ] 예상 질문 자동 생성
- [ ] 호출 관계 조회 (SQLite)
- [ ] 라인별 코드 설명
- [ ] BYOK 지원

## 라이선스

MIT
