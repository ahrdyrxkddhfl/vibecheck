# 실험 D 컨트롤 — 기존 15문항 재측정 (pyproject 청크 추가 후)

- 실행 시각: 2026-08-25 12:35
- 대상: ctxd-dev/ctxd
- 인덱스: /Users/hdh22/work/vibecheck-targets/ctxd/.vibecheck/chroma (68청크, tests 제외, L1 포함, pyproject 포함)
- top_k: 8
- 목적: 새 청크가 기존 문항을 밀어냈는지 확인. Q05·Q09가 간섭 위험 최대
- 참고: A3는 23/27이었으나 그 인덱스는 소실됨. 요약이 새로 생성되어 직접 비교 불가
- 채점: `exp_a_grading.md` 기준. 검색 순위는 자동, 답변 품질은 수동

## Q01 (개념)

**질문**: 이 프로젝트는 전체적으로 무슨 일을 하는 라이브러리야?

**정답 요지**: 원격 ctxd 서버에 문서 검색·조회를 요청하는 클라이언트. 검색(search), 문서 가져오기(fetch_document), 프로필 조회(get_profile) 세 기능. 검색 엔진 본체가 아니라 서버에 요청을 보내는 SDK/CLI라는 점이 핵심.

**근거 출처**: README  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/client.py::Client`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/client.py::src/ctxd/client.py`
2. `src/ctxd/cli.py::_build_parser`
3. `src/ctxd/cli.py::src/ctxd/cli.py`
4. `src/ctxd/_metadata.py::src/ctxd/_metadata.py`
5. `src/ctxd/models.py::src/ctxd/models.py`
6. `src/ctxd/config.py::src/ctxd/config.py`
7. `src/ctxd/models.py::DocumentResult`
8. `src/ctxd/models.py::ProfileResult`

**정답 청크 순위: miss**  
**pyproject 청크 진입: 아니오**

### 답변

## ctxd 라이브러리 개요

이 프로젝트는 **ctxd 서비스의 Python SDK 및 CLI 도구**입니다. ctxd 서비스에 연결된 앱(Slack, Google Drive, GitHub, Google Calendar 등)의 인덱싱된 콘텐츠를 검색하고 조회하는 기능을 제공합니다.

---

### 핵심 기능

**1. 콘텐츠 검색 및 조회**

`src/ctxd/client.py`의 `Client` 클래스와 `src/ctxd/models.py`의 모델들을 보면, 세 가지 주요 API 기능을 제공합니다:

- `search(query)` – DSL 쿼리(예: `text:deployment application:slack`)로 인덱싱된 문서를 검색 → `SearchResult` 반환
- `fetch_document(document_uid)` – 문서 고유 ID로 특정 문서를 가져옴 → `DocumentResult` 반환
- `get_profile()` – 연결된 앱 통합 목록과 인덱싱된 파일 트리 조회 → `ProfileResult` 반환

**2. 동기/비동기 클라이언트 모두 지원**

`src/ctxd/client.py`의 `Client`는 `AsyncClient`를 내부적으로 감싸서 동기 방식으로 사용할 수 있게 해줍니다. 이미 이벤트 루프가 실행 중인 경우 별도 스레드를 만들어 처리합니다.

**3. CLI 도구 제공**

`src/ctxd/cli.py`에 정의된 `main` 함수를 통해 터미널에서 `ctxd` 명령어로 직접 사용할 수 있습니다:

| 명령어 | 기능 |
|---|---|
| `ctxd login` | API 키 저장 |
| `ctxd logout` | 저장된 API 키 삭제 |
| `ctxd status` | 인증 상태 확인 |
| `ctxd install-app` | 앱 연동 페이지 열기 |
| `ctxd search <쿼리>` | 콘텐츠 검색 |
| `ctxd fetch <문서ID>` | 특정 문서 조회 |
| `ctxd profile` | 연동된 앱 및 파일 트리 확인 |

**4. 인증 및 설정 관리**

`src/ctxd/config.py`에서 API 키를 환경변수(`CTXD_API_KEY`), 로컬 저장소(`~/.ctxd/config.json`), 또는 직접 입력 순으로 우선순위를 두어 관리합니다. 기본 서버 주소는 `https://mcp.ctxd.dev`입니다(`DEFAULT_BASE_URL` 참고).

---

### 한 줄 요약

> Slack, Google Drive 등 외부 앱에 인덱싱된 콘텐츠를 **검색·조회**할 수 있는 Python SDK이자 CLI 도구입니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 miss. 정답 청크(Client) 대신 L1 client.py로 답함. SDK/CLI 성격과 세 기능 정확.

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
3. `src/ctxd/client.py::src/ctxd/client.py`
4. `src/ctxd/secure_store.py::load_secret_bundle`
5. `src/ctxd/async_client.py::AsyncClient.base_url`
6. `src/ctxd/cli.py::src/ctxd/cli.py`
7. `src/ctxd/client.py::Client.base_url`
8. `src/ctxd/client.py::Client.__enter__`

**정답 청크 순위: 1**  
**pyproject 청크 진입: 아니오**

### 답변

## `search()` 호출 시 서버 통신 방식

### 호출 흐름 요약

```
Client.search()  →  AsyncClient.search()  →  AsyncClient.call_tool()
```

### 단계별 설명

**1단계: `Client.search()` (src/ctxd/client.py, 35~36행)**

동기(Synchronous) 방식으로 호출할 수 있도록 비동기 메서드를 감싸는 역할을 합니다.

```python
def search(self, query: str) -> SearchResult:
    return self._run(self._async_client.search(query))
```

`_run()`은 내부적으로 `asyncio`와 `threading`을 사용해 비동기 코드를 동기 환경에서 실행합니다. 이미 실행 중인 이벤트 루프가 있으면 별도의 스레드를 만들어 처리합니다.

---

**2단계: `AsyncClient.search()` (src/ctxd/async_client.py, 40~42행)**

실제 서버 호출을 담당합니다.

```python
async def search(self, query: str) -> SearchResult:
    payload = await self.call_tool("search", {"query": query})
    return SearchResult.model_validate(payload)
```

- `call_tool("search", {"query": query})`를 호출합니다. 즉, **`"search"`라는 이름의 도구(tool)에 `{"query": 검색어}` 형태의 인자를 전달**하는 방식으로 서버와 통신합니다.
- 서버로부터 응답을 받으면 `SearchResult.model_validate()`로 결과를 검증하고 반환합니다.

---

**3단계: 실제 HTTP 통신 (`call_tool()`)**

서버와의 실제 네트워크 통신은 `AsyncClient.call_tool()`에서 이루어집니다. 그런데 `call_tool()`의 구체적인 구현 코드는 제공된 코드 조각에 포함되어 있지 않아, **정확히 어떤 프로토콜(HTTP, WebSocket 등)과 어떤 엔드포인트 경로를 사용하는지는 제공된 코드만으로는 알 수 없습니다.**

---

### 정리

| 단계 | 위치 | 역할 |
|------|------|------|
| `Client.search()` | `src/ctxd/client.py` | 동기 래퍼, `asyncio`/`threading`으로 실행 |
| `AsyncClient.search()` | `src/ctxd/async_client.py` | `call_tool("search", {...})` 호출 후 결과 검증 |
| `AsyncClient.call_tool()` | `src/ctxd/async_client.py` | 실제 서버 통신 (구현 코드 미제공) |

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 순위 1위인데 0점. 정답이 call_tool에 있는데 그 청크가 top_k에 없어 "프로토콜을 알 수 없다"로 끝남. Q11과 같은 청크에서 갈림.

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
5. `src/ctxd/async_client.py::AsyncClient._parse_json_payload`
6. `src/ctxd/cli.py::_emit_result`
7. `src/ctxd/async_client.py::AsyncClient.fetch_document`
8. `src/ctxd/client.py::Client`

**정답 청크 순위: 5**  
**pyproject 청크 진입: 아니오**

### 답변

## 서버 응답 오류 처리 흐름

오류 처리는 크게 **두 단계**로 나뉩니다.

---

### 1단계: HTTP 상태 코드 확인 (`_parse_response`)
📄 `src/ctxd/async_client.py` — `AsyncClient._parse_response` (109~131행)

HTTP 응답을 받으면 가장 먼저 상태 코드를 확인합니다.

```python
if response.status_code >= 400:
    message = f"ctxd MCP request failed with status {response.status_code}"
    try:
        error_payload = response.json()  # JSON으로 파싱 시도
    except ValueError:
        error_payload = response.text   # 실패하면 텍스트 그대로
    raise CtxdError(message, status_code=response.status_code, payload=error_payload)
```

- **400 이상**의 상태 코드면, 응답 본문을 JSON 또는 텍스트로 읽은 뒤 `CtxdError` 예외를 발생시키고 처리를 즉시 중단합니다.
- 상태 코드가 정상이면 Content-Type에 따라 SSE 또는 JSON 형식으로 파싱을 계속합니다. 둘 다 아니면 `CtxdProtocolError`(형식 불일치 예외)를 발생시킵니다.

---

### 2단계: JSON 응답 본문 안의 오류 확인 (`_parse_json_payload`)
📄 `src/ctxd/async_client.py` — `AsyncClient._parse_json_payload` (146~174행)

HTTP 상태 코드가 정상이더라도 **응답 본문 자체에 오류가 담겨 있을 수 있습니다.** 아래 순서로 검사합니다.

| 검사 항목 | 조건 | 발생 예외 |
|---|---|---|
| JSON-RPC 오류 필드 | 본문에 `"error"` 키가 있음 | `CtxdError` |
| result 누락 | `result`가 dict가 아님 | `CtxdProtocolError` |
| content 누락/비어있음 | `content`가 리스트가 아니거나 비어있음 | `CtxdProtocolError` |
| 타입 불일치 | 첫 번째 항목의 `type`이 `"text"`가 아님 | `CtxdProtocolError` |
| text 타입 불일치 | `text`가 문자열이 아님 | `CtxdProtocolError` |
| 서버가 오류 표시 | `result.isError`가 참 | `CtxdError` |
| JSON 파싱 실패 | text가 유효한 JSON이 아님 | `CtxdProtocolError` |

---

### 3단계: CLI 출력 시 오류 표시 (`_emit_result`, `_payload_has_error`)
📄 `src/ctxd/cli.py` — `_emit_result` (271~310행), `_payload_has_error` (313~316행)

예외 없이 정상적으로 파싱된 응답이라도, **페이로드 내부에 `error` 또는 `dsl_parse_error` 필드가 있으면** CLI에서 오류로 간주합니다.

```python
def _payload_has_error(payload: dict) -> bool:
    if payload.get("error"):
        return True
    return bool(payload.get("dsl_parse_error"))
```

- `--json` 옵션일 때: 전체를 JSON으로 출력하고, 오류 필드가 있으면 **종료 코드 1** 반환
- 텍스트 출력일 때: `Error: ...` 또는 `DSL parse error: ...` 메시지를 출력하고 **종료 코드 1** 반환

---

### 예외 클래스 계층
📄 `src/ctxd/exceptions.py`

- `CtxdError` — 기본 오류 (상태 코드 400+, JSON-RPC 오류 등)
  - `CtxdProtocolError` — 응답 형식이 예상과 다를 때
  - `CtxdAuthError` — 인증(로그인/토큰) 실패 시

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 5위. isError/파싱실패/네트워크 세 경로 모두 정확. 예외 계층까지 정리.

---

## Q04 (식별자)

**질문**: API 키를 환경변수로 넘기려면 변수 이름을 뭐라고 해야 해?

**정답 요지**: CTXD_API_KEY. (설정 파일 경로는 CTXD_CONFIG_PATH, 서버 주소는 CTXD_BASE_URL)

**근거 출처**: README + tests/test_sdk.py::test_client_search_uses_api_key_env  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/config.py::resolve_api_key`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/config.py::resolve_api_key`
2. `src/ctxd/cli.py::_handle_login`
3. `src/ctxd/cli.py::_handle_logout`
4. `src/ctxd/cli.py::_resolve_login_api_key`
5. `src/ctxd/async_client.py::AsyncClient.call_tool`
6. `src/ctxd/cli.py::_prompt_api_key`
7. `src/ctxd/cli.py::_handle_status`
8. `src/ctxd/config.py::save_api_key`

**정답 청크 순위: 1**  
**pyproject 청크 진입: 아니오**

### 답변

## 환경변수 이름: `CTXD_API_KEY`

`src/ctxd/config.py`의 `resolve_api_key` 함수 28행을 보면:

```python
env_api_key = os.getenv("CTXD_API_KEY")
```

환경변수 이름은 **`CTXD_API_KEY`** 입니다.

---

### 사용 예시

**Linux / macOS:**
```bash
export CTXD_API_KEY=your_api_key_here
```

**Windows (PowerShell):**
```powershell
$env:CTXD_API_KEY = "your_api_key_here"
```

---

### 참고: API 키를 찾는 우선순위

`resolve_api_key` 함수(`src/ctxd/config.py`, 24~41행)는 아래 순서로 API 키를 탐색합니다:

1. **직접 전달된 값** (`api_key` 인자)
2. **환경변수** `CTXD_API_KEY`
3. **저장된 시크릿** (이전에 `ctxd login`으로 저장한 값)

즉, 환경변수를 설정해두면 코드에 직접 키를 넘기지 않아도 자동으로 인식됩니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 1위. CTXD_API_KEY 정확, 탐색 우선순위까지 덧붙임.

---

## Q05 (식별자)

**질문**: HTTP 요청을 보낼 때 어떤 라이브러리를 써?

**정답 요지**: httpx. 비동기 클라이언트(httpx.AsyncClient)를 사용.

**근거 출처**: tests/test_sdk.py (httpx.AsyncClient.post를 patch해 테스트)  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/async_client.py::AsyncClient`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/secure_store.py::load_secret_bundle`
2. `src/ctxd/client.py::src/ctxd/client.py`
3. `src/ctxd/cli.py::src/ctxd/cli.py`
4. `src/ctxd/cli.py::_handle_install_app`
5. `src/ctxd/async_client.py::src/ctxd/async_client.py`
6. `src/ctxd/async_client.py::AsyncClient.call_tool`
7. `src/ctxd/secure_store.py::src/ctxd/secure_store.py`
8. `src/ctxd/secure_store.py::save_secret_bundle`

**정답 청크 순위: miss**  
**pyproject 청크 진입: 아니오**

### 답변

## HTTP 요청 라이브러리: `httpx`

`src/ctxd/async_client.py` 파일에서 HTTP 요청을 보낼 때 **`httpx`** 라이브러리를 사용합니다.

### 근거

파일 상단에 명시적으로 import되어 있습니다:

```python
import httpx
```

실제 요청은 `AsyncClient.call_tool` 메서드(52–89행)에서 `httpx.AsyncClient`를 통해 POST 요청으로 이루어집니다:

```python
async with httpx.AsyncClient(timeout=self._timeout) as client:
    response = await client.post(
        self._base_url,
        headers=headers,
        json=request_body,
    )
```

### 구조 요약

- **`httpx.AsyncClient`**: 비동기 HTTP 클라이언트로, `src/ctxd/async_client.py`의 `AsyncClient` 클래스 내부에서 사용됩니다.
- **`src/ctxd/client.py`의 `Client`** 클래스는 동기 방식으로 보이지만, 내부적으로 `AsyncClient`를 감싸고 `asyncio`로 실행하는 구조입니다. 즉, 동기 클라이언트도 결국 `httpx`를 통해 HTTP 요청을 보냅니다.
- 오류 처리도 `httpx.RequestError`를 잡아 처리하고 있어, `httpx`가 핵심 HTTP 통신 라이브러리임을 확인할 수 있습니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 miss인데 만점. L1과 call_tool 청크로 httpx.AsyncClient까지 정확. pyproject 청크 간섭 없음(사전 예측 빗나감).

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
3. `src/ctxd/models.py::DocumentResult`
4. `src/ctxd/exceptions.py::CtxdAuthError`
5. `src/ctxd/exceptions.py::CtxdError.__init__`
6. `src/ctxd/models.py::SearchResult`
7. `src/ctxd/async_client.py::AsyncClient`
8. `src/ctxd/models.py::SearchItem`

**정답 청크 순위: 2**  
**pyproject 청크 진입: 아니오**

### 답변

## SDK가 직접 정의한 예외 클래스

`src/ctxd/exceptions.py`에 총 3개의 예외 클래스가 정의되어 있습니다.

---

### 1. `CtxdError` — 기본 예외 클래스

모든 커스텀 예외의 부모 클래스입니다. Python 내장 `Exception`을 상속합니다.

**생성자 매개변수:**
- `message` (str): 예외 메시지
- `status_code` (int | None): HTTP 상태 코드 (선택)
- `payload` (Any | None): 응답 본문 등 추가 데이터 (선택)

**발생하는 경우 (`src/ctxd/async_client.py` 기준):**

| 상황 | 위치 |
|------|------|
| 서버에 HTTP 요청 자체가 실패할 때 (네트워크 오류 등, `httpx.RequestError` 발생 시) | `call_tool()` |
| 서버가 HTTP 400 이상의 오류 상태 코드를 반환할 때 | `_parse_response()` |
| JSON-RPC 응답 본문에 `"error"` 키가 포함되어 있을 때 | `_parse_json_payload()` |
| MCP 응답의 `isError` 플래그가 `True`일 때 | `_parse_json_payload()` |

---

### 2. `CtxdProtocolError` — 프로토콜 형식 오류

`CtxdError`를 상속합니다. 서버 응답의 **구조가 기대한 형식과 다를 때** 발생합니다.

**발생하는 경우:**

| 상황 | 위치 |
|------|------|
| 응답의 `Content-Type`이 JSON도 SSE도 아닐 때 | `_parse_response()` |
| SSE 응답에 `data:` 로 시작하는 줄이 없을 때 | `_parse_sse_payload()` |
| 응답 본문에 `result` 객체가 없을 때 | `_parse_json_payload()` |
| `result.content`가 비어있거나 리스트가 아닐 때 | `_parse_json_payload()` |
| `content`의 첫 번째 항목이 `type: "text"`가 아닐 때 | `_parse_json_payload()` |
| `text` 필드가 문자열이 아닐 때 | `_parse_json_payload()` |
| `text` 필드의 내용이 유효한 JSON이 아닐 때 | `_parse_json_payload()` |

---

### 3. `CtxdAuthError` — 인증 오류

`CtxdError`를 상속합니다. **API 키 등 인증 정보가 없거나 유효하지 않을 때** 발생합니다.

**발생하는 경우:**

| 상황 | 위치 |
|------|------|
| API 키가 설정되지 않아 액세스 토큰을 가져올 수 없을 때 | `_resolve_access_token()` |

클래스 주석(`Raised when login, refresh, or credential resolution fails.`)에 따르면 로그인, 토큰 갱신, 자격증명 해석 실패도 이 예외를 사용하도록 설계되어 있습니다.

---

### 상속 구조 요약

```
Exception
└── CtxdError           # 기본 예외 (네트워크/HTTP/RPC 오류)
    ├── CtxdProtocolError  # 응답 형식이 맞지 않을 때
    └── CtxdAuthError      # 인증 정보가 없거나 실패할 때
```

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 2위. 예외 3종과 상속 구조 정확.

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
3. `src/ctxd/async_client.py::src/ctxd/async_client.py`
4. `src/ctxd/client.py::src/ctxd/client.py`
5. `src/ctxd/client.py::Client`
6. `src/ctxd/async_client.py::AsyncClient.call_tool`
7. `src/ctxd/async_client.py::AsyncClient`
8. `src/ctxd/async_client.py::AsyncClient.search`

**정답 청크 순위: miss**  
**pyproject 청크 진입: 아니오**

### 답변

## 왜 이런 구조를 선택했는가

### 핵심 이유: 실제 로직은 한 번만 작성하기

`src/ctxd/async_client.py`의 `AsyncClient`에 실제 네트워크 통신 로직(`call_tool`, `_parse_response`, `_parse_sse_payload` 등)이 전부 들어 있습니다.

`src/ctxd/client.py`의 `Client`는 이 `AsyncClient`를 그대로 품고(`self._async_client = AsyncClient(...)`), 각 메서드에서 단순히 `_run()`으로 감싸 호출합니다:

```python
def search(self, query: str) -> SearchResult:
    return self._run(self._async_client.search(query))
```

즉, 통신·파싱 로직을 `AsyncClient`에만 작성하고 `Client`는 "동기 껍데기" 역할만 합니다. 로직 중복이 없습니다.

---

### `_run()`이 해결하는 기술적 문제

Python에서 `async` 함수를 동기 코드에서 호출하려면 이벤트 루프(비동기 작업을 실행하는 실행 엔진)가 필요합니다. `Client._run()`은 두 가지 상황을 모두 처리합니다:

```python
@staticmethod
def _run(coro):
    try:
        asyncio.get_running_loop()       # 이미 이벤트 루프가 돌고 있는지 확인
    except RuntimeError:
        return asyncio.run(coro)         # 루프 없으면 새로 만들어서 실행

    # 이미 루프가 있으면 (예: Jupyter notebook) → 별도 스레드에서 실행
    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
```

- **이벤트 루프가 없을 때**: `asyncio.run(coro)`로 새 루프를 만들어 실행
- **이미 이벤트 루프가 돌고 있을 때** (예: Jupyter Notebook, FastAPI 서버 내부): `asyncio.run()`을 중첩 호출할 수 없으므로 별도 스레드에서 새 루프를 띄워 실행

이 처리가 없으면 Jupyter 같은 환경에서 동기 클라이언트를 쓸 때 오류가 납니다.

---

### 정리하면

| 역할 | 클래스 | 파일 |
|------|--------|------|
| 실제 통신·파싱 로직 | `AsyncClient` | `src/ctxd/async_client.py` |
| 동기 환경용 래퍼 | `Client` | `src/ctxd/client.py` |

- **사용자 입장**: `async/await` 문법이 낯선 경우 `Client`를, 비동기 코드를 이미 쓰는 경우 `AsyncClient`를 직접 사용할 수 있어 선택지가 생깁니다.
- **개발자 입장**: 로직을 `AsyncClient`에 한 번만 작성하면 두 인터페이스 모두에서 동작하므로 유지보수 부담이 줄어듭니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): A
- 메모: 1점 만점. 통신 로직이 한 벌이라는 점과 _run을 짚어 기준 충족. 다만 "핵심 이유"로 의도를 단정하는 어조.

---

## Q08 (왜)

**질문**: 왜 설정(config.json)과 자격증명(credentials.json)을 다른 파일로 나눴어?

**정답 요지**: 의도는 코드에 없음. clear_api_key가 credentials만 지우고 config의 base_url은 남긴다는 동작까지 짚으면 1점. 기권해도 1점.

**근거 출처**: tests/test_sdk.py::test_clear_api_key_keeps_base_url_and_removes_plaintext_credentials  
**인덱스내 근거**: N  
**정답 청크**: `src/ctxd/config.py::clear_api_key`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/config.py::src/ctxd/config.py`
2. `src/ctxd/secure_store.py::src/ctxd/secure_store.py`
3. `src/ctxd/config.py::save_config`
4. `src/ctxd/async_client.py::src/ctxd/async_client.py`
5. `src/ctxd/cli.py::src/ctxd/cli.py`
6. `src/ctxd/secure_store.py::save_secret_bundle`
7. `src/ctxd/config.py::get_config_path`
8. `src/ctxd/config.py::load_config`

**정답 청크 순위: miss**  
**pyproject 청크 진입: 아니오**

### 답변

## 설정과 자격증명을 분리한 이유

코드에서 읽어낼 수 있는 근거들을 정리하면 다음과 같습니다.

---

### 1. 저장하는 데이터의 성격이 다릅니다

| 파일 | 경로 | 저장 내용 |
|------|------|-----------|
| `config.json` | `~/.ctxd/config.json` | `base_url` 같은 일반 설정값 |
| `credentials.json` | `~/.ctxd/credentials.json` | `api_key` 같은 민감한 인증 정보 |

`src/ctxd/config.py`의 `save_api_key` 함수를 보면, `base_url`은 `save_config()`로 `config.json`에 저장하고, `api_key`는 `save_secret_bundle()`로 `credentials.json`에 따로 저장합니다. 두 종류의 데이터를 명확히 구분해서 쓰고 있습니다.

---

### 2. 파일 경로를 독립적으로 제어할 수 있습니다

`src/ctxd/secure_store.py`의 `get_credentials_path` 함수를 보면:

```python
def get_credentials_path() -> Path:
    configured = os.getenv("CTXD_CREDENTIALS_PATH")  # 자격증명 경로만 따로 지정 가능
    if configured:
        return Path(configured).expanduser()

    config_path = os.getenv("CTXD_CONFIG_PATH")
    if config_path:
        return Path(config_path).expanduser().parent / "credentials.json"

    return DEFAULT_CREDENTIALS_PATH
```

`CTXD_CREDENTIALS_PATH` 환경변수로 자격증명 파일 위치를 **설정 파일과 완전히 독립적으로** 지정할 수 있습니다. 예를 들어 자격증명만 더 보안이 강한 위치(예: 암호화된 볼륨, 시스템 키링 경로 등)에 따로 보관하는 것이 가능합니다.

---

### 3. 자격증명 삭제와 일반 설정 삭제의 동작이 다릅니다

`src/ctxd/config.py`의 `clear_api_key` 함수를 보면:

```python
def clear_api_key(*, base_url: str | None = None, keep_base_url: bool = True) -> Path:
    clear_secret_bundle(...)          # credentials.json 파일 자체를 삭제
    if keep_base_url:
        retained["base_url"] = resolved_base_url
    return save_config(retained)      # config.json은 base_url을 남겨두고 유지
```

로그아웃할 때 `credentials.json`은 파일째 지워버리지만(`src/ctxd/secure_store.py`의 `clear_secret_bundle`이 `path.unlink()` 호출), `config.json`은 `base_url` 같은 설정값을 선택적으로 보존합니다. 파일이 분리되어 있기 때문에 이런 **세밀한 제어**가 가능합니다.

---

### 요약

코드 구조로 보아, **"언제든 지워져도 되는 설정값"과 "민감하게 다뤄야 하는 인증 정보"를 파일 단위로 분리**한 것으로 판단됩니다. 덕분에 독립적인 경로 지정, 파일 단위의 삭제 제어, 데이터 성격에 따른 명확한 책임 분리가 모두 가능해집니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: 1점 만점. clear_api_key가 base_url을 남긴다는 동작을 짚음. 결론을 "판단됩니다"로 유보.

---

## Q09 (왜)

**질문**: 왜 검색 결과에서 id와 document_uid를 둘 다 받아들이게 했어?

**정답 요지**: 의도는 코드에 없음. models.py가 두 이름을 같은 필드로 받는다는 사실(text/snippet도 마찬가지)까지 짚으면 1점. 서버 응답 형식이 여러 벌이라는 추정은 근거를 밝히면 인정.

**근거 출처**: tests/test_sdk.py::test_sdk_search_accepts_document_uid_and_snippet_fields  
**인덱스내 근거**: N  
**정답 청크**: `src/ctxd/models.py::SearchItem`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/models.py::SearchItem`
2. `src/ctxd/cli.py::_handle_status`
3. `src/ctxd/cli.py::_handle_install_app`
4. `src/ctxd/cli.py::_handle_logout`
5. `src/ctxd/client.py::Client.fetch_document`
6. `src/ctxd/cli.py::_build_parser`
7. `src/ctxd/models.py::DocumentResult`
8. `src/ctxd/client.py::Client.search`

**정답 청크 순위: 1**  
**pyproject 청크 진입: 아니오**

### 답변

## `id`와 `document_uid`를 둘 다 받아들이는 이유

`src/ctxd/models.py`의 `SearchItem` 클래스를 보면:

```python
id: str = Field(validation_alias=AliasChoices("id", "document_uid"))
```

`validation_alias=AliasChoices("id", "document_uid")`는 Pydantic의 기능으로, **데이터를 받아들일 때** `"id"`라는 키로 들어오든 `"document_uid"`라는 키로 들어오든 모두 `id` 필드에 저장하겠다는 의미입니다.

이렇게 한 이유는 코드에서 두 가지 단서로 읽어낼 수 있습니다:

1. **API 응답 필드명 불일치 대응**: 검색 결과를 내려주는 서버(API)가 같은 값을 어떤 경우엔 `"id"`, 어떤 경우엔 `"document_uid"`로 내려줄 수 있습니다. 두 이름을 모두 허용함으로써 어느 쪽이 오더라도 파싱이 깨지지 않게 방어한 것입니다.

2. **CLI와 모델 간 용어 통일**: `src/ctxd/cli.py`의 `_build_parser` 함수를 보면 `fetch` 서브커맨드의 인자 이름이 `document_uid`이고, 설명도 *"Document UID returned by search"*라고 되어 있습니다. 즉 CLI에서는 `document_uid`라는 용어를 사용하고, 내부 모델에서는 `id`로 통일해서 관리하는 구조입니다. `AliasChoices`가 그 둘 사이의 다리 역할을 합니다.

요약하면, **외부(API 응답 또는 CLI)에서 사용하는 이름이 통일되어 있지 않기 때문에**, 두 이름을 모두 수용하도록 별칭(alias)을 설정한 것입니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: 1점 만점. 순위 1위. AliasChoices 사실을 짚고 추정 근거를 밝힘. text/snippet은 언급 없음.
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
3. `src/ctxd/config.py::save_api_key`
4. `src/ctxd/cli.py::_resolve_login_api_key`
5. `src/ctxd/cli.py::_build_parser`
6. `src/ctxd/cli.py::src/ctxd/cli.py`
7. `src/ctxd/cli.py::_handle_login`
8. `src/ctxd/client.py::src/ctxd/client.py`

**정답 청크 순위: 3**  
**pyproject 청크 진입: 아니오**

### 답변

## `ctxd login` API 키 저장 흐름

`ctxd login` 명령을 입력하면 아래 순서로 함수들이 호출됩니다.

---

### 1. `main` → `_handle_login` (`src/ctxd/cli.py`)

`main` 함수는 `args.command == "login"` 조건을 보고 `_handle_login`을 호출합니다.

---

### 2. `_handle_login` → `_resolve_login_api_key` (`src/ctxd/cli.py`, 183–198행)

`_handle_login` 내부에서 `_resolve_login_api_key()`를 호출해 API 키와 `should_save` 플래그를 받습니다.

---

### 3. `_resolve_login_api_key` → `_prompt_api_key` (`src/ctxd/cli.py`, 227–243행)

`_resolve_login_api_key`는 다음 순서로 API 키를 찾습니다:

| 순서 | 출처 | `should_save` 반환값 |
|------|------|---------------------|
| 1 | 환경변수 `CTXD_API_KEY` | `False` (저장 안 함) |
| 2 | 이미 저장된 키 (`resolve_api_key()`) | `False` (저장 안 함) |
| 3 | 사용자 직접 입력 (`_prompt_api_key()`) | **`True` (저장 필요)** |

사용자가 터미널에서 직접 입력한 경우에만 `should_save=True`가 반환됩니다. `_prompt_api_key`는 `getpass.getpass("ctxd API key: ")`로 입력을 받습니다.

---

### 4. `_handle_login` → `save_api_key` (`src/ctxd/config.py`, 74–83행)

`_handle_login`에서 `should_save`가 `True`일 때만 `save_api_key(api_key)`를 호출합니다 (환경변수나 기존 저장 키를 사용한 경우에는 저장하지 않습니다).

---

### 5. `save_api_key` → `save_secret_bundle` + `save_config` (`src/ctxd/config.py`)

`save_api_key` 내부에서:
- `save_secret_bundle({"api_key": api_key.strip()}, ...)` — API 키 자체를 **비밀 번들(secret bundle)**로 저장
- `save_config(config)` — `base_url` 등 설정을 **설정 파일**에 저장

합니다.

---

### 흐름 요약

```
ctxd login
  └─ main()
       └─ _handle_login()
            ├─ _resolve_login_api_key()
            │    └─ _prompt_api_key()  ← 사용자가 키 입력
            ├─ Client(api_key=...).get_profile()  ← 키 유효성 검증
            └─ save_api_key(api_key)  ← should_save=True일 때만
                 ├─ save_secret_bundle({"api_key": ...})  ← 키 저장
                 └─ save_config(config)  ← 설정 파일 저장
```

최종적으로 API 키는 `save_secret_bundle`이 처리하는 **비밀 번들** 형태로, 설정은 `save_config`가 처리하는 **설정 파일**로 저장됩니다. 단, `save_secret_bundle`과 `save_config`의 실제 저장 경로(파일 시스템 위치)는 제공된 코드에 해당 함수의 구현이 없으므로 알 수 없습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): A
- 메모: 순위 3위. 함수 사슬은 맞으나 최종 파일명(credentials.json)을 못 댐. save_secret_bundle 구현이 top_k에 없었음.

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
3. `src/ctxd/secure_store.py::load_secret_bundle`
4. `src/ctxd/async_client.py::AsyncClient.base_url`
5. `src/ctxd/client.py::Client.base_url`
6. `src/ctxd/client.py::src/ctxd/client.py`
7. `src/ctxd/async_client.py::AsyncClient.__aexit__`
8. `src/ctxd/async_client.py::AsyncClient.call_tool`

**정답 청크 순위: miss**  
**pyproject 청크 진입: 아니오**

### 답변

## `Client.search()` 호출 경로

아래 순서로 코드가 실행됩니다.

---

### 1. `Client.search()` — `src/ctxd/client.py` 35~36행

```python
def search(self, query: str) -> SearchResult:
    return self._run(self._async_client.search(query))
```

`Client`는 동기(synchronous) 클라이언트입니다. 내부에 `AsyncClient` 인스턴스(`self._async_client`)를 가지고 있으며, 비동기 메서드를 동기 방식으로 감싸서 실행합니다.

---

### 2. `Client._run()` — `src/ctxd/client.py` 47~68행

`_run()`은 비동기 코루틴을 동기 환경에서 실행시키는 역할을 합니다.

- **현재 실행 중인 이벤트 루프가 없으면** → `asyncio.run(coro)`로 바로 실행합니다.
- **이미 이벤트 루프가 실행 중이면** → 새 스레드(`threading.Thread`)를 만들어 그 안에서 `asyncio.run(coro)`를 실행한 뒤 결과를 가져옵니다.  
  (이벤트 루프는 중첩 실행이 불가능하기 때문에, 새 스레드에서 독립적인 루프를 실행하는 방식입니다.)

---

### 3. `AsyncClient.search()` — `src/ctxd/async_client.py` 40~42행

```python
async def search(self, query: str) -> SearchResult:
    payload = await self.call_tool("search", {"query": query})
    return SearchResult.model_validate(payload)
```

`call_tool()`을 `"search"` 도구 이름과 쿼리 인자로 호출합니다.

---

### 4. `AsyncClient.call_tool()` — `src/ctxd/async_client.py` 52~89행

실제 HTTP 요청이 만들어지는 곳입니다.

1. **요청 본문 구성**: JSON-RPC 2.0 형식으로 `tools/call` 메서드를 호출하는 본문을 만듭니다.
   ```python
   {
       "jsonrpc": "2.0",
       "method": "tools/call",
       "params": {"name": "search", "arguments": {"query": "..."}},
       "id": 1,
   }
   ```

2. **액세스 토큰 획득**: `self._resolve_access_token()`으로 인증 토큰을 가져옵니다.

3. **HTTP 헤더 구성**: `Authorization: Bearer {token}` 등의 헤더를 설정합니다.

4. **HTTP POST 요청 전송** (`httpx` 라이브러리 사용):
   - `self._client`(미리 생성된 클라이언트)가 있으면 그것을 사용합니다.
   - 없으면 `httpx.AsyncClient`를 임시로 생성해 요청을 보냅니다.
   - 목적지는 `self._base_url`입니다.

5. **응답 파싱**: `self._parse_response(response)`로 결과를 처리해 반환합니다.

---

### 흐름 요약

```
Client.search(query)
  └→ Client._run(AsyncClient.search(query))        # 동기 → 비동기 브릿지
       └→ AsyncClient.search(query)
            └→ AsyncClient.call_tool("search", {"query": query})
                 ├→ _resolve_access_token()         # 인증 토큰 획득
                 └→ httpx.AsyncClient.post(base_url, ...)  # 실제 HTTP 요청 발송
```

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 miss인데 만점. call_tool이 8위로 걸려 JSON-RPC와 httpx POST까지 서술. Q02와 대비되는 지점.

---

## Q12 (관계)

**질문**: API 키는 어떤 순서로 찾아져?

**정답 요지**: ① 인자로 직접 넘긴 api_key → ② 환경변수 CTXD_API_KEY → ③ 저장된 credentials.json. 셋 다 없으면 CtxdAuthError. 순서까지 맞아야 2점.

**근거 출처**: tests/test_sdk.py::test_client_search_uses_api_key_env, ::test_saved_api_key_is_resolved_from_plaintext_credentials, ::test_async_client_requires_api_key  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/config.py::resolve_api_key`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/config.py::resolve_api_key`
2. `src/ctxd/cli.py::_handle_logout`
3. `src/ctxd/config.py::save_api_key`
4. `src/ctxd/cli.py::_resolve_login_api_key`
5. `src/ctxd/cli.py::_prompt_api_key`
6. `src/ctxd/cli.py::_handle_login`
7. `src/ctxd/cli.py::_handle_status`
8. `src/ctxd/client.py::Client.__init__`

**정답 청크 순위: 1**  
**pyproject 청크 진입: 아니오**

### 답변

## API 키 탐색 순서

코드에는 두 가지 상황에서 API 키를 찾는 흐름이 있습니다.

---

### 일반적인 API 키 탐색 (`src/ctxd/config.py` > `resolve_api_key`)

1. **직접 전달된 값** — 함수 호출 시 `api_key` 인자로 넘겨진 값이 있으면 그것을 사용합니다.
2. **환경 변수 `CTXD_API_KEY`** — 인자가 없으면 운영체제의 환경 변수를 확인합니다.
3. **저장된 시크릿** — 환경 변수도 없으면 `load_secret_bundle()`을 통해 저장된 파일에서 `api_key`를 읽어옵니다.
4. **없음** — 위 세 곳 모두에서 찾지 못하면 `None`을 반환합니다.

---

### 로그인 시 API 키 탐색 (`src/ctxd/cli.py` > `_resolve_login_api_key`)

로그인 명령(`ctxd login`)에서는 순서가 약간 다릅니다.

1. **환경 변수 `CTXD_API_KEY`** — 가장 먼저 환경 변수를 확인합니다.
2. **저장된 시크릿** — 환경 변수가 없으면 `resolve_api_key()`를 호출해 저장된 값을 찾습니다.
3. **사용자 직접 입력** — 그것도 없으면 `_prompt_api_key()`를 통해 터미널에서 직접 입력을 받습니다.  
   단, 터미널(tty)이 아닌 환경(예: 파이프, 스크립트)에서는 입력을 받지 않고 `None`을 반환합니다.
4. **없음** — 세 곳 모두 실패하면 `None`과 `False`를 반환하고, 이후 `_handle_login`에서 오류가 발생합니다.

---

### 차이점 요약

| 단계 | `resolve_api_key` (일반) | `_resolve_login_api_key` (로그인) |
|------|--------------------------|----------------------------------|
| 1순위 | 함수 인자로 직접 전달 | 환경 변수 |
| 2순위 | 환경 변수 | 저장된 시크릿 |
| 3순위 | 저장된 시크릿 | 터미널 직접 입력 |

로그인 흐름에 "직접 전달" 단계가 없는 것은, `_resolve_login_api_key`가 CLI 명령어 처리에 특화되어 있어서 외부에서 값을 주입받는 상황을 고려하지 않기 때문으로 보입니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 1위. 인자→환경변수→저장값 순서 정확. resolve_api_key가 None을 반환한다는 점도 정확.

---

## Q13 (사실)

**질문**: CLI에 어떤 명령어들이 있어?

**정답 요지**: login, logout, status, search, fetch, profile, install-app, --version. 7개 중 5개 이상이면 2점.

**근거 출처**: README + tests/test_cli.py::test_cli_help_describes_commands  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/cli.py::_build_parser`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/cli.py::_build_parser`
2. `src/ctxd/cli.py::src/ctxd/cli.py`
3. `src/ctxd/config.py::src/ctxd/config.py`
4. `src/ctxd/cli.py::_resolve_login_api_key`
5. `src/ctxd/client.py::src/ctxd/client.py`
6. `src/ctxd/cli.py::_prompt_api_key`
7. `src/ctxd/cli.py::_handle_logout`
8. `pyproject.toml::pyproject.toml`

**정답 청크 순위: 1**  
**pyproject 청크 진입: 예**

### 답변

## ctxd CLI 명령어 목록

`src/ctxd/cli.py`의 `_build_parser` 함수에 정의된 명령어들입니다.

---

### 전역 옵션

| 옵션 | 설명 |
|------|------|
| `--version` | 설치된 ctxd 버전을 출력하고 종료 |

---

### 서브 명령어

#### 1. `ctxd login`
API 키를 입력받아 저장합니다.
- 환경변수 `CTXD_API_KEY` → 저장된 키 → 터미널 직접 입력 순서로 키를 찾습니다.

#### 2. `ctxd logout`
이 기기에 저장된 API 키를 삭제합니다.

#### 3. `ctxd status`
API 키가 설정되어 있는지(인증 여부)를 확인합니다.

#### 4. `ctxd install-app`
Slack, Google Drive, GitHub 등 앱 연동 설치 페이지를 엽니다.

| 옵션 | 설명 |
|------|------|
| `--no-browser` | 브라우저를 열지 않고 URL만 출력 |

#### 5. `ctxd search QUERY`
인덱싱된 앱 콘텐츠를 검색하고 JSON으로 결과를 출력합니다.

- `QUERY`: 검색어 또는 DSL 토큰 (예: `text:deployment application:slack`)
- 여러 토큰을 띄어쓰기로 구분하거나 따옴표로 묶어서 전달 가능
- 결과는 항상 JSON 형식으로 출력

#### 6. `ctxd fetch DOCUMENT_UID`
문서 UID로 단일 문서를 가져옵니다.

| 인자/옵션 | 설명 |
|----------|------|
| `document_uid` | 검색 결과에서 얻은 문서 UID (필수) |
| `--json` | 전체 응답을 JSON 형식으로 출력 |

#### 7. `ctxd profile`
현재 인증된 사용자의 연동된 서비스 목록과 인덱싱된 파일 트리를 보여줍니다.

| 옵션 | 설명 |
|------|------|
| `--json` | 응답을 JSON 형식으로 출력 |

---

### 사용 예시
```
ctxd login
ctxd install-app
ctxd search text:deployment application:slack
ctxd fetch doc-123 --json
```
(이 예시는 `_build_parser` 함수의 `epilog`에 명시된 내용입니다.)

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 1위. 명령 7개와 --version 모두. pyproject 청크가 8위로 진입한 유일한 문항이나 답변에 영향 없음.

---

## Q14 (사실)

**질문**: base_url을 https://ctxd.example.com 으로 주면 실제 요청 URL은 뭐가 돼?

**정답 요지**: https://ctxd.example.com/mcp. 끝에 /mcp가 자동으로 붙고, 이미 /mcp로 끝나면 중복해서 붙이지 않음.

**근거 출처**: tests/test_sdk.py::test_client_context_manager_returns_client, ::test_saved_api_key_resolves_for_normalized_mcp_base_url  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/async_client.py::AsyncClient._normalize_base_url`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/async_client.py::AsyncClient.base_url`
2. `src/ctxd/config.py::resolve_base_url`
3. `src/ctxd/client.py::Client.base_url`
4. `src/ctxd/config.py::_resolve_base_url_from_config`
5. `src/ctxd/secure_store.py::load_secret_bundle`
6. `src/ctxd/secure_store.py::clear_secret_bundle`
7. `src/ctxd/secure_store.py::save_secret_bundle`
8. `src/ctxd/config.py::clear_api_key`

**정답 청크 순위: miss**  
**pyproject 청크 진입: 아니오**

### 답변

## 실제 요청 URL 분석

제공된 코드만으로는 `base_url`이 실제 HTTP 요청 URL로 어떻게 조합되는지 알 수 없습니다. 이유를 아래에 설명합니다.

---

### 확인된 내용

`src/ctxd/config.py`의 `resolve_base_url` 함수(97–109행)에 따르면, `https://ctxd.example.com`을 직접 인자로 넘기면 해당 값이 `.strip()` 처리된 후 그대로 반환됩니다. 즉:

```
resolve_base_url("https://ctxd.example.com")
→ "https://ctxd.example.com"
```

이 값은 `src/ctxd/async_client.py`의 `AsyncClient._base_url`에 저장되고(`base_url` 메서드, 28–29행), `src/ctxd/client.py`의 `Client.base_url`(26–27행)을 통해 외부에 노출됩니다.

---

### 알 수 없는 내용

코드에서 확인한 것은 **`_base_url`에 값이 저장된다**는 사실뿐입니다. 실제 HTTP 요청을 보낼 때 이 `_base_url`에 **어떤 경로(path)나 쿼리 파라미터가 붙는지**는 제공된 코드 조각에 나타나 있지 않습니다.

예를 들어, 요청 URL이 다음 중 어느 형태인지는 판단할 수 없습니다:

- `https://ctxd.example.com/v1/search`
- `https://ctxd.example.com/api/...`
- 그 외 다른 형태

실제 요청 URL을 확인하려면 `AsyncClient` 내부에서 HTTP 요청을 실제로 보내는 메서드(예: `httpx`, `aiohttp` 등의 호출부)가 포함된 코드가 추가로 필요합니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 순위 miss. _normalize_base_url이 top_k에 없어 /mcp를 못 댐. 실험 A 세 조건에 이어 네 번째 실패.

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
3. `src/ctxd/cli.py::_handle_logout`
4. `src/ctxd/config.py::resolve_api_key`
5. `src/ctxd/secure_store.py::save_secret_bundle`
6. `src/ctxd/secure_store.py::load_secret_bundle`
7. `src/ctxd/client.py::Client.__init__`
8. `src/ctxd/cli.py::_handle_login`

**정답 청크 순위: 5**  
**pyproject 청크 진입: 아니오**

### 답변

## 결론: 아니요, `base_url`마다 따로 관리되지 않습니다.

API 키는 **단 하나의 파일**에 저장되며, `base_url`에 관계없이 항상 같은 파일을 덮어씁니다.

---

### 근거 설명

#### 1. `save_secret_bundle`이 `base_url`을 실제로 사용하지 않습니다

`src/ctxd/secure_store.py`의 `save_secret_bundle` 함수를 보면:

```python
def save_secret_bundle(
    bundle: dict[str, Any], *, base_url: str, client_id: str | None
) -> None:
    del base_url, client_id          # ← 파라미터를 즉시 삭제(무시)
    path = get_credentials_path()    # ← 항상 고정된 하나의 경로 사용
```

`base_url`과 `client_id`를 인자로 받긴 하지만, 첫 줄에서 `del`로 즉시 버립니다. 그리고 `get_credentials_path()`로 **항상 동일한 고정 경로**를 가져와 그 파일에 씁니다.

#### 2. `load_secret_bundle`도 마찬가지입니다

`src/ctxd/secure_store.py`의 `load_secret_bundle` 함수도 동일한 구조입니다:

```python
def load_secret_bundle(*, base_url: str, client_id: str | None) -> dict[str, Any]:
    del base_url, client_id          # ← 역시 즉시 삭제
    path = get_credentials_path()    # ← 항상 같은 파일을 읽음
```

#### 3. 저장 시 `base_url`은 설정 파일에만 기록됩니다

`src/ctxd/config.py`의 `save_api_key`를 보면:

```python
config["base_url"] = resolved_base_url   # ← 설정(config)에 base_url 기록
save_secret_bundle({"api_key": api_key.strip()}, base_url=resolved_base_url, ...)
```

`base_url`은 설정 파일(`config`)에는 저장되지만, 실제 API 키 파일(`secret_bundle`)은 `base_url`을 구분 키로 쓰지 않고 단일 파일에 덮어씁니다.

---

### 요약

| 항목 | 실제 동작 |
|------|-----------|
| `base_url`별 별도 파일 | ❌ 없음 |
| API 키 저장 위치 | `get_credentials_path()`가 반환하는 **하나의 고정 파일** |
| `base_url` 파라미터 역할 | 함수 시그니처에는 있으나, 내부에서 즉시 무시(`del`) |

따라서 서버 주소를 바꿔도 저장된 API 키는 같은 파일 하나에 관리되며, 새로 저장하면 이전 것을 덮어씁니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 5위. del base_url을 짚어 base_url별 관리가 아님을 정확히 판정.

---

## 집계

| 문항 | 점수 | 만점 | 플래그 | 순위 | pyproject 진입 |
|---|---|---|---|---|---|
| Q01 | 2 | 2 | - | miss | 아니오 |
| Q02 | 0 | 2 | A | 1 | 아니오 |
| Q03 | 2 | 2 | - | 5 | 아니오 |
| Q04 | 2 | 2 | - | 1 | 아니오 |
| Q05 | 2 | 2 | - | miss | 아니오 |
| Q06 | 2 | 2 | - | 2 | 아니오 |
| Q07 | 1 | 1 | A | miss | 아니오 |
| Q08 | 1 | 1 | - | miss | 아니오 |
| Q09 | 1 | 1 | - | 1 | 아니오 |
| Q10 | 1 | 2 | A | 3 | 아니오 |
| Q11 | 2 | 2 | - | miss | 아니오 |
| Q12 | 2 | 2 | - | 1 | 아니오 |
| Q13 | 2 | 2 | - | 1 | **예 (8위)** |
| Q14 | 0 | 2 | A | miss | 아니오 |
| Q15 | 2 | 2 | - | 5 | 아니오 |
| **합계** | **22** | **27** | A 4건 | | 1/15 |

- A3(23/27)와 직접 비교 불가: 인덱스가 소실되어 요약이 새로 생성됨
- 이 22점이 새 기준선