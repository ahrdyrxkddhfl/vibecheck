# 실험 A2 — L1 파일 청크 도입 후 재측정

- 실행 시각: 2026-08-24 15:29
- 대상: ctxd-dev/ctxd
- 인덱스: .vibecheck/cache_ctxd_l1/chroma (9파일 67청크, tests 제외, L1 포함)
- top_k: 5
- 채점: `exp_a_grading.md` 기준. 검색 순위는 자동, 답변 품질은 수동
- 대조군: `exp_a_control.md` (4/27), `exp_a_results.md` (20/27, L1 없음)

---

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

**정답 청크 순위: miss**

### 답변

## 프로젝트 개요

이 프로젝트는 **ctxd**라는 이름의 Python 라이브러리이자 CLI 도구입니다.

### 핵심 역할

**앱(Slack, Google Drive, GitHub, Google Calendar 등)에 저장된 콘텐츠를 인덱싱하고, 그 인덱싱된 데이터를 검색·조회할 수 있도록 해주는 SDK 및 CLI 도구**입니다.

`src/ctxd/cli.py`의 `_build_parser` 함수에 적힌 설명을 그대로 옮기면:

> "Search and fetch content from your ctxd-connected apps, manage CLI authentication, and inspect indexed data."

즉, 연결된 앱의 콘텐츠를 검색하고 가져오며, 인증을 관리하고, 인덱싱된 데이터를 확인하는 것이 목적입니다.

---

### 주요 기능 (CLI 기준)

`src/ctxd/cli.py`의 `_build_parser` 함수에 정의된 서브커맨드들을 보면:

| 커맨드 | 역할 |
|---|---|
| `login` / `logout` | API 키를 저장하거나 삭제하여 인증 관리 |
| `status` | 현재 인증 상태 확인 |
| `install-app` | Slack, Google Drive 등 외부 앱 연동 설치 페이지(`https://app.ctxd.dev/knowledge-base/add-application`) 열기 (`src/ctxd/cli.py`의 `_handle_install_app`) |
| `search` | DSL(도메인 특화 쿼리 문법)을 사용해 인덱싱된 앱 콘텐츠 검색, 결과는 JSON |
| `fetch` | 문서 UID로 특정 문서 1건 조회 |
| `profile` | 연결된 앱 목록 및 인덱싱된 파일 트리 확인 |

---

### 데이터 구조

`src/ctxd/models.py`에 두 가지 핵심 데이터 모델이 정의되어 있습니다.

- **`DocumentResult`**: 검색으로 얻은 문서 한 건을 나타냅니다. `id`, `app_name`, `title`, `text`, `url`, `metadata` 등의 필드를 가집니다.
- **`ProfileResult`**: 사용자의 프로필 정보를 나타내며, `integration_access`(연결된 앱 접근 정보)와 `file_tree`(인덱싱된 파일 트리)를 포함합니다.

---

### 정리

한 문장으로 요약하면, **ctxd는 Slack·Google Drive 같은 외부 서비스에 저장된 문서들을 인덱싱하고, 그 내용을 검색하거나 가져올 수 있게 해주는 Python SDK이자 CLI 도구**입니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: 1**

### 답변

## `search()` 호출 시 서버 통신 방식

### 호출 흐름

제공된 코드에서 확인할 수 있는 호출 흐름은 다음과 같습니다:

```
Client.search()          (src/ctxd/client.py, 35-36행)
  → AsyncClient.search() (src/ctxd/async_client.py, 40-42행)
    → AsyncClient.call_tool("search", {"query": query})
```

### 단계별 설명

1. **`Client.search()`** (`src/ctxd/client.py`, 35-36행)  
   동기(일반) 함수처럼 사용할 수 있도록, 내부적으로 `_run()`을 통해 비동기 메서드를 동기적으로 실행합니다.

2. **`AsyncClient.search()`** (`src/ctxd/async_client.py`, 40-42행)  
   실제 통신은 `call_tool("search", {"query": query})`를 호출하는 방식으로 이루어집니다.  
   - 첫 번째 인자 `"search"` : 실행할 도구(tool)의 이름  
   - 두 번째 인자 `{"query": query}` : 검색어를 담은 파라미터

3. **결과 처리**  
   `call_tool()`이 반환한 응답(`payload`)을 `SearchResult.model_validate(payload)`로 변환하여 구조화된 객체로 반환합니다.

### 정확히 알 수 없는 부분

`call_tool()`의 구현 코드가 제공되지 않았으므로, **서버와의 실제 프로토콜(예: HTTP REST, WebSocket, MCP 등)과 엔드포인트 주소**는 제공된 코드만으로는 알 수 없습니다. 다만 `base_url` 속성이 `AsyncClient`에 존재하는 것으로 보아 (`src/ctxd/client.py`, 26-27행), 특정 서버 주소를 기반으로 통신한다는 점은 확인됩니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: miss**

### 답변

## 서버 응답 오류 처리 방식

오류 처리는 크게 **두 단계**로 나뉩니다.

---

### 1단계: HTTP 상태 코드 확인 (네트워크 수준 오류)

`src/ctxd/async_client.py`의 `AsyncClient._parse_response` 메서드에서 처리합니다.

```python
if response.status_code >= 400:
    message = f"ctxd MCP request failed with status {response.status_code}"
    try:
        error_payload = response.json()
    except ValueError:
        error_payload = response.text
    raise CtxdError(
        message, status_code=response.status_code, payload=error_payload
    )
```

HTTP 상태 코드가 **400 이상**이면:
1. 응답 본문을 **JSON으로 파싱**하려 시도합니다.
2. JSON 파싱이 실패하면 **텍스트 그대로** 가져옵니다.
3. `CtxdError` 예외를 발생시키며, 상태 코드와 응답 내용을 함께 담습니다.

---

### 2단계: 응답 형식이 맞지 않을 때 (프로토콜 수준 오류)

상태 코드는 정상이지만, 응답의 `Content-Type`이 지원하지 않는 형식이면:

```python
raise CtxdProtocolError(
    f"Unsupported MCP response content type: {content_type or 'unknown'}"
)
```

`src/ctxd/exceptions.py`의 `CtxdProtocolError`가 발생합니다. 이는 "서버가 응답은 했지만 예상한 형식(`application/json` 또는 `text/event-stream`)이 아닐 때" 쓰이는 예외입니다.

---

### 3단계: 응답 본문 내 오류 필드 확인 (애플리케이션 수준 오류)

`src/ctxd/cli.py`의 `_payload_has_error` 함수는 HTTP 상태 코드와 무관하게, **파싱된 응답 데이터 안에** `error` 또는 `dsl_parse_error` 필드가 있는지 확인합니다.

```python
def _payload_has_error(payload: dict) -> bool:
    if payload.get("error"):
        return True
    return bool(payload.get("dsl_parse_error"))
```

즉, 서버가 HTTP 200으로 응답했더라도 본문 안에 오류 내용이 담겨 있을 수 있고, 이를 별도로 체크하는 구조입니다.

---

### 예외 클래스 계층 요약

| 예외 클래스 | 발생 조건 |
|---|---|
| `CtxdError` | HTTP 400 이상 응답 |
| `CtxdProtocolError` | 지원하지 않는 응답 형식 (`CtxdError`의 하위 클래스) |
| `CtxdAuthError` | 로그인·토큰 갱신 실패 (`CtxdError`의 하위 클래스) |

`CtxdProtocolError`와 `CtxdAuthError` 모두 `src/ctxd/exceptions.py`에서 `CtxdError`를 상속하므로, `CtxdError` 하나만 잡아도 모든 오류를 포괄할 수 있습니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: 3**

### 답변

## 환경변수 이름: `CTXD_API_KEY`

`src/ctxd/cli.py`의 `_resolve_login_api_key` 함수와 `src/ctxd/config.py`의 `resolve_api_key` 함수 모두에서 다음과 같이 환경변수를 읽고 있습니다:

```python
env_api_key = os.getenv("CTXD_API_KEY")
```

즉, 환경변수 이름은 **`CTXD_API_KEY`** 입니다.

### 사용 예시

```bash
# Linux / macOS
export CTXD_API_KEY="your-api-key-here"

# 또는 명령 실행 시 인라인으로
CTXD_API_KEY="your-api-key-here" ctxd login
```

### API 키를 찾는 우선순위

`_resolve_login_api_key` 함수(`src/ctxd/cli.py` 227~243행)를 보면 API 키를 다음 순서로 찾습니다:

1. **환경변수** `CTXD_API_KEY` → 있으면 즉시 사용
2. **저장된 설정** (이전에 `ctxd login`으로 저장된 키)
3. **사용자 직접 입력** (터미널 프롬프트)

환경변수가 가장 먼저 확인되므로, 설정해두면 다른 방법보다 우선 적용됩니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: miss**

### 답변

제공된 코드 조각만으로는 HTTP 요청에 어떤 라이브러리를 사용하는지 직접적으로 확인하기 어렵습니다.

다만, `src/ctxd/async_client.py`에 `AsyncClient`라는 클래스가 있고, `src/ctxd/client.py`의 `Client` 클래스가 내부적으로 `self._async_client`를 보유하고 있음을 알 수 있습니다. 이 구조로 보아 비동기 HTTP 클라이언트를 래핑하고 있음을 알 수 있지만, 해당 파일들에서 어떤 라이브러리를 `import`하는지 보여주는 코드 조각이 제공되지 않아 구체적인 라이브러리 이름(예: `httpx`, `aiohttp` 등)은 확인할 수 없습니다.

`async_client.py`나 `client.py`의 `import` 구문이 포함된 코드 조각이 있다면 더 정확하게 답변드릴 수 있습니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: 2**

### 답변

## SDK가 직접 정의한 예외 클래스

파일 `src/ctxd/exceptions.py`에 총 **3개**의 예외 클래스가 정의되어 있습니다.

---

### 1. `CtxdError` (기본 예외 클래스)

```python
class CtxdError(Exception):
```

- 이 SDK의 **모든 커스텀 예외의 부모 클래스**입니다. Python 내장 `Exception`을 상속합니다.
- 아래 두 속성을 추가로 가집니다:
  - `status_code`: HTTP 상태 코드 (예: 401, 404 등). 없을 수도 있습니다 (`None` 허용).
  - `payload`: 오류와 함께 전달할 추가 데이터. 없을 수도 있습니다 (`None` 허용).
- 직접 발생시키거나, 아래 두 하위 클래스를 통해 발생합니다.

---

### 2. `CtxdProtocolError` (`CtxdError`의 하위 클래스)

```python
class CtxdProtocolError(CtxdError):
    """Raised when the MCP server response does not match the expected shape."""
```

- **MCP 서버의 응답이 예상한 형태와 다를 때** 발생합니다.
  - 예를 들어, 서버가 반환한 데이터의 구조(필드, 타입 등)가 SDK가 기대하는 형식과 맞지 않는 상황입니다.

---

### 3. `CtxdAuthError` (`CtxdError`의 하위 클래스)

```python
class CtxdAuthError(CtxdError):
    """Raised when login, refresh, or credential resolution fails."""
```

- **인증 관련 작업이 실패할 때** 발생합니다. 구체적으로는:
  - **로그인(login)** 실패
  - **토큰 갱신(refresh)** 실패
  - **자격증명 해석(credential resolution)** 실패

---

### 상속 구조 요약

```
Exception (Python 내장)
  └── CtxdError
        ├── CtxdProtocolError
        └── CtxdAuthError
```

`CtxdProtocolError`와 `CtxdAuthError`는 모두 `CtxdError`를 상속하므로, `except CtxdError`로 두 예외를 한 번에 잡을 수 있습니다.

---

> **참고:** 각 예외가 코드의 **어느 지점에서 실제로 `raise` 되는지**는 제공된 코드에 포함되어 있지 않아 확인할 수 없습니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: miss**

### 답변

## 동기 Client와 비동기 AsyncClient를 분리하고 감싸는 이유

### 1. 실제 통신 로직은 AsyncClient 한 곳에만 구현

`src/ctxd/async_client.py`의 `AsyncClient`에 `search`, `fetch_document`, `get_profile`, `call_tool` 등 실제 HTTP 통신 로직이 전부 들어 있습니다.

`src/ctxd/client.py`의 `Client`는 이 로직을 **전혀 중복하지 않고**, 단순히 `AsyncClient`의 메서드를 호출한 뒤 결과를 반환합니다:

```python
def search(self, query: str) -> SearchResult:
    return self._run(self._async_client.search(query))
```

이렇게 하면 네트워크 통신 코드를 한 군데만 수정해도 동기·비동기 양쪽에 동시에 반영됩니다.

---

### 2. 동기로 쓰고 싶은 사용자도 지원해야 하므로

Python에서 `async def`로 만든 함수(코루틴)는 `await`나 이벤트 루프 없이는 실행되지 않습니다. 일반적인 스크립트나 Jupyter 환경 등 **비동기를 쓰지 않는 환경**에서는 `AsyncClient`를 그대로 쓸 수 없습니다.

`Client._run()` 메서드가 이 문제를 해결합니다:

```python
@staticmethod
def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)   # 이벤트 루프가 없으면 직접 실행

    # 이미 이벤트 루프가 돌고 있으면 별도 스레드에서 실행
    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
```

- **이벤트 루프가 없는 환경** (일반 스크립트): `asyncio.run()`으로 직접 실행
- **이벤트 루프가 이미 돌고 있는 환경** (Jupyter 노트북 등): 중첩 실행이 불가능하므로 별도 스레드를 만들어 그 안에서 `asyncio.run()` 호출

이처럼 환경에 따라 두 경로를 나누는 것으로 보아, **"동기 사용자도 어느 환경에서든 그냥 쓸 수 있게"** 하는 것이 `Client`의 존재 이유로 보입니다.

---

### 3. 구조 요약

```
사용자 (동기 환경)          사용자 (비동기 환경)
      ↓                            ↓
   Client                     AsyncClient
(client.py)               (async_client.py)
      ↓ _run()으로 감싸서 호출
   AsyncClient
(실제 HTTP 통신 담당)
```

- `AsyncClient` (`src/ctxd/async_client.py`): 실제 로직 담당
- `Client` (`src/ctxd/client.py`): 동기 인터페이스를 제공하는 얇은 래퍼(wrapper)

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: miss**

### 답변

## config.json과 credentials.json을 나눈 이유

코드를 보면 두 파일의 **저장 내용**과 **접근 방식**이 명확히 구분되어 있습니다.

---

### 1. 저장하는 데이터의 성격이 다릅니다

| 파일 | 저장 내용 | 관련 코드 |
|---|---|---|
| `config.json` | `base_url` 같은 일반 설정값 | `src/ctxd/config.py` `save_config` |
| `credentials.json` | `api_key` 같은 민감한 자격증명 | `src/ctxd/secure_store.py` `save_secret_bundle` |

`src/ctxd/config.py`의 `save_api_key` 함수를 보면 이 구분이 명확히 드러납니다.

```python
def save_api_key(api_key: str, *, base_url: str | None = None) -> Path:
    resolved_base_url = resolve_base_url(base_url)
    config = load_config()
    config["base_url"] = resolved_base_url   # ← base_url은 config.json에
    save_secret_bundle(
        {"api_key": api_key.strip()}, ...    # ← api_key는 credentials.json에
    )
    return save_config(config)
```

같은 저장 동작임에도 일반 설정과 API 키를 **서로 다른 함수·파일**로 보냅니다.

---

### 2. 파일 경로를 독립적으로 제어할 수 있습니다

`src/ctxd/secure_store.py`의 `get_credentials_path` 함수를 보면:

```python
configured = os.getenv("CTXD_CREDENTIALS_PATH")  # 자격증명만 따로 경로 지정 가능
if configured:
    return Path(configured).expanduser()
```

`CTXD_CREDENTIALS_PATH`라는 **전용 환경 변수**가 따로 존재합니다. 이는 자격증명 파일만 별도의 보안 위치(예: 암호화된 디렉터리)에 저장하고 싶을 때 config.json을 건드리지 않고 분리 배치할 수 있도록 의도된 설계입니다.

---

### 3. 결론

코드 구조로 보아, 이 분리는 **"무엇이 민감한가"를 코드 레벨에서 명시**하기 위한 설계입니다. 두 파일 모두 권한을 `0o600`(소유자만 읽기/쓰기)으로 설정하지만, 자격증명은 `secure_store.py`라는 **별도 모듈**로 완전히 격리되어 있어 나중에 저장 방식을 교체(예: OS 키체인 연동)하더라도 `config.py` 쪽은 수정하지 않아도 되는 구조입니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: 1**

### 답변

## `id`와 `document_uid`를 둘 다 허용한 이유

`src/ctxd/models.py`의 `SearchItem` 클래스를 보면:

```python
id: str = Field(validation_alias=AliasChoices("id", "document_uid"))
```

`AliasChoices`는 Pydantic의 기능으로, 서버 응답(JSON)에서 특정 필드를 읽어올 때 **여러 이름 중 하나로 들어와도 같은 필드로 인식**하게 해줍니다. 즉, 서버가 `"id"`라는 키로 보내든 `"document_uid"`라는 키로 보내든, 모두 `SearchItem.id`에 담기게 됩니다.

이렇게 설계한 이유는 코드에서 읽어낼 수 있습니다:

- **`fetch` 커맨드(`src/ctxd/cli.py`)** 에서는 인자 이름을 `document_uid`라고 부르고 (`fetch_parser.add_argument("document_uid", ...)`), 도움말에도 "Document UID returned by search"라고 명시되어 있습니다.
- **`Client.fetch_document`(`src/ctxd/client.py`)** 역시 파라미터 이름으로 `document_uid`를 사용합니다.

즉, 코드 전반에서는 `document_uid`라는 용어를 사용하고 있는데, **검색 결과를 반환하는 서버(API)가 경우에 따라 `id` 또는 `document_uid` 중 어느 키 이름으로 응답할 수 있는 상황**을 고려해, 두 이름 모두를 허용하도록 만든 것으로 보입니다.

쉽게 말하면, "서버 응답 형식이 통일되어 있지 않거나, 버전에 따라 키 이름이 다를 수 있으니 둘 다 받아들이자"는 방어적 설계입니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: 4**

### 답변

## `ctxd login` API 키 저장 흐름

### 전체 흐름 요약

```
사용자 입력
    → _handle_login()
        → _resolve_login_api_key()
            → _prompt_api_key()   ← 사용자가 직접 입력
        → Client.get_profile()    ← API 키 유효성 검증
        → save_api_key()          ← 저장
            → save_secret_bundle()  ← 실제 보안 저장소에 기록
```

---

### 단계별 설명

#### 1. `_handle_login` (`src/ctxd/cli.py`, 183~198행)
`ctxd login` 명령의 진입점입니다.  
`_resolve_login_api_key()`를 호출해 API 키를 얻고, `should_save`가 `True`인 경우에만 `save_api_key()`를 호출해 저장합니다.

#### 2. `_resolve_login_api_key` (`src/ctxd/cli.py`, 227~243행)
API 키를 **세 가지 경로**로 찾습니다 (우선순위 순서):

| 순서 | 출처 | `should_save` 반환값 |
|------|------|----------------------|
| 1 | 환경 변수 `CTXD_API_KEY` | `False` (저장 안 함) |
| 2 | 이미 저장된 키 (`resolve_api_key()`) | `False` (저장 안 함) |
| 3 | 사용자 직접 입력 (`_prompt_api_key()`) | `True` (저장 함) |

**사용자가 직접 입력한 경우에만** `should_save = True`가 반환되어 저장 단계로 넘어갑니다.

#### 3. `save_api_key` (`src/ctxd/config.py`, 74~83행)
API 키를 실제로 저장하는 함수입니다.  
내부적으로 `save_secret_bundle({"api_key": api_key.strip()}, ...)` 를 호출해 **보안 저장소(secure_store)** 에 키를 기록하고, 베이스 URL 정보는 별도의 설정 파일(`save_config()`)에 저장합니다.

---

### 핵심 정리

- 사용자가 입력한 API 키는 `_handle_login` → `_resolve_login_api_key` → `_prompt_api_key` 순으로 수집됩니다.
- 유효성 검증(`Client.get_profile()`) 통과 후, `save_api_key` → `save_secret_bundle`을 통해 **보안 저장소**에 최종 저장됩니다.
- 환경 변수나 이미 저장된 키를 사용한 경우에는 저장 단계를 건너뜁니다.

`save_secret_bundle`의 구체적인 저장 위치(파일 경로, 키체인 등)는 제공된 코드만으로는 확인할 수 없습니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: miss**

### 답변

## `Client.search()` 호출 경로 분석

### 전체 흐름 요약

```
Client.search()   →   AsyncClient.search()   →   AsyncClient.call_tool()   →   HTTP 요청
(동기 래퍼)           (비동기 구현)               (실제 전송)
```

---

### 단계별 설명

#### 1단계: `Client.search()` — `src/ctxd/client.py` 35–36행

```python
def search(self, query: str) -> SearchResult:
    return self._run(self._async_client.search(query))
```

- 사용자가 직접 호출하는 **동기(synchronous) 메서드**입니다.
- 내부적으로 `self._async_client`라는 `AsyncClient` 인스턴스를 보유하고 있으며, 그 비동기 메서드를 `self._run()`으로 감싸서 동기처럼 실행합니다.
- `_run()`이 비동기 루프를 대신 돌려주는 역할을 합니다(이른바 "동기 래퍼" 패턴).

#### 2단계: `AsyncClient.search()` — `src/ctxd/async_client.py` 40–42행

```python
async def search(self, query: str) -> SearchResult:
    payload = await self.call_tool("search", {"query": query})
    return SearchResult.model_validate(payload)
```

- 실제 비동기 로직이 있는 곳입니다.
- `self.call_tool("search", {"query": query})`를 `await`(기다려서 결과를 받아옴)합니다.
- `call_tool`이 반환한 원시 데이터를 `SearchResult.model_validate()`로 파싱해서 구조화된 객체로 변환합니다.

#### 3단계: `AsyncClient.call_tool()` — HTTP 요청 발생

- `call_tool()`은 제공된 코드 조각에 직접 구현이 보이지 않지만, `AsyncClient.search()`가 이를 호출하고 있으므로 `AsyncClient` 내부에 정의된 메서드입니다.
- 이름과 구조로 보아 `"search"`라는 도구 이름과 `{"query": query}` 파라미터를 서버에 전달하는 HTTP 요청을 담당하는 지점입니다. 서버 주소는 `AsyncClient._base_url`(`src/ctxd/async_client.py` 28–29행)에서 가져옵니다.

---

### 정리

| 단계 | 파일 | 역할 |
|------|------|------|
| `Client.search()` | `src/ctxd/client.py:35` | 동기 진입점, 비동기 호출을 동기로 변환 |
| `AsyncClient.search()` | `src/ctxd/async_client.py:40` | 비동기 로직, `call_tool` 호출 및 결과 파싱 |
| `AsyncClient.call_tool()` | `src/ctxd/async_client.py` (내부) | 실제 HTTP 요청 전송 |

`call_tool()`의 구체적인 구현(예: 어떤 HTTP 라이브러리를 쓰는지, 엔드포인트 경로가 무엇인지)은 제공된 코드 조각에 포함되어 있지 않아 확인할 수 없습니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: 1**

### 답변

## API 키 탐색 순서

코드에는 두 가지 상황에 따라 API 키를 찾는 함수가 각각 존재합니다.

---

### 1. 일반적인 API 호출 시 — `resolve_api_key` (`src/ctxd/config.py`, 24–41행)

| 순서 | 출처 | 설명 |
|------|------|------|
| 1 | **함수 인자** (`api_key` 매개변수) | 호출 시 직접 넘긴 값 |
| 2 | **환경 변수** `CTXD_API_KEY` | OS 환경 변수 |
| 3 | **저장된 번들** (`load_secret_bundle`) | 로컬에 저장된 인증 정보 |

셋 모두 없으면 `None`을 반환합니다.

---

### 2. 로그인 명령 실행 시 — `_resolve_login_api_key` (`src/ctxd/cli.py`, 227–243행)

| 순서 | 출처 | 설명 |
|------|------|------|
| 1 | **환경 변수** `CTXD_API_KEY` | OS 환경 변수 |
| 2 | **저장된 번들** (`resolve_api_key()` 호출) | 로컬에 저장된 인증 정보 |
| 3 | **사용자 직접 입력** (`_prompt_api_key`) | 터미널에서 `getpass`로 입력받음 |

이 함수는 키와 함께 **"사용자가 직접 입력했는지 여부"** (`bool`)도 함께 반환합니다. 사용자 입력인 경우에만 `True`가 되는데, 이는 이후 로직에서 입력된 키를 저장할지 결정하는 데 쓰이는 것으로 보입니다.

---

### 두 경로의 차이점

- **일반 호출**(`resolve_api_key`)은 "함수 인자 → 환경 변수 → 저장소" 순입니다.
- **로그인 명령**(`_resolve_login_api_key`)은 인자를 받지 않으므로 "환경 변수 → 저장소 → 터미널 입력" 순이며, 터미널 입력이 추가됩니다.
- 터미널 입력(`_prompt_api_key`)은 `sys.stdin.isatty()`를 확인하므로, **비대화형 환경(예: 파이프, 자동화 스크립트)에서는 입력 프롬프트가 뜨지 않고 바로 `None`을 반환**합니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: 1**

### 답변

## ctxd CLI 명령어 목록

`src/ctxd/cli.py`의 `_build_parser` 함수에 정의된 명령어들은 다음과 같습니다.

---

### 인증 관련

| 명령어 | 설명 |
|---|---|
| `ctxd login` | API 키를 입력받아 저장합니다. 이후 CLI/SDK 호출에 사용됩니다. |
| `ctxd logout` | 저장된 API 키를 삭제합니다. |
| `ctxd status` | 현재 인증(API 키)이 설정되어 있는지 확인합니다. |

---

### 앱 설치

| 명령어 | 옵션 | 설명 |
|---|---|---|
| `ctxd install-app` | `--no-browser` | Slack, Google Drive 등 앱 연동 설치 페이지를 엽니다. `--no-browser`를 사용하면 브라우저를 열지 않고 URL만 출력합니다. |

---

### 데이터 조회

| 명령어 | 인자/옵션 | 설명 |
|---|---|---|
| `ctxd search QUERY` | `QUERY` (필수) | 인덱싱된 앱 콘텐츠를 검색하고 JSON으로 결과를 출력합니다. 예: `ctxd search text:deployment application:slack` |
| `ctxd fetch DOCUMENT_UID` | `document_uid` (필수), `--json` | 특정 문서 UID로 문서 하나를 가져옵니다. `--json`을 붙이면 전체 응답을 JSON으로 출력합니다. |
| `ctxd profile` | `--json` | 연결된 앱 연동 목록과 인덱싱된 파일 트리를 보여줍니다. `--json`을 붙이면 JSON으로 출력합니다. |

---

### 버전 확인 (서브커맨드가 아닌 옵션)

| 옵션 | 설명 |
|---|---|
| `ctxd --version` | 설치된 ctxd 버전을 출력합니다. |

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: miss**

### 답변

## 질문에 대한 답변

제공된 코드만으로는 **실제 요청 URL**이 정확히 무엇인지 알 수 없습니다.

---

### 이유 설명

제공된 코드 조각들은 다음 역할만 담당합니다:

1. **`resolve_base_url` (`src/ctxd/config.py`, 97-109행)**
   - `https://ctxd.example.com` 을 인자로 받으면, 그 값을 공백 제거 후 그대로 반환합니다.
   - 즉, `_base_url` 에는 `"https://ctxd.example.com"` 이 저장됩니다.

2. **`Client.base_url` / `AsyncClient.base_url` (`src/ctxd/client.py`, `src/ctxd/async_client.py`)**
   - 단순히 저장된 `_base_url` 값을 꺼내 반환할 뿐입니다.

---

### 알 수 없는 이유

실제 **HTTP 요청이 어떤 URL로 전송되는지** 확인하려면, 각 API 엔드포인트 경로(예: `/v1/...`)가 `base_url` 에 어떻게 조합되는지를 보여주는 코드가 필요합니다. 예를 들면:

- 요청 메서드(예: `get`, `post`)가 `base_url`과 경로를 합치는 방식
- 경로에 슬래시가 어떻게 처리되는지

이 부분은 제공된 코드 조각에 포함되어 있지 않아, 검토했으나 근거를 찾지 못했습니다.

---

### 확실한 사실

`https://ctxd.example.com` 을 인자로 주면, 이 값은 **변형 없이** `_base_url`로 저장되고 반환됩니다. 거기에 어떤 경로가 붙어서 실제 요청이 만들어지는지는 제공된 코드만으로는 알 수 없습니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

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

**정답 청크 순위: 3**

### 답변

## 답변: API 키는 서버 주소(base_url)마다 따로 관리되지 않습니다.

### 근거

`src/ctxd/secure_store.py`의 `save_secret_bundle` 함수와 `load_secret_bundle` 함수를 보면, 두 함수 모두 `base_url`과 `client_id` 매개변수를 받지만 **즉시 버립니다**:

```python
def save_secret_bundle(bundle, *, base_url, client_id):
    del base_url, client_id  # ← 받자마자 삭제
    path = get_credentials_path()  # ← 항상 같은 경로 사용
    ...
```

```python
def load_secret_bundle(*, base_url, client_id):
    del base_url, client_id  # ← 받자마자 삭제
    path = get_credentials_path()  # ← 항상 같은 경로 사용
    ...
```

`del base_url, client_id`로 인자를 바로 폐기하고, 그 이후에는 `get_credentials_path()`가 반환하는 **단일 고정 경로**에만 저장하고 읽습니다. 즉, `base_url`이 무엇이든 상관없이 항상 같은 파일 하나에 덮어씁니다.

### 실제 동작 방식

- **저장** (`save_api_key`): `base_url`이 달라도 같은 파일에 덮어씀
- **삭제** (`clear_api_key`): `base_url`에 무관하게 같은 파일을 삭제함
- **읽기** (`load_secret_bundle`): `base_url`에 무관하게 같은 파일을 읽음

결론적으로, `base_url`을 구분하는 구조는 함수 시그니처(매개변수 이름)에만 형식적으로 남아 있을 뿐, 실제 저장 로직에서는 전혀 활용되지 않습니다. API 키는 서버 주소와 무관하게 **하나의 파일에만** 보관됩니다.

### 채점

- 점수(0~2): 
- 플래그(H/A/-): 
- 메모: 

---

