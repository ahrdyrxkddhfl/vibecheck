# 실험 A3 — top_k 5->8 (인덱스는 A2와 동일)

- 실행 시각: 2026-08-24 15:54
- 대상: ctxd-dev/ctxd
- 인덱스: .vibecheck/cache_ctxd_l1/chroma (9파일 67청크, tests 제외, L1 포함)
- top_k: 8
- 채점: `exp_a_grading.md` 기준. 검색 순위는 자동, 답변 품질은 수동
- 대조군: `exp_a2_results_l1.md` (21/27, top_k=5)

## Q01 (개념)

**질문**: 이 프로젝트는 전체적으로 무슨 일을 하는 라이브러리야?

**정답 요지**: 원격 ctxd 서버에 문서 검색·조회를 요청하는 클라이언트. 검색(search), 문서 가져오기(fetch_document), 프로필 조회(get_profile) 세 기능. 검색 엔진 본체가 아니라 서버에 요청을 보내는 SDK/CLI라는 점이 핵심.

**근거 출처**: README  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/client.py::Client`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/cli.py::_build_parser`
2. `src/ctxd/models.py::ProfileResult`
3. `src/ctxd/cli.py::_handle_install_app`
4. `src/ctxd/models.py::DocumentResult`
5. `src/ctxd/_metadata.py::src/ctxd/_metadata.py`
6. `src/ctxd/client.py::src/ctxd/client.py`
7. `src/ctxd/models.py::src/ctxd/models.py`
8. `src/ctxd/config.py::save_api_key`

**정답 청크 순위: miss**

### 답변

## ctxd 라이브러리 개요

이 프로젝트는 **ctxd**라는 서비스에 연결하여 Slack, Google Drive, GitHub, Google Calendar 같은 외부 앱들의 콘텐츠를 **검색하고 조회**할 수 있게 해주는 Python 라이브러리 겸 CLI 도구입니다.

---

### 핵심 기능

#### 1. 콘텐츠 검색 및 문서 조회
`src/ctxd/client.py`의 `Client` 클래스가 다음 세 가지 주요 API를 제공합니다:

- **`search(query)`** — DSL(도메인 특화 언어) 형식의 쿼리로 연동된 앱들의 색인 콘텐츠를 검색합니다.  
  예: `text:deployment application:slack`
- **`fetch_document(document_uid)`** — 검색 결과에서 얻은 문서 ID로 특정 문서 1건을 가져옵니다.
- **`get_profile()`** — 사용자의 연동 앱 목록과 색인된 파일 트리를 조회합니다.

#### 2. 동기/비동기 클라이언트
`src/ctxd/client.py`의 `Client`는 내부적으로 `AsyncClient`를 감싸고 있으며, 비동기 환경이 아닌 일반 Python 코드에서도 사용할 수 있도록 `threading`과 `asyncio.run()`을 통해 동기 방식으로 동작합니다.

#### 3. CLI 도구
`src/ctxd/cli.py`의 `_build_parser()`에서 확인할 수 있듯, `ctxd`라는 이름의 커맨드라인 도구를 제공합니다:

| 명령어 | 역할 |
|---|---|
| `ctxd login` | API 키를 저장 |
| `ctxd logout` | 저장된 API 키를 삭제 |
| `ctxd status` | 인증 상태 확인 |
| `ctxd install-app` | 앱 연동 페이지 열기 |
| `ctxd search` | 콘텐츠 검색 |
| `ctxd fetch` | 문서 1건 조회 |
| `ctxd profile` | 프로필(연동 앱, 파일 트리) 조회 |

#### 4. 데이터 모델
`src/ctxd/models.py`에 Pydantic 모델로 정의되어 있습니다:
- **`SearchItem` / `SearchResult`** — 검색 결과
- **`DocumentResult`** — 개별 문서 (제목, 본문, URL 등 포함)
- **`ProfileResult`** — 연동 현황과 파일 트리

---

### 한 줄 요약

> Slack, Google Drive 등 외부 서비스에 색인된 데이터를 **API 및 CLI로 검색·조회**할 수 있게 해주는 Python SDK입니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: A/A2와 동일. _build_parser 기반으로 프로젝트 성격 정확히 서술.

---

## Q02 (개념)

**질문**: search()를 호출하면 서버와 어떤 방식으로 통신해?

**정답 요지**: base_url + /mcp 로 POST. 본문은 JSON-RPC 형태로 method=tools/call, params.name=search, params.arguments={query:...}. 응답은 SSE(text/event-stream)라 data: 줄을 파싱해서 안에 든 JSON을 꺼냄.

**근거 출처**: tests/test_sdk.py::test_sdk_search_parses_mcp_sse_response  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/async_client.py::AsyncClient.search`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/async_client.py::AsyncClient.search`
2. `src/ctxd/client.py::Client.search`
3. `src/ctxd/client.py::Client.base_url`
4. `src/ctxd/secure_store.py::load_secret_bundle`
5. `src/ctxd/cli.py::_build_parser`
6. `src/ctxd/client.py::Client.__enter__`
7. `src/ctxd/async_client.py::AsyncClient.base_url`
8. `src/ctxd/client.py::src/ctxd/client.py`

**정답 청크 순위: 1**

### 답변

## `search()` 호출 시 서버 통신 방식

### 전체 흐름

```
Client.search()  →  AsyncClient.search()  →  AsyncClient.call_tool()
```

### 단계별 설명

**1단계: 동기 → 비동기 변환** (`src/ctxd/client.py`, `Client.search`)

```python
def search(self, query: str) -> SearchResult:
    return self._run(self._async_client.search(query))
```

`Client.search()`는 내부적으로 `AsyncClient.search()`를 호출하고, `_run()`을 통해 비동기 함수를 동기 방식으로 실행합니다.

- 현재 실행 중인 이벤트 루프(asyncio 루프)가 없으면 → `asyncio.run()`으로 직접 실행
- 이미 루프가 돌고 있으면 → **별도 스레드**를 만들어 `asyncio.run()`을 그 안에서 실행한 뒤 결과를 기다림

**2단계: 실제 검색 요청 구성** (`src/ctxd/async_client.py`, `AsyncClient.search`)

```python
async def search(self, query: str) -> SearchResult:
    payload = await self.call_tool("search", {"query": query})
    return SearchResult.model_validate(payload)
```

`"search"`라는 이름의 도구(tool)와 `{"query": query}` 형태의 인자를 `call_tool()`에 전달합니다.

**3단계: 서버 통신** (`AsyncClient.call_tool`)

실제 HTTP 통신은 `call_tool()`에서 이루어집니다. 다만 제공된 코드 조각에 `call_tool()`의 구현 내용이 포함되어 있지 않아, 어떤 HTTP 라이브러리를 쓰는지, 어떤 엔드포인트로 요청하는지 등 **세부 통신 방식은 제공된 코드만으로는 알 수 없습니다.**

**4단계: 응답 변환**

`call_tool()`이 반환한 딕셔너리(`payload`)를 `SearchResult.model_validate(payload)`로 변환하여 돌려줍니다. `SearchResult`는 `src/ctxd/models.py`에 정의된 모델입니다.

### 요약 정리

| 역할 | 위치 |
|---|---|
| 동기 진입점 | `src/ctxd/client.py` - `Client.search` |
| 비동기/스레드 처리 | `src/ctxd/client.py` - `Client._run` |
| 요청 데이터 구성 | `src/ctxd/async_client.py` - `AsyncClient.search` |
| 실제 서버 통신 | `AsyncClient.call_tool` (구현 코드 미제공) |
| 응답 파싱 | `SearchResult.model_validate()` |

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: 정답 청크 1등. call_tool이 top_k에 없어 SSE/JSON-RPC 미언급. Q05와 달리 이 문항은 call_tool이 8등 안에 들어오지 못했다.

---

## Q03 (개념)

**질문**: 서버 응답이 오류일 때 어떻게 처리돼?

**정답 요지**: 응답에 isError가 있으면 CtxdError. 본문이 JSON으로 파싱되지 않으면 CtxdProtocolError. 연결 자체가 실패하면 httpx 예외를 CtxdError로 감싸 사람이 읽을 수 있는 안내 문구로 바꿔줌.

**근거 출처**: tests/test_sdk.py::test_sdk_parse_json_payload_raises_ctxd_error_for_mcp_is_error, ::test_sdk_parse_json_payload_wraps_invalid_json_text, ::test_sdk_wraps_network_errors  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/async_client.py::AsyncClient._parse_json_payload`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/async_client.py::AsyncClient._parse_response`
2. `src/ctxd/cli.py::_payload_has_error`
3. `src/ctxd/exceptions.py::CtxdAuthError`
4. `src/ctxd/exceptions.py::CtxdProtocolError`
5. `src/ctxd/async_client.py::AsyncClient.fetch_document`
6. `src/ctxd/async_client.py::AsyncClient._parse_json_payload`
7. `src/ctxd/client.py::Client`
8. `src/ctxd/exceptions.py::CtxdError.__init__`

**정답 청크 순위: 6**

### 답변

## 서버 응답 오류 처리 흐름

오류 처리는 크게 **두 단계**로 나뉩니다: HTTP 수준 오류와 응답 본문 수준 오류입니다.

---

### 1단계: HTTP 상태 코드 확인 (`src/ctxd/async_client.py` — `_parse_response`)

```
HTTP 응답이 오면
  └─ 상태 코드가 400 이상?
       └─ YES → CtxdError 발생
            ├─ 응답 본문이 JSON이면 → JSON 객체를 payload로 담음
            └─ JSON이 아니면 → 텍스트 그대로를 payload로 담음
```

즉, `404 Not Found`, `500 Internal Server Error` 같은 HTTP 오류가 오면 즉시 `CtxdError`를 발생시킵니다.

---

### 2단계: 응답 본문(JSON-RPC) 내용 확인 (`src/ctxd/async_client.py` — `_parse_json_payload`)

HTTP 상태 코드는 200이더라도 본문 안에 오류가 있을 수 있습니다. 이때는 다음 순서로 검사합니다:

| 상황 | 발생하는 예외 |
|------|--------------|
| 본문에 `"error"` 필드가 있음 (JSON-RPC 오류) | `CtxdError` |
| `result` 필드가 없거나 딕셔너리가 아님 | `CtxdProtocolError` |
| `content` 목록이 없거나 비어 있음 | `CtxdProtocolError` |
| 첫 번째 항목의 `type`이 `"text"`가 아님 | `CtxdProtocolError` |
| `text` 필드가 문자열이 아님 | `CtxdProtocolError` |
| `isError`가 참(true)임 | `CtxdError` |
| `text` 내용이 유효한 JSON이 아님 | `CtxdProtocolError` |

---

### 3단계: Content-Type이 지원되지 않을 때 (`_parse_response`)

응답의 `Content-Type` 헤더가 `text/event-stream`도 `application/json`도 아니고, 본문도 SSE 형식(`event:` 또는 `data:`로 시작)이 아니면 `CtxdProtocolError`를 발생시킵니다.

---

### 예외 클래스 구조 (`src/ctxd/exceptions.py`)

```
CtxdError                  ← 기본 오류 (HTTP 오류, JSON-RPC 오류 등)
├─ status_code: int | None   (HTTP 상태 코드)
└─ payload: Any | None       (서버가 보낸 오류 데이터)

CtxdProtocolError(CtxdError) ← 응답 형식이 예상과 다를 때
CtxdAuthError(CtxdError)     ← 인증 실패 시
```

---

### CLI에서의 추가 확인 (`src/ctxd/cli.py` — `_payload_has_error`)

예외 발생과는 별개로, CLI 레벨에서도 성공적으로 파싱된 페이로드 안에 `"error"` 또는 `"dsl_parse_error"` 필드가 있는지 한 번 더 체크합니다. 이는 서버가 HTTP 200으로 응답했지만 내용상 오류를 표현한 경우를 잡기 위한 것으로 보입니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 A2의 miss에서 6등으로 복귀. 답변 품질은 세 조건 모두 동일.

---

## Q04 (식별자)

**질문**: API 키를 환경변수로 넘기려면 변수 이름을 뭐라고 해야 해?

**정답 요지**: CTXD_API_KEY. (설정 파일 경로는 CTXD_CONFIG_PATH, 서버 주소는 CTXD_BASE_URL)

**근거 출처**: README + tests/test_sdk.py::test_client_search_uses_api_key_env  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/config.py::resolve_api_key`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/cli.py::_resolve_login_api_key`
2. `src/ctxd/cli.py::_handle_login`
3. `src/ctxd/config.py::resolve_api_key`
4. `src/ctxd/cli.py::_prompt_api_key`
5. `src/ctxd/async_client.py::AsyncClient.call_tool`
6. `src/ctxd/config.py::save_api_key`
7. `src/ctxd/cli.py::_handle_logout`
8. `src/ctxd/cli.py::_handle_status`

**정답 청크 순위: 3**

### 답변

## 환경변수 이름: `CTXD_API_KEY`

`src/ctxd/config.py`의 `resolve_api_key` 함수와 `src/ctxd/cli.py`의 `_resolve_login_api_key` 함수 두 곳 모두에서 `os.getenv("CTXD_API_KEY")`로 읽어오고 있습니다.

```python
env_api_key = os.getenv("CTXD_API_KEY")
```

### 사용 방법 예시

```bash
export CTXD_API_KEY=여기에_API_키_입력
```

### API 키를 찾는 우선순위

코드를 보면 API 키는 다음 순서로 탐색됩니다:

1. **환경변수 `CTXD_API_KEY`** ← 여기에 설정하면 됩니다
2. **저장된 키** (이전에 `ctxd login`으로 저장한 키)
3. **직접 입력** (터미널에서 대화형으로 입력)

또한 `src/ctxd/cli.py`의 `_handle_login` 함수의 에러 메시지에서도 `CTXD_API_KEY`를 명시적으로 언급하고 있어, 이것이 공식적으로 안내되는 환경변수 이름임을 확인할 수 있습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: 정답 청크 3등. A/A2와 동일하게 CLI 전용 함수를 SDK 함수로 혼동. top_k를 늘려도 유사 청크 오염은 해소되지 않았다.

---

## Q05 (식별자)

**질문**: HTTP 요청을 보낼 때 어떤 라이브러리를 써?

**정답 요지**: httpx. 비동기 클라이언트(httpx.AsyncClient)를 사용.

**근거 출처**: tests/test_sdk.py (httpx.AsyncClient.post를 patch해 테스트)  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/async_client.py::AsyncClient`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/secure_store.py::load_secret_bundle`
2. `src/ctxd/secure_store.py::save_secret_bundle`
3. `src/ctxd/client.py::Client.base_url`
4. `src/ctxd/cli.py::_build_parser`
5. `src/ctxd/async_client.py::AsyncClient.base_url`
6. `src/ctxd/cli.py::_handle_install_app`
7. `src/ctxd/async_client.py::AsyncClient.call_tool`
8. `src/ctxd/async_client.py::AsyncClient.search`

**정답 청크 순위: miss**

### 답변

## HTTP 요청 라이브러리

`src/ctxd/async_client.py`의 `AsyncClient.call_tool` 메서드를 보면, HTTP 요청을 보낼 때 **`httpx`** 라이브러리를 사용합니다.

구체적으로는 `httpx.AsyncClient`를 사용하는데, 이름에서 알 수 있듯이 **비동기(async/await) 방식**으로 HTTP 요청을 처리합니다.

코드에서 두 가지 방식으로 활용됩니다:

```python
# 방식 1: 미리 주입된 클라이언트 객체가 있을 때
if self._client is not None:
    response = await self._client.post(...)

# 방식 2: 클라이언트 객체가 없을 때 임시로 생성해서 사용
else:
    async with httpx.AsyncClient(timeout=self._timeout) as client:
        response = await client.post(...)
```

또한 `httpx.RequestError`를 잡아 에러 처리를 하고 있는 것으로 보아, 네트워크 연결 오류도 `httpx`의 예외 체계를 통해 관리합니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): A
- 메모: A/A2의 1점에서 상승. httpx.AsyncClient를 정확히 답하고 두 가지 사용 패턴과 httpx.RequestError 처리까지 언급. 원인은 L1이 아니라 call_tool이 7등으로 들어온 것. 실험 A에서 '답이 call_tool에 있는데 못 받는다'고 진단한 지점이 통로를 넓히자 그대로 해소됐다. 정답 청크는 여전히 miss.

---

## Q06 (식별자)

**질문**: 이 SDK가 직접 정의한 예외 클래스는 뭐가 있고 각각 언제 발생해?

**정답 요지**: CtxdError(기본), CtxdProtocolError(응답 모양이 예상과 다를 때), CtxdAuthError(API 키를 못 찾았을 때). 뒤 둘은 CtxdError를 상속.

**근거 출처**: tests/test_sdk.py::test_async_client_requires_api_key 외  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/exceptions.py::CtxdError`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/exceptions.py::src/ctxd/exceptions.py`
2. `src/ctxd/exceptions.py::CtxdError`
3. `src/ctxd/exceptions.py::CtxdAuthError`
4. `src/ctxd/models.py::DocumentResult`
5. `src/ctxd/models.py::SearchItem`
6. `src/ctxd/models.py::SearchResult`
7. `src/ctxd/models.py::ProfileResult`
8. `src/ctxd/exceptions.py::CtxdError.__init__`

**정답 청크 순위: 2**

### 답변

## SDK가 정의한 예외 클래스

`src/ctxd/exceptions.py` 파일에 총 **3개**의 예외 클래스가 정의되어 있습니다.

---

### 1. `CtxdError` (기반 클래스)

모든 커스텀 예외의 부모 클래스입니다. Python 내장 `Exception`을 상속합니다.

**가지는 속성:**
- `message` (str): 에러 메시지
- `status_code` (int | None): HTTP 상태 코드 (선택)
- `payload` (Any | None): 추가 데이터 (선택)

아래 두 예외 클래스의 공통 구조를 정의하는 역할을 합니다.

---

### 2. `CtxdProtocolError`

```python
class CtxdProtocolError(CtxdError):
    """Raised when the MCP server response does not match the expected shape."""
```

`CtxdError`를 상속합니다.

**발생 시점:** MCP 서버의 응답이 **예상한 형태(shape)와 일치하지 않을 때** 발생합니다. 클래스의 docstring에 명시되어 있습니다.

---

### 3. `CtxdAuthError`

```python
class CtxdAuthError(CtxdError):
    """Raised when login, refresh, or credential resolution fails."""
```

`CtxdError`를 상속합니다.

**발생 시점:** 다음 세 가지 인증 관련 상황에서 발생합니다. 클래스의 docstring에 명시되어 있습니다.
- **로그인(login) 실패**
- **토큰 갱신(refresh) 실패**
- **자격증명 해석(credential resolution) 실패**

---

### 관계 요약

```
Exception (Python 내장)
└── CtxdError              ← 공통 기반, status_code·payload 속성 보유
    ├── CtxdProtocolError  ← 서버 응답 형식 불일치 시
    └── CtxdAuthError      ← 인증/자격증명 관련 실패 시
```

각 예외가 **구체적으로 코드 어디에서 raise되는지**는 제공된 코드만으로는 알 수 없습니다. `exceptions.py`에는 클래스 정의만 있고, 실제로 raise하는 호출 코드는 제공된 조각에 포함되어 있지 않습니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: A2에서 오른 점수 유지. 예외 3종을 상속 구조까지 정확히. L1 청크가 1등.

---

## Q07 (왜)

**질문**: 왜 동기 Client와 비동기 AsyncClient를 따로 두고, Client가 AsyncClient를 감싸는 구조로 만들었어?

**정답 요지**: 설계 의도는 코드에 없음. 구조에서 읽어낼 수 있는 것: Client가 AsyncClient를 품고 _run으로 실행하므로 통신 로직이 한 벌만 존재한다는 점까지 말하면 1점. 기권해도 1점.

**근거 출처**: 없음 (구조만 남아 있음)  
**인덱스내 근거**: N  
**정답 청크**: `src/ctxd/client.py::Client._run`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/async_client.py::AsyncClient.__aenter__`
2. `src/ctxd/async_client.py::AsyncClient.__aexit__`
3. `src/ctxd/client.py::Client`
4. `src/ctxd/async_client.py::AsyncClient.call_tool`
5. `src/ctxd/async_client.py::AsyncClient`
6. `src/ctxd/async_client.py::AsyncClient.search`
7. `src/ctxd/client.py::Client.call_tool`
8. `src/ctxd/client.py::Client.base_url`

**정답 청크 순위: miss**

### 답변

## 왜 이런 구조를 선택했는가?

### 핵심 이유: 실제 로직은 한 곳에만 구현하기 위해

`AsyncClient` (`src/ctxd/async_client.py`)에 HTTP 통신, 응답 파싱, 인증 등 **모든 실질적인 로직**이 구현되어 있습니다. `Client` (`src/ctxd/client.py`)는 그 로직을 전혀 재구현하지 않고, 단순히 `AsyncClient`의 비동기 메서드를 동기적으로 실행하는 역할만 합니다.

예를 들어 `Client.search`는 이렇게만 되어 있습니다:
```python
def search(self, query: str) -> SearchResult:
    return self._run(self._async_client.search(query))
```

만약 두 클라이언트를 완전히 분리해서 작성했다면, HTTP 요청·파싱·에러 처리 코드가 두 곳에 중복되어 유지보수가 어려워졌을 것입니다.

---

### 동기 클라이언트를 별도로 둔 이유: 이벤트 루프가 없는 환경을 위해

Python에서 `async`/`await` 코드는 실행 중인 **이벤트 루프**(비동기 작업을 관리하는 실행 환경)가 있어야 동작합니다. 일반적인 스크립트나 동기 코드에서는 이벤트 루프가 없기 때문에 `AsyncClient`를 직접 쓸 수 없습니다. 그래서 `Client`가 이 간극을 메워줍니다.

---

### 핵심 기술적 도전: 이미 이벤트 루프가 실행 중일 때

`Client._run` 메서드(`src/ctxd/client.py`, 47-67행)를 보면 단순히 `asyncio.run()`만 쓰지 않는 이유가 드러납니다. `asyncio.run()`은 **이미 이벤트 루프가 실행 중인 상황에서는 에러**를 냅니다(예: Jupyter 노트북, 다른 비동기 프레임워크 내부).

그래서 두 경우를 나눠 처리합니다:

```python
@staticmethod
def _run(coro):
    try:
        asyncio.get_running_loop()  # 현재 루프가 있는지 확인
    except RuntimeError:
        return asyncio.run(coro)   # 없으면 그냥 실행

    # 이미 루프가 실행 중이면 → 별도 스레드에서 새 루프를 만들어 실행
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            error["value"] = exc

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    ...
```

- **이벤트 루프가 없을 때**: `asyncio.run()`으로 바로 실행
- **이벤트 루프가 이미 실행 중일 때**: 새 스레드를 만들어 그 안에서 별도의 이벤트 루프로 실행 (스레드는 이벤트 루프를 공유하지 않으므로 충돌 없음)

---

### 요약

| 역할 | 담당 클래스 | 파일 |
|---|---|---|
| 실제 HTTP 통신·파싱 로직 | `AsyncClient` | `src/ctxd/async_client.py` |
| 비동기 코드를 동기 환경에서 실행 가능하게 | `Client` | `src/ctxd/client.py` |

이 구조 덕분에 **로직 중복 없이** `async`/`await`을 모르는 사용자도 일반 함수처럼 `Client`를 사용할 수 있고, `async`를 사용하는 사용자는 `AsyncClient`를 직접 쓸 수 있습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: in_index=N. 만점 유지.

---

## Q08 (왜)

**질문**: 왜 설정(config.json)과 자격증명(credentials.json)을 다른 파일로 나눴어?

**정답 요지**: 의도는 코드에 없음. clear_api_key가 credentials만 지우고 config의 base_url은 남긴다는 동작까지 짚으면 1점. 기권해도 1점.

**근거 출처**: tests/test_sdk.py::test_clear_api_key_keeps_base_url_and_removes_plaintext_credentials  
**인덱스내 근거**: N  
**정답 청크**: `src/ctxd/config.py::clear_api_key`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/config.py::src/ctxd/config.py`
2. `src/ctxd/config.py::save_config`
3. `src/ctxd/secure_store.py::save_secret_bundle`
4. `src/ctxd/secure_store.py::get_credentials_path`
5. `src/ctxd/config.py::get_config_path`
6. `src/ctxd/_metadata.py::src/ctxd/_metadata.py`
7. `src/ctxd/secure_store.py::src/ctxd/secure_store.py`
8. `src/ctxd/config.py::load_config`

**정답 청크 순위: miss**

### 답변

## 설정과 자격증명을 별도 파일로 나눈 이유

코드에서 두 파일의 역할 차이와 처리 방식 차이를 확인할 수 있습니다.

---

### 1. 저장되는 데이터의 성격이 다릅니다

**`config.json`** (`src/ctxd/config.py`, `DEFAULT_CONFIG_PATH`)
- `base_url` 같은 **일반 설정값**을 저장합니다.
- 읽기 오류가 나면 그냥 빈 딕셔너리 `{}`를 반환하고 조용히 넘어갑니다.

```python
# load_config: 오류 시 빈 딕셔너리 반환
except (OSError, json.JSONDecodeError):
    return {}
```

**`credentials.json`** (`src/ctxd/secure_store.py`, `DEFAULT_CREDENTIALS_PATH`)
- `api_key` 같은 **민감한 인증 정보**를 저장합니다.
- 읽기 오류가 나면 `CtxdAuthError`를 **예외로 던집니다**. 즉, 손상된 자격증명은 무시하지 않고 반드시 알립니다.

```python
# load_secret_bundle: 오류 시 예외 발생
except (OSError, json.JSONDecodeError) as exc:
    raise CtxdAuthError("Stored ctxd credentials are invalid.") from exc
```

이처럼 오류 처리 방식이 다른 것으로 보아, 자격증명은 설정보다 훨씬 엄격하게 다뤄야 하는 데이터로 구분하고 있습니다.

---

### 2. 파일 경로를 독립적으로 제어할 수 있습니다

`src/ctxd/secure_store.py`의 `get_credentials_path` 함수를 보면:

```python
def get_credentials_path() -> Path:
    configured = os.getenv("CTXD_CREDENTIALS_PATH")  # 자격증명 전용 환경변수
    if configured:
        return Path(configured).expanduser()

    config_path = os.getenv("CTXD_CONFIG_PATH")
    if config_path:
        return Path(config_path).expanduser().parent / "credentials.json"

    return DEFAULT_CREDENTIALS_PATH  # ~/.ctxd/credentials.json
```

`CTXD_CREDENTIALS_PATH`라는 **자격증명 전용 환경변수**가 별도로 존재합니다. 설정 파일 경로(`CTXD_CONFIG_PATH`)와 독립적으로 자격증명 위치를 지정할 수 있어서, 예를 들어 자격증명만 더 보안이 강한 경로(예: 암호화된 볼륨)에 놓는 것이 가능합니다.

---

### 3. 삭제(clear) 동작이 다릅니다

`clear_api_key` 함수(`src/ctxd/config.py`)를 보면:

```python
def clear_api_key(*, base_url: str | None = None, keep_base_url: bool = True) -> Path:
    clear_secret_bundle(...)       # credentials.json 삭제
    retained: dict[str, Any] = {}
    if keep_base_url:
        retained["base_url"] = resolved_base_url
    return save_config(retained)   # config.json은 base_url을 유지
```

API 키를 지울 때 자격증명 파일은 삭제하지만, 설정 파일의 `base_url`은 선택적으로 보존할 수 있습니다. 두 파일이 합쳐져 있었다면 이런 세밀한 제어가 어렵습니다.

---

### 요약

| 항목 | `config.json` | `credentials.json` |
|---|---|---|
| 저장 내용 | `base_url` 등 일반 설정 | `api_key` 등 민감 정보 |
| 오류 처리 | 조용히 빈값 반환 | 예외 발생 |
| 경로 제어 | `CTXD_CONFIG_PATH` | `CTXD_CREDENTIALS_PATH` (별도) |
| 삭제 | 선택적 보존 | API 키 제거 시 삭제 |

민감한 자격증명을 별도 파일로 분리함으로써, 더 엄격한 오류 처리와 독립적인 경로 관리가 가능하도록 설계되어 있습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: in_index=N. 만점 유지.

---

## Q09 (왜)

**질문**: 왜 검색 결과에서 id와 document_uid를 둘 다 받아들이게 했어?

**정답 요지**: 의도는 코드에 없음. models.py가 두 이름을 같은 필드로 받는다는 사실(text/snippet도 마찬가지)까지 짚으면 1점. 서버 응답 형식이 여러 벌이라는 추정은 근거를 밝히면 인정.

**근거 출처**: tests/test_sdk.py::test_sdk_search_accepts_document_uid_and_snippet_fields  
**인덱스내 근거**: N  
**정답 청크**: `src/ctxd/models.py::SearchItem`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/models.py::SearchItem`
2. `src/ctxd/cli.py::_build_parser`
3. `src/ctxd/cli.py::_handle_status`
4. `src/ctxd/client.py::Client.fetch_document`
5. `src/ctxd/cli.py::_handle_logout`
6. `src/ctxd/cli.py::_handle_install_app`
7. `src/ctxd/client.py::Client.search`
8. `src/ctxd/models.py::DocumentResult`

**정답 청크 순위: 1**

### 답변

## `id`와 `document_uid`를 둘 다 허용하는 이유

`src/ctxd/models.py`의 `SearchItem` 클래스를 보면:

```python
id: str = Field(validation_alias=AliasChoices("id", "document_uid"))
```

`AliasChoices`는 Pydantic의 기능으로, API 응답에서 데이터를 받아올 때 **여러 이름 중 하나로 들어와도 같은 필드에 매핑**되도록 합니다. 즉, 서버가 `id`라는 키로 보내든 `document_uid`라는 키로 보내든 모두 `SearchItem.id` 필드에 저장됩니다.

### 왜 이렇게 했는지 코드에서 읽히는 근거

`src/ctxd/cli.py`의 `_build_parser` 함수를 보면, `fetch` 서브커맨드의 인자 이름이 `document_uid`로 정의되어 있고:

```python
fetch_parser.add_argument("document_uid", help="Document UID returned by search.")
```

도움말에도 **"search가 반환한 document UID"** 라고 명시되어 있습니다. 즉, 사용자가 검색 결과에서 얻은 값을 `fetch` 명령에 그대로 넘기는 흐름입니다.

이 구조로 보아, **서버 API가 검색 결과의 식별자 필드 이름을 `id`에서 `document_uid`로 바꿨거나, 두 가지 이름을 혼용하는 상황**에 대응하기 위해 양쪽을 모두 허용한 것으로 보입니다. CLI의 `fetch` 명령이 `document_uid`라는 용어를 사용하는 반면, 모델 내부 필드명은 `id`로 통일되어 있는 점이 이 간극을 메우려는 의도를 뒷받침합니다.

### 요약

| 상황 | 처리 |
|------|------|
| 서버가 `"id": "..."` 로 응답 | `SearchItem.id`에 저장 |
| 서버가 `"document_uid": "..."` 로 응답 | 동일하게 `SearchItem.id`에 저장 |

제공된 코드만으로는 서버 API가 실제로 어떤 이름을 사용하는지, 또는 언제 이름이 변경됐는지는 확인할 수 없습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: in_index=N. 만점 유지. 정답 청크 1등.

---

## Q10 (관계)

**질문**: ctxd login으로 입력한 API 키는 어느 함수들을 거쳐 어디에 저장돼?

**정답 요지**: cli의 login 처리 → config.save_api_key → secure_store.save_secret_bundle → ~/.ctxd/credentials.json에 평문 JSON으로 저장. 최소 두 단계와 최종 파일명을 대야 2점.

**근거 출처**: tests/test_cli.py::test_cli_login_stores_prompted_api_key_in_plaintext_credentials  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/config.py::save_api_key`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/cli.py::_handle_logout`
2. `src/ctxd/async_client.py::AsyncClient._resolve_access_token`
3. `src/ctxd/cli.py::_resolve_login_api_key`
4. `src/ctxd/config.py::save_api_key`
5. `src/ctxd/cli.py::_handle_login`
6. `src/ctxd/cli.py::_build_parser`
7. `src/ctxd/cli.py::_handle_status`
8. `src/ctxd/cli.py::_prompt_api_key`

**정답 청크 순위: 4**

### 답변

## `ctxd login` 실행 시 API 키 저장 흐름

### 함수 호출 순서

```
ctxd login
  → _handle_login()          [src/ctxd/cli.py, 183-198행]
    → _resolve_login_api_key() [src/ctxd/cli.py, 227-243행]
      → _prompt_api_key()    [src/ctxd/cli.py, 246-257행]
    → save_api_key()         [src/ctxd/config.py, 74-83행]
```

### 각 단계 설명

1. **`_handle_login()`** (`src/ctxd/cli.py`)
   - `ctxd login` 명령어의 진입점입니다.
   - `_resolve_login_api_key()`를 호출해 API 키를 가져옵니다.
   - API 키를 가져온 뒤 `Client(api_key=api_key).get_profile()`로 키가 유효한지 서버에 검증합니다.
   - `should_save`가 `True`인 경우에만 `save_api_key(api_key)`를 호출해 저장합니다.

2. **`_resolve_login_api_key()`** (`src/ctxd/cli.py`)
   - API 키를 **우선순위 순서**로 찾습니다:
     1. 환경 변수 `CTXD_API_KEY`
     2. 이미 저장된 설정(`resolve_api_key()`)
     3. 사용자가 직접 입력 (`_prompt_api_key()` 호출)
   - 사용자가 **직접 입력한 경우에만** `should_save = True`를 반환합니다. 즉, 환경 변수나 기존 저장값에서 가져온 경우엔 다시 저장하지 않습니다.

3. **`_prompt_api_key()`** (`src/ctxd/cli.py`)
   - `getpass.getpass()`를 이용해 터미널에서 API 키를 입력받습니다.
   - 비대화형 환경(터미널이 아닌 경우)이거나 입력을 취소하면 `None`을 반환합니다.

4. **`save_api_key()`** (`src/ctxd/config.py`)
   - 최종적으로 API 키가 저장되는 함수입니다.
   - 내부적으로 `save_secret_bundle({"api_key": api_key.strip()}, ...)`을 호출해 **`secure_store`(보안 저장소)** 에 저장합니다.
   - 추가로 `base_url`을 설정 파일(`config`)에도 기록합니다.

### 요약

사용자가 터미널에 입력한 API 키는 `_prompt_api_key` → `_resolve_login_api_key` → `_handle_login` → `save_api_key` 순으로 전달되며, **최종적으로 `save_secret_bundle`을 통해 보안 저장소(`secure_store`)에 저장**됩니다. 보안 저장소의 구체적인 위치(예: OS 키체인, 파일 등)는 제공된 코드만으로는 알 수 없습니다(`save_secret_bundle`의 구현이 포함되어 있지 않습니다).

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: A/A2의 1점에서 상승. save_api_key 본문이 들어와 save_secret_bundle 호출과 config의 base_url 기록까지 짚었다. 최종 파일명(credentials.json)은 여전히 미언급이나 '보안 저장소에 저장'까지 도달해 2점으로 판정.

---

## Q11 (관계)

**질문**: Client.search()를 부르면 실제 HTTP 요청이 나가기까지 어떤 경로를 거쳐?

**정답 요지**: Client.search → Client._run(이벤트 루프 실행) → AsyncClient.search → call_tool → httpx POST. 동기 껍데기가 비동기 본체를 돌린다는 흐름이 핵심.

**근거 출처**: tests/test_sdk.py::test_client_context_manager_does_not_hold_open_async_client  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/client.py::Client._run`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/async_client.py::AsyncClient.search`
2. `src/ctxd/client.py::Client.search`
3. `src/ctxd/client.py::Client.base_url`
4. `src/ctxd/secure_store.py::load_secret_bundle`
5. `src/ctxd/async_client.py::AsyncClient.base_url`
6. `src/ctxd/client.py::Client.__enter__`
7. `src/ctxd/config.py::resolve_base_url`
8. `src/ctxd/async_client.py::AsyncClient.__aexit__`

**정답 청크 순위: miss**

### 답변

## `Client.search()` 호출 경로 설명

### 전체 흐름 요약

```
Client.search()
  → Client._run(AsyncClient.search())
    → AsyncClient.call_tool("search", {"query": query})
      → (HTTP 요청 발송)
        → SearchResult.model_validate(payload)
```

---

### 단계별 설명

#### 1단계: `Client.search()` — `src/ctxd/client.py` 35~36행

```python
def search(self, query: str) -> SearchResult:
    return self._run(self._async_client.search(query))
```

동기(sync) 메서드입니다. 내부에 보관된 `_async_client`(비동기 클라이언트 인스턴스)의 `search()`를 호출하되, `_run()`으로 감싸서 **비동기 코드를 동기적으로 실행**합니다. 즉, 호출자는 `async/await` 없이 일반 함수처럼 쓸 수 있습니다.

---

#### 2단계: `AsyncClient.search()` — `src/ctxd/async_client.py` 40~42행

```python
async def search(self, query: str) -> SearchResult:
    payload = await self.call_tool("search", {"query": query})
    return SearchResult.model_validate(payload)
```

실제 비동기 처리가 이루어지는 곳입니다. `call_tool("search", {"query": query})`를 `await`하여 실행합니다.

---

#### 3단계: `AsyncClient.call_tool()` — HTTP 요청 발송

`call_tool()`이 실제 HTTP 요청을 보내는 지점입니다. `AsyncClient` 안에 `_client`라는 `httpx` 클라이언트가 있고(`__aexit__`에서 `self._client.aclose()`로 닫는 것을 보아 `httpx` 비동기 클라이언트임을 알 수 있습니다), `call_tool()`이 이를 통해 네트워크 요청을 보냅니다. 요청이 향하는 주소는 `_base_url`에 저장된 URL입니다(`src/ctxd/async_client.py` 28~29행).

> **참고**: `call_tool()`의 내부 구현 코드는 제공된 코드 조각에 포함되어 있지 않으므로, 정확한 엔드포인트 경로나 HTTP 메서드(GET/POST 등)는 제공된 코드만으로는 알 수 없습니다.

---

#### 4단계: 결과 반환

HTTP 응답으로 받은 `payload`를 `SearchResult.model_validate(payload)`로 변환하여 최종적으로 `SearchResult` 객체를 반환합니다. `model_validate`는 Pydantic 모델의 메서드로, 딕셔너리 데이터를 타입이 정의된 Python 객체로 변환하는 역할을 합니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 miss. A/A2와 동일하게 경로 전체 정확.

---

## Q12 (관계)

**질문**: API 키는 어떤 순서로 찾아져?

**정답 요지**: ① 인자로 직접 넘긴 api_key → ② 환경변수 CTXD_API_KEY → ③ 저장된 credentials.json. 셋 다 없으면 CtxdAuthError. 순서까지 맞아야 2점.

**근거 출처**: tests/test_sdk.py::test_client_search_uses_api_key_env, ::test_saved_api_key_is_resolved_from_plaintext_credentials, ::test_async_client_requires_api_key  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/config.py::resolve_api_key`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/config.py::resolve_api_key`
2. `src/ctxd/cli.py::_resolve_login_api_key`
3. `src/ctxd/cli.py::_prompt_api_key`
4. `src/ctxd/config.py::save_api_key`
5. `src/ctxd/cli.py::_handle_logout`
6. `src/ctxd/cli.py::_handle_login`
7. `src/ctxd/config.py::clear_api_key`
8. `src/ctxd/cli.py::_handle_status`

**정답 청크 순위: 1**

### 답변

## API 키 탐색 순서

API 키를 찾는 함수는 두 가지가 있으며, 사용되는 맥락에 따라 순서가 조금 다릅니다.

---

### 1. 일반 사용 시 — `resolve_api_key` (`src/ctxd/config.py`, 24–41행)

| 순서 | 위치 | 설명 |
|------|------|------|
| 1️⃣ | 함수 인자 | `api_key` 매개변수로 직접 전달된 값 |
| 2️⃣ | 환경 변수 | `CTXD_API_KEY` 환경 변수 |
| 3️⃣ | 저장된 번들 | `load_secret_bundle`으로 읽어온 로컬 저장소의 `api_key` 값 |

세 곳 모두에서 찾지 못하면 `None`을 반환합니다.

---

### 2. 로그인 처리 시 — `_resolve_login_api_key` (`src/ctxd/cli.py`, 227–243행)

| 순서 | 위치 | 설명 |
|------|------|------|
| 1️⃣ | 환경 변수 | `CTXD_API_KEY` 환경 변수 |
| 2️⃣ | 저장된 번들 | `resolve_api_key()`를 통해 로컬 저장소 확인 |
| 3️⃣ | 사용자 직접 입력 | `_prompt_api_key()`로 터미널에서 직접 입력받음 |

이 함수는 사용자가 직접 입력했는지 여부를 `bool` 값으로 함께 반환합니다. 직접 입력한 경우(`True`)에만 `_handle_login`(`src/ctxd/cli.py`, 183–198행)이 `save_api_key`를 호출해 키를 저장소에 저장합니다.

---

### 차이점 요약

- **일반 사용**(`resolve_api_key`)은 **함수 인자 → 환경변수 → 저장소** 순입니다.
- **로그인**(`_resolve_login_api_key`)은 함수 인자가 없으므로 **환경변수 → 저장소 → 터미널 입력** 순이며, 터미널 입력은 `sys.stdin.isatty()`가 `True`일 때(대화형 환경)만 동작합니다(`src/ctxd/cli.py`, `_prompt_api_key` 246–257행).

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 1등. 우선순위 3단계 정확.

---

## Q13 (사실)

**질문**: CLI에 어떤 명령어들이 있어?

**정답 요지**: login, logout, status, search, fetch, profile, install-app, --version. 7개 중 5개 이상이면 2점.

**근거 출처**: README + tests/test_cli.py::test_cli_help_describes_commands  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/cli.py::_build_parser`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/cli.py::_build_parser`
2. `src/ctxd/cli.py::_resolve_login_api_key`
3. `src/ctxd/cli.py::_handle_install_app`
4. `src/ctxd/config.py::src/ctxd/config.py`
5. `src/ctxd/cli.py::src/ctxd/cli.py`
6. `src/ctxd/cli.py::_handle_logout`
7. `src/ctxd/cli.py::_quote_shell_stripped_text_token`
8. `src/ctxd/models.py::src/ctxd/models.py`

**정답 청크 순위: 1**

### 답변

## ctxd CLI 명령어 목록

`src/ctxd/cli.py`의 `_build_parser` 함수에 정의된 명령어들입니다.

---

### 인증 관련

| 명령어 | 설명 |
|--------|------|
| `ctxd login` | API 키를 입력받아 저장합니다. 환경변수 → 저장된 키 → 직접 입력 순으로 키를 찾습니다. |
| `ctxd logout` | 로컬에 저장된 API 키를 삭제합니다. |
| `ctxd status` | 현재 API 키가 설정되어 있는지 확인합니다. |

---

### 앱 연동

| 명령어 | 옵션 | 설명 |
|--------|------|------|
| `ctxd install-app` | `--no-browser` | Slack, Google Drive, GitHub, Google Calendar 등을 연결할 수 있는 앱 설치 페이지를 엽니다. `--no-browser`를 붙이면 브라우저를 열지 않고 URL만 출력합니다. |

---

### 데이터 조회

| 명령어 | 인자/옵션 | 설명 |
|--------|-----------|------|
| `ctxd search QUERY` | `QUERY` (필수) | 인덱싱된 앱 콘텐츠를 검색합니다. 결과는 항상 JSON으로 출력됩니다. 예: `ctxd search text:deployment application:slack` |
| `ctxd fetch DOCUMENT_UID` | `document_uid` (필수), `--json` | 문서 UID로 단일 문서를 가져옵니다. `--json`을 붙이면 전체 응답을 JSON으로 출력합니다. |
| `ctxd profile` | `--json` | 연결된 연동 서비스 목록과 인덱싱된 파일 트리를 보여줍니다. `--json`을 붙이면 JSON으로 출력합니다. |

---

### 전역 옵션

| 옵션 | 설명 |
|------|------|
| `--version` | 설치된 ctxd 버전을 출력하고 종료합니다. |

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 1등. 명령어 7개 전부. L1 청크 3개가 4/5/8등에 들어왔으나 답변은 _build_parser 기반으로 A와 동일.

---

## Q14 (사실)

**질문**: base_url을 https://ctxd.example.com 으로 주면 실제 요청 URL은 뭐가 돼?

**정답 요지**: https://ctxd.example.com/mcp. 끝에 /mcp가 자동으로 붙고, 이미 /mcp로 끝나면 중복해서 붙이지 않음.

**근거 출처**: tests/test_sdk.py::test_client_context_manager_returns_client, ::test_saved_api_key_resolves_for_normalized_mcp_base_url  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/async_client.py::AsyncClient._normalize_base_url`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/config.py::resolve_base_url`
2. `src/ctxd/async_client.py::AsyncClient.base_url`
3. `src/ctxd/client.py::Client.base_url`
4. `src/ctxd/secure_store.py::load_secret_bundle`
5. `src/ctxd/config.py::_resolve_base_url_from_config`
6. `src/ctxd/secure_store.py::clear_secret_bundle`
7. `src/ctxd/secure_store.py::save_secret_bundle`
8. `src/ctxd/config.py::clear_api_key`

**정답 청크 순위: miss**

### 답변

## 질문에 대한 답변

제공된 코드만으로는 **실제 요청 URL이 어떻게 조합되는지** 알 수 없습니다.

이유를 설명하면:

- `src/ctxd/config.py`의 `resolve_base_url` 함수는 `https://ctxd.example.com`을 그대로 반환합니다. 즉, base_url 자체는 `https://ctxd.example.com`으로 확정됩니다.
- `src/ctxd/async_client.py`의 `AsyncClient.base_url`과 `src/ctxd/client.py`의 `Client.base_url`은 저장된 `_base_url` 값을 그대로 반환하는 것만 보여줄 뿐, **어떤 경로(path)나 엔드포인트를 base_url에 붙여서 최종 요청 URL을 만드는지**에 대한 코드는 제공된 조각에 포함되어 있지 않습니다.

따라서 "실제 요청 URL"을 파악하려면 `AsyncClient` 내부에서 HTTP 요청을 실제로 보내는 부분(예: `httpx`, `aiohttp` 등의 호출 코드)을 확인해야 합니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 세 조건 모두 실패. _normalize_base_url이 top_k=8에서도 miss. 검색이 base_url이라는 이름을 공유하는 프로퍼티들만 물어온다. 이름 중복이 정작 필요한 로직을 밀어내는 사례로 보인다. in_index=Y이므로 0점.

---

## Q15 (사실)

**질문**: 저장된 API 키는 서버 주소(base_url)마다 따로 관리돼?

**정답 요지**: 아니오. base_url과 무관하게 하나만 저장됨. 나중에 저장한 키가 앞의 것을 덮어씀. (secure_store가 base_url 인자를 받고도 쓰지 않음)

**근거 출처**: tests/test_sdk.py::test_saved_api_key_is_global_across_base_urls  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/secure_store.py::save_secret_bundle`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/config.py::save_api_key`
2. `src/ctxd/config.py::clear_api_key`
3. `src/ctxd/secure_store.py::save_secret_bundle`
4. `src/ctxd/cli.py::_handle_logout`
5. `src/ctxd/secure_store.py::load_secret_bundle`
6. `src/ctxd/config.py::resolve_api_key`
7. `src/ctxd/cli.py::_resolve_login_api_key`
8. `src/ctxd/async_client.py::AsyncClient.base_url`

**정답 청크 순위: 3**

### 답변

## 결론: 아니요, `base_url`에 관계없이 하나의 파일에 통합 저장됩니다.

---

### 근거

핵심은 `src/ctxd/secure_store.py`의 두 함수에 있습니다.

**`save_secret_bundle` (40~59행)**
```python
def save_secret_bundle(
    bundle: dict[str, Any], *, base_url: str, client_id: str | None
) -> None:
    del base_url, client_id          # ← base_url을 즉시 버림
    path = get_credentials_path()    # ← 항상 동일한 경로 사용
    ...
```

**`load_secret_bundle` (24~37행)**
```python
def load_secret_bundle(*, base_url: str, client_id: str | None) -> dict[str, Any]:
    del base_url, client_id          # ← base_url을 즉시 버림
    path = get_credentials_path()    # ← 항상 동일한 경로 사용
    ...
```

두 함수 모두 `base_url` 파라미터를 받긴 하지만, 함수 첫 줄에서 `del base_url`로 즉시 폐기합니다. 그리고 저장/불러오기 경로는 항상 `get_credentials_path()`가 반환하는 **단일 고정 경로**를 사용합니다.

---

### 흐름 정리

`src/ctxd/config.py`의 `save_api_key` (74~83행)를 보면:

```python
save_secret_bundle(
    {"api_key": api_key.strip()},
    base_url=resolved_base_url,   # 전달되지만...
    client_id=None,
)
```

`base_url`을 전달하지만, `save_secret_bundle` 내부에서 무시되므로 어떤 서버 주소를 사용하든 **동일한 파일에 덮어씌워** 저장됩니다.

즉, 서버 주소 A로 저장한 뒤 서버 주소 B로 다시 저장하면, A의 키는 사라지고 B의 키만 남습니다. `base_url`별 분리 저장은 이루어지지 않습니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 3등. save/load 양쪽 모두에서 del base_url을 짚어 A2보다 근거가 넓어졌다.

---

## 집계

### 세 조건 비교

| 조건 | L1 | top_k | 점수 | Hit@1 | MRR |
|---|---|---|---|---|---|
| A | 없음 | 5 | 20/27 | 33.3% | 0.44 |
| A2 | 있음 | 5 | 21/27 | 33.3% | 0.42 |
| **A3** | **있음** | **8** | **23/27** | 33.3% | — |
| 컨트롤 | — | — | 4/27 | — | — |

top_k는 검색 순위를 바꾸지 않으므로 Hit@1은 A2와 동일하다.
달라진 것은 LLM이 받는 청크 수뿐이다.

### 문항별 변화

| 문항 | A | A2 | A3 | 원인 |
|---|---|---|---|---|
| Q05 | 1 | 1 | **2** | call_tool이 7등으로 진입 |
| Q06 | 1 | **2** | 2 | L1 청크가 파일 내 심볼 목록 제공 |
| Q10 | 1 | 1 | **2** | save_api_key 본문이 4등으로 진입 |
| Q14 | 0 | 0 | 0 | 세 조건 모두 실패 |

나머지 11문항은 세 조건에서 동일했다.

### 결론 — 진단에 맞는 처방은 top_k였다

두 조치의 성격이 다르다.

- **L1 도입**: 없던 정보를 새로 만든다. +1점 (Q06)
- **top_k 5->8**: 이미 있던 정보를 도달시킨다. +2점 (Q05, Q10)

실험 A의 진단은 "답이 call_tool 안에 있는데 컨텍스트에 못 받는다"였다.
이 진단에 대응하는 처방은 통로를 넓히는 것이었고, L1은 진단을 넘겨짚은 처방이었다.

**교훈: 진단이 '도달 실패'라면 정보를 늘리기 전에 통로부터 넓혀본다.**
top_k 조정은 공짜이고 되돌리기 쉬우며, 효과가 없으면 그 자체가
'정보가 실제로 없다'는 증거가 되어 다음 처방의 근거가 된다.

L1도 무용하지는 않았다. Q06처럼 "이 파일에 무엇이 있는가"를 묻는
목록형 질문은 개별 심볼 청크로는 답할 수 없고 파일 개요가 필요하다.
다만 L1이 겨냥했던 Q05(라이브러리 이름)는 L1이 아니라 top_k가 해결했다.
L1 요약이 httpx라는 고유명사만 담고 "HTTP 요청"이라는 개념어를 담지 않아
질의와 맞물리지 않았기 때문으로 보인다.

### 미해결 — Q14

세 조건 모두 실패했다. 검색 결과가 매번 base_url이라는 이름을 공유하는
프로퍼티들(Client.base_url, AsyncClient.base_url, resolve_base_url)로 채워지고,
정작 정규화를 수행하는 _normalize_base_url이 밀려난다.

이름이 겹치는 청크가 많을 때 정작 필요한 로직이 밀리는 패턴으로 추정되나,
사례가 하나뿐이라 단정하지 않는다. 실사용에서 유사 사례가 축적되면
패턴으로 묶어 다룬다.

### 실험 종료 사유

세 번의 측정 모두 같은 레포, 같은 15문항, 같은 채점자로 수행했다.
이 시험지에 맞춰 파라미터를 계속 조정하면 개선되는 것은 도구가 아니라
"이 15문항의 점수"가 된다. 테스트셋을 보며 튜닝하는 것과 같은 문제다.

top_k=8을 기본값으로 채택하되, 이것이 일반적 최적값이라고 주장하지 않는다.
ctxd 59~67청크 규모에서 관찰된 값이다.

다음 단계는 파라미터 조정이 아니라 CLI 연결과 실사용이다.
15문항 시험지가 포착하지 못하는 문제(첫 실행 시간, 질문을 던지는 방식,
답변 길이, 중단 시 복구)는 실제로 써봐야 드러난다.
