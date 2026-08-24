# 실험 A — 본 측정 (인덱스 제공)

- 실행 시각: 2026-08-24 14:49
- 대상: ctxd-dev/ctxd
- 인덱스: .vibecheck/cache_ctxd/chroma (9파일 59청크, tests 제외)
- top_k: 5
- 채점: `exp_a_grading.md` 기준. 검색 순위는 자동, 답변 품질은 수동
- 대조군: `exp_a_control.md` (4/27)

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
5. `src/ctxd/config.py::save_api_key`

**정답 청크 순위: miss**

### 답변

## 이 프로젝트는 무슨 일을 하는 라이브러리인가?

이 프로젝트는 **ctxd**라는 서비스의 Python SDK이자 CLI(명령줄 도구)입니다.

---

### 핵심 기능

**ctxd**는 Slack, Google Drive, GitHub, Google Calendar 같은 외부 앱들을 연결해서, 그 앱들에 쌓인 콘텐츠(문서, 메시지 등)를 **검색하고 가져올 수 있게 해주는** 라이브러리입니다.

구체적으로는 다음 기능을 제공합니다:

| 기능 | 설명 |
|---|---|
| **인증 관리** | API 키를 저장(`login`)하거나 삭제(`logout`)하고, 설정 상태를 확인(`status`)합니다 |
| **앱 연결** | Slack, Google Drive 등 외부 앱을 연결하는 설치 페이지(`install-app`)를 안내합니다 |
| **콘텐츠 검색** | 연결된 앱들의 색인된 콘텐츠를 DSL(검색 질의어)로 검색(`search`)합니다 |
| **문서 조회** | 검색 결과로 얻은 문서 UID로 특정 문서를 상세 조회(`fetch`)합니다 |
| **프로필 확인** | 연결된 통합 앱 목록과 색인된 파일 트리를 확인(`profile`)합니다 |

---

### 근거가 되는 코드

- `src/ctxd/cli.py`의 `_build_parser` 함수에서 CLI 명령어 전체 구조와 각 설명이 명시되어 있습니다.
- `src/ctxd/models.py`의 `DocumentResult` 클래스를 보면, 검색 결과 문서가 `id`, `app_name`, `title`, `text`, `url`, `metadata` 같은 필드를 가진다는 것을 알 수 있습니다. 즉 여러 앱에서 가져온 문서를 통일된 형태로 다룹니다.
- `src/ctxd/models.py`의 `ProfileResult` 클래스에는 `integration_access`(연결된 통합 앱 접근 정보)와 `file_tree`(색인된 파일 트리)가 있어, 연결된 앱 관리 기능이 있음을 알 수 있습니다.
- `src/ctxd/config.py`의 `save_api_key` 함수에서 API 키를 안전하게 저장하는 인증 흐름이 있음을 알 수 있습니다.
- `src/ctxd/cli.py`의 `_handle_install_app` 함수에서 앱 연결 URL이 `https://app.ctxd.dev/knowledge-base/add-application`임을 확인할 수 있습니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 miss(client.py::Client). 그러나 _build_parser와 ProfileResult/DocumentResult로 프로젝트 성격을 정확히 재구성. 검색 실패가 답변 실패로 직결되지 않는 사례.

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
4. `src/ctxd/async_client.py::AsyncClient.base_url`
5. `src/ctxd/secure_store.py::load_secret_bundle`

**정답 청크 순위: 1**

### 답변

## `search()` 호출 시 서버 통신 방식

### 호출 흐름

```
Client.search()  →  AsyncClient.search()  →  AsyncClient.call_tool()
```

1. **`Client.search()`** (`src/ctxd/client.py`, 35-36행)
   - 동기(sync) 메서드입니다.
   - 내부적으로 `self._run(self._async_client.search(query))`를 호출하여, 비동기 메서드를 동기 방식으로 실행합니다.

2. **`AsyncClient.search()`** (`src/ctxd/async_client.py`, 40-42행)
   - 비동기(async) 메서드입니다.
   - `self.call_tool("search", {"query": query})`를 호출합니다.
     - 도구 이름은 `"search"`, 전달 파라미터는 `{"query": 검색어}` 형태입니다.
   - 서버로부터 받은 응답(`payload`)을 `SearchResult.model_validate(payload)`로 검증한 뒤 반환합니다.

### 실제 통신의 핵심: `call_tool()`

실제 서버와의 통신은 `call_tool()` 메서드에서 이루어집니다. `search()`는 `call_tool("search", {"query": query})`를 호출하는 방식으로, **"search"라는 이름의 도구(tool)를 원격 서버에 요청**합니다.

다만, `call_tool()`의 구체적인 구현 코드(예: HTTP 요청인지, WebSocket인지, MCP 프로토콜인지 등)는 **제공된 코드 조각에 포함되어 있지 않아** 정확한 통신 방식을 단정할 수 없습니다.

### 서버 주소

통신 대상 서버의 주소는 `AsyncClient._base_url` (`src/ctxd/async_client.py`, 28-29행)에 저장되어 있으며, `Client.base_url` / `AsyncClient.base_url`을 통해 확인할 수 있습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: 정답 청크 1등. 호출 흐름은 정확하나 SSE/JSON-RPC를 말하지 못함. 답이 call_tool 본문에 있는데 그 청크가 top_k에 없어 '구체적 통신 방식은 알 수 없다'고 기권. 청크 경계 문제.

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

**정답 청크 순위: 5**

### 답변

## 서버 응답 오류 처리 방식

오류 처리는 크게 **두 단계**로 나뉩니다.

---

### 1단계: HTTP 상태 코드 확인 (`_parse_response`)
**파일: `src/ctxd/async_client.py`, 109–131행**

HTTP 응답이 도착하면 가장 먼저 상태 코드를 확인합니다.

```
상태 코드 >= 400 (예: 404, 500)
  → 응답 본문을 JSON으로 파싱 시도
      성공하면 JSON 객체를 오류 정보로 사용
      실패하면 텍스트 그대로 사용
  → CtxdError 예외 발생
      (메시지: "ctxd MCP request failed with status {상태코드}")
```

상태 코드가 정상이면 `Content-Type` 헤더를 보고 JSON 또는 SSE(Server-Sent Events) 형식으로 파싱합니다. 둘 다 아니면 `CtxdProtocolError`(응답 형식이 맞지 않을 때 쓰는 예외)를 발생시킵니다.

---

### 2단계: JSON 응답 내용 확인 (`_parse_json_payload`)
**파일: `src/ctxd/async_client.py`, 146–174행**

HTTP 상태 코드가 정상이어도 응답 **내용** 자체에 오류가 있을 수 있습니다. 이 단계에서 추가로 검사합니다.

| 검사 항목 | 발생 예외 |
|---|---|
| 응답 본문에 `"error"` 키가 있음 (JSON-RPC 규약상 오류) | `CtxdError` |
| `result` 필드가 없거나 객체가 아님 | `CtxdProtocolError` |
| `result.content`가 없거나 빈 배열 | `CtxdProtocolError` |
| 첫 번째 콘텐츠 항목이 `text` 타입이 아님 | `CtxdProtocolError` |
| `text` 값이 문자열이 아님 | `CtxdProtocolError` |
| `result.isError`가 `true` | `CtxdError` |
| `text` 값이 유효한 JSON이 아님 | `CtxdProtocolError` |

---

### 예외 클래스 구조
**파일: `src/ctxd/exceptions.py`**

- `CtxdError` — 기본 오류 클래스. HTTP 오류나 JSON-RPC 오류에 사용됩니다.
- `CtxdProtocolError` — `CtxdError`의 하위 클래스. 응답이 예상한 **형식**과 맞지 않을 때 사용됩니다.
- `CtxdAuthError` — `CtxdError`의 하위 클래스. 인증 관련 실패에 사용됩니다.

---

### CLI에서의 추가 처리
**파일: `src/ctxd/cli.py`, 313–316행**

예외를 던지지 않고 성공적으로 파싱된 응답 내에서도, `_payload_has_error` 함수가 페이로드 딕셔너리 안의 `"error"` 또는 `"dsl_parse_error"` 키를 검사하여 애플리케이션 수준의 오류를 추가로 판별합니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 5등이지만 _parse_response가 1등으로 들어와 보완. 2단 구조와 예외 3종, 발생 조건 모두 정확.

---

## Q04 (식별자)

**질문**: API 키를 환경변수로 넘기려면 변수 이름을 뭐라고 해야 해?

**정답 요지**: CTXD_API_KEY. (설정 파일 경로는 CTXD_CONFIG_PATH, 서버 주소는 CTXD_BASE_URL)

**근거 출처**: README + tests/test_sdk.py::test_client_search_uses_api_key_env  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/config.py::resolve_api_key`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/cli.py::_resolve_login_api_key`
2. `src/ctxd/config.py::resolve_api_key`
3. `src/ctxd/cli.py::_handle_login`
4. `src/ctxd/async_client.py::AsyncClient._resolve_access_token`
5. `src/ctxd/config.py::save_api_key`

**정답 청크 순위: 2**

### 답변

## 환경변수 이름: `CTXD_API_KEY`

`src/ctxd/config.py`의 `resolve_api_key` 함수와 `src/ctxd/cli.py`의 `_resolve_login_api_key` 함수 모두 아래와 같이 동일한 환경변수 이름을 사용합니다:

```python
os.getenv("CTXD_API_KEY")
```

따라서 환경변수 이름은 **`CTXD_API_KEY`** 입니다.

### 사용 예시 (셸)
```bash
export CTXD_API_KEY="your-api-key-here"
```

### 참고: API 키 조회 우선순위

코드에 따르면 API 키는 다음 순서로 탐색됩니다:

1. **환경변수 `CTXD_API_KEY`** — 가장 먼저 확인
2. **저장된 설정(secret)** — `save_api_key`로 저장된 값
3. **직접 입력(프롬프트)** — 대화형 터미널에서 사용자에게 입력 요청

환경변수가 설정되어 있으면 저장된 설정이나 입력 프롬프트 없이 바로 해당 값이 사용됩니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: CTXD_API_KEY는 정확. 그러나 우선순위를 '환경변수 먼저'로 오답. 실제 resolve_api_key는 인자 우선. CLI 전용 _resolve_login_api_key(1등)를 SDK 함수로 혼동. 정답 청크가 2등에 있었음에도 유사 청크에 밀림.

---

## Q05 (식별자)

**질문**: HTTP 요청을 보낼 때 어떤 라이브러리를 써?

**정답 요지**: httpx. 비동기 클라이언트(httpx.AsyncClient)를 사용.

**근거 출처**: tests/test_sdk.py (httpx.AsyncClient.post를 patch해 테스트)  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/async_client.py::AsyncClient`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/secure_store.py::load_secret_bundle`
2. `src/ctxd/async_client.py::AsyncClient.base_url`
3. `src/ctxd/secure_store.py::save_secret_bundle`
4. `src/ctxd/async_client.py::AsyncClient.fetch_document`
5. `src/ctxd/client.py::Client.base_url`

**정답 청크 순위: miss**

### 답변

제공된 코드 조각들만으로는 HTTP 요청에 어떤 라이브러리를 사용하는지 알 수 없습니다.

제공된 코드에는:
- `src/ctxd/secure_store.py` — 자격증명 파일 저장/로드 로직
- `src/ctxd/async_client.py` — `base_url` 반환, `fetch_document` 호출
- `src/ctxd/client.py` — `AsyncClient`를 감싸는 동기 클라이언트

등이 포함되어 있지만, 실제 HTTP 요청을 보내는 부분(예: `httpx`, `aiohttp`, `requests` 등의 import나 호출 코드)은 제공된 조각 어디에도 나타나지 않습니다.

HTTP 라이브러리를 확인하려면 `src/ctxd/async_client.py`의 import 구문이나 `call_tool` 메서드의 구현 코드가 필요합니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): A
- 메모: httpx를 말하지 못함. 정답 청크 miss로 imports 주입이 도달하지 못했다. imports는 청크에 붙어 있어 그 청크가 검색되지 않으면 효력이 없다. 다만 무엇이 없어서 답할 수 없는지 정확히 지목.

---

## Q06 (식별자)

**질문**: 이 SDK가 직접 정의한 예외 클래스는 뭐가 있고 각각 언제 발생해?

**정답 요지**: CtxdError(기본), CtxdProtocolError(응답 모양이 예상과 다를 때), CtxdAuthError(API 키를 못 찾았을 때). 뒤 둘은 CtxdError를 상속.

**근거 출처**: tests/test_sdk.py::test_async_client_requires_api_key 외  
**인덱스내 근거**: Y  
**정답 청크**: `src/ctxd/exceptions.py::CtxdError`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/exceptions.py::CtxdError`
2. `src/ctxd/exceptions.py::CtxdAuthError`
3. `src/ctxd/models.py::SearchResult`
4. `src/ctxd/models.py::SearchItem`
5. `src/ctxd/exceptions.py::CtxdError.__init__`

**정답 청크 순위: 1**

### 답변

## SDK가 정의한 예외 클래스

`src/ctxd/exceptions.py`에 두 가지 예외 클래스가 정의되어 있습니다.

---

### 1. `CtxdError` (4–14행)

Python 내장 `Exception`을 상속한 **기본 예외 클래스**입니다.

**담을 수 있는 정보:**
- `message` (str) — 에러 설명 문자열
- `status_code` (int | None) — HTTP 상태 코드 (선택)
- `payload` (Any | None) — 추가 데이터 (선택)

**발생 시점:** 제공된 코드만으로는 이 클래스가 직접 어디서 `raise`되는지 알 수 없습니다. 다만 아래 `CtxdAuthError`의 부모 클래스이므로, SDK 전반의 공통 에러 기반으로 설계된 것으로 보입니다.

---

### 2. `CtxdAuthError` (21–22행)

`CtxdError`를 상속한 **인증 관련 예외 클래스**입니다.

**발생 시점:** 클래스의 docstring에 명시된 대로, 다음 세 가지 상황에서 발생합니다:
- **로그인(login) 실패**
- **토큰 갱신(refresh) 실패**
- **인증 정보 해석(credential resolution) 실패**

---

### 관계 요약

```
Exception
  └── CtxdError          # 공통 기반 예외 (메시지 + HTTP 코드 + 페이로드)
        └── CtxdAuthError  # 인증 실패 전용 예외
```

`CtxdAuthError`가 `CtxdError`를 상속하고 있으므로, `CtxdError`를 잡는(catch) 코드는 인증 에러도 함께 처리하게 됩니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: 정답 청크 1등. CtxdError와 CtxdAuthError만 서술하고 CtxdProtocolError 누락. 3등/4등에 있었으나 활용 못 함.

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
3. `src/ctxd/async_client.py::AsyncClient.call_tool`
4. `src/ctxd/async_client.py::AsyncClient`
5. `src/ctxd/client.py::Client.call_tool`

**정답 청크 순위: miss**

### 답변

## 왜 동기 `Client`와 비동기 `AsyncClient`를 분리했는가?

### 핵심 이유: 서로 다른 실행 환경 지원

Python에는 두 가지 실행 방식이 있습니다.

- **비동기(async)**: `async def`, `await`를 사용하며, `asyncio` 이벤트 루프 위에서 동작합니다.
- **동기(sync)**: 일반적인 함수 호출 방식으로, `await` 없이 순서대로 실행됩니다.

비동기 코드와 동기 코드는 서로 직접 섞어 쓸 수 없기 때문에, 두 환경을 모두 지원하려면 각각의 인터페이스가 필요합니다.

---

### `Client`가 `AsyncClient`를 감싸는 구조

`src/ctxd/client.py`의 `Client.call_tool`을 보면:

```python
def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return self._run(self._async_client.call_tool(name, arguments))
```

동기 `Client`는 내부에 `AsyncClient` 인스턴스(`self._async_client`)를 갖고, `self._run()`을 통해 비동기 함수를 동기적으로 실행시킵니다.

이렇게 감싸는 구조를 선택한 이유는 코드에서 추론할 수 있습니다:

- **로직 중복 방지**: HTTP 요청, 응답 파싱, 에러 처리 등 **실제 핵심 로직은 `AsyncClient` 하나에만** 구현되어 있습니다 (`src/ctxd/async_client.py`의 `call_tool`, `_parse_response`, `_parse_json_payload` 등). `Client`는 그 로직을 다시 구현하지 않고 그대로 재사용합니다.
- **유지보수 용이**: 로직 변경이 필요할 때 `AsyncClient`만 수정하면 동기 `Client`에도 자동으로 반영됩니다.

---

### `AsyncClient` 자체의 설계

`src/ctxd/async_client.py`의 `AsyncClient.call_tool`을 보면, 컨텍스트 매니저(`async with ... as client:`)로 사용할 때와 아닐 때를 모두 처리합니다:

```python
if self._client is not None:
    # async with AsyncClient() as c: 형태로 쓴 경우 → 연결 재사용
    response = await self._client.post(...)
else:
    # 단독 호출 시 → 매번 새 연결 생성 후 닫기
    async with httpx.AsyncClient(timeout=self._timeout) as client:
        response = await client.post(...)
```

`__aenter__`에서 `httpx.AsyncClient`를 생성하고, `__aexit__`에서 `aclose()`로 닫는 구조로 보아, 연결을 반복해서 재사용하고 싶은 경우(`async with` 사용)와 일회성 호출 두 가지 사용 패턴을 모두 지원하도록 설계되었음을 알 수 있습니다.

---

### 요약

| 목적 | 설명 |
|---|---|
| 환경 분리 | 비동기(`AsyncClient`)와 동기(`Client`) 실행 환경을 각각 지원 |
| 코드 재사용 | 핵심 로직은 `AsyncClient`에만 두고, `Client`는 감싸서 재사용 |
| 이중 사용 패턴 | `AsyncClient`는 컨텍스트 매니저(연결 재사용)와 단독 호출 모두 지원 |

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: in_index=N. 만점. 구조(Client가 AsyncClient를 감쌈)를 설명하고 중복 방지라는 근거까지 코드에서 도출. 정답 청크는 miss였으나 call_tool로 동일 결론에 도달. 컨트롤과 달리 실제 심볼명을 근거로 씀.

---

## Q08 (왜)

**질문**: 왜 설정(config.json)과 자격증명(credentials.json)을 다른 파일로 나눴어?

**정답 요지**: 의도는 코드에 없음. clear_api_key가 credentials만 지우고 config의 base_url은 남긴다는 동작까지 짚으면 1점. 기권해도 1점.

**근거 출처**: tests/test_sdk.py::test_clear_api_key_keeps_base_url_and_removes_plaintext_credentials  
**인덱스내 근거**: N  
**정답 청크**: `src/ctxd/config.py::clear_api_key`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/config.py::save_config`
2. `src/ctxd/secure_store.py::get_credentials_path`
3. `src/ctxd/config.py::load_config`
4. `src/ctxd/secure_store.py::save_secret_bundle`
5. `src/ctxd/config.py::get_config_path`

**정답 청크 순위: miss**

### 답변

## 설정과 자격증명을 별도 파일로 나눈 이유

제공된 코드에서 읽을 수 있는 근거는 크게 두 가지입니다.

---

### 1. 보안 민감도가 다르다

`src/ctxd/config.py`의 `save_config` 함수와 `src/ctxd/secure_store.py`의 `save_secret_bundle` 함수 모두 파일 저장 후 권한을 `0o600`(소유자만 읽기/쓰기 가능)으로 설정하긴 합니다.

그러나 파일 자체의 **역할**이 다릅니다.

- `config.json` — 일반 설정값을 담습니다. (`load_config`가 파싱 오류 시 빈 딕셔너리를 반환하는 것에서 보듯, 없어도 동작이 계속됩니다.)
- `credentials.json` — "시크릿 번들(secret bundle)"이라고 명시된 민감한 자격증명을 담습니다. 파일 이름 자체가 `secure_store.py`에 위치해 있어, 보안 저장소로서 별도 모듈로 격리되어 있습니다.

파일을 분리함으로써, 설정 파일은 공유하거나 버전 관리에 포함시키더라도 자격증명 파일은 별도로 엄격하게 관리할 수 있게 됩니다.

---

### 2. 경로를 독립적으로 제어할 수 있다

`src/ctxd/secure_store.py`의 `get_credentials_path` 함수를 보면:

```python
def get_credentials_path() -> Path:
    configured = os.getenv("CTXD_CREDENTIALS_PATH")  # 자격증명 전용 환경변수
    if configured:
        return Path(configured).expanduser()

    config_path = os.getenv("CTXD_CONFIG_PATH")
    if config_path:
        return Path(config_path).expanduser().parent / "credentials.json"

    return DEFAULT_CREDENTIALS_PATH
```

자격증명 파일은 `CTXD_CREDENTIALS_PATH`라는 **전용 환경변수**로 경로를 따로 지정할 수 있습니다. 설정 파일(`CTXD_CONFIG_PATH`, `src/ctxd/config.py`의 `get_config_path`)과 완전히 독립적입니다.

이 구조에서 보면, 예를 들어 설정 파일은 프로젝트 디렉터리에 두고 자격증명 파일은 보안이 강화된 별도 디렉터리(예: 비밀 관리 시스템이 마운트하는 경로)에 두는 운영 방식을 지원하려는 의도로 볼 수 있습니다.

---

### 요약

| 구분 | 설정 (`config.json`) | 자격증명 (`credentials.json`) |
|---|---|---|
| 파일 | `src/ctxd/config.py` | `src/ctxd/secure_store.py` |
| 경로 제어 환경변수 | `CTXD_CONFIG_PATH` | `CTXD_CREDENTIALS_PATH` (별도) |
| 없을 때 동작 | 빈 딕셔너리로 계속 동작 | 별도 처리 (코드에 명시 안 됨) |
| 분리 이유 | 민감도 차이 + 경로 독립 제어 | ← 동일 |

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: in_index=N. 만점. CTXD_CREDENTIALS_PATH 전용 환경변수라는 코드 근거를 찾아냈다. 컨트롤의 일반론과 질적으로 다름.

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
3. `src/ctxd/cli.py::_build_parser`
4. `src/ctxd/client.py::Client.fetch_document`
5. `src/ctxd/cli.py::_handle_logout`

**정답 청크 순위: 1**

### 답변

## `id`와 `document_uid`를 둘 다 받아들이는 이유

`src/ctxd/models.py`의 `SearchItem` 클래스를 보면:

```python
id: str = Field(validation_alias=AliasChoices("id", "document_uid"))
```

`validation_alias=AliasChoices(...)` 는 Pydantic에서 "이 필드를 채울 때 여러 이름 중 하나를 사용할 수 있다"는 설정입니다. 즉, API 응답 데이터에 `id`라는 키가 오든, `document_uid`라는 키가 오든 모두 `SearchItem.id` 필드로 받아들입니다.

### 왜 이렇게 했는가?

`src/ctxd/cli.py`의 `_build_parser` 함수를 보면, `fetch` 명령어의 인자 이름이 `document_uid`로 정의되어 있고:

```python
fetch_parser.add_argument("document_uid", help="Document UID returned by search.")
```

그 설명에도 **"search가 반환한 document UID"** 라고 명시되어 있습니다. 즉, 검색 결과(`SearchItem`)에서 얻은 식별자를 그대로 `fetch` 명령어에 넘겨 쓰는 흐름입니다.

이로 보아, **서버 API가 검색 결과를 줄 때 `id`라는 키를 쓰는 경우도 있고 `document_uid`라는 키를 쓰는 경우도 있는 상황**에서, 어느 쪽으로 오더라도 `SearchItem.id`로 일관되게 받아서 사용자에게 노출하기 위해 두 별칭을 모두 허용한 것으로 보입니다.

- `text` 필드에도 동일하게 `AliasChoices("text", "snippet")`이 적용된 것을 보면, 이 코드베이스는 **API 응답의 필드명이 버전이나 엔드포인트에 따라 다를 수 있는 상황**을 의도적으로 수용하는 설계를 채택하고 있습니다.

정리하면, API 응답에서 같은 개념(문서 식별자)을 `id` 또는 `document_uid`로 부를 수 있기 때문에, 둘 다 허용해서 `SearchItem.id` 하나로 통일해서 다루기 위한 것입니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: in_index=N. 만점. AliasChoices를 짚고 text/snippet까지 확장. 추정임을 밝히고 근거 제시.

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
4. `src/ctxd/cli.py::_build_parser`
5. `src/ctxd/cli.py::_handle_login`

**정답 청크 순위: miss**

### 답변

## `ctxd login`으로 입력한 API 키의 저장 경로

### 전체 흐름 요약

```
ctxd login
  └─ _handle_login()        (cli.py, 183~198행)
       ├─ _resolve_login_api_key()   (cli.py, 227~243행)
       │    └─ _prompt_api_key()     (사용자에게 직접 입력받음)
       └─ save_api_key(api_key)      (저장 함수 호출)
```

---

### 단계별 설명

#### 1단계: `_handle_login()` — 진입점
`cli.py` 183~198행의 `_handle_login()`이 `login` 명령의 핵심 처리 함수입니다.

#### 2단계: `_resolve_login_api_key()` — API 키 확보
`cli.py` 227~243행의 `_resolve_login_api_key()`에서 API 키를 아래 **우선순위 순서**로 가져옵니다:

1. 환경 변수 `CTXD_API_KEY` 확인
2. 이미 저장된 키(`resolve_api_key()`) 확인
3. 위 둘 다 없으면 `_prompt_api_key()`로 **사용자에게 직접 입력** 요청

이 함수는 키와 함께 `should_save`(새로 입력받았는지 여부)를 함께 반환합니다.

> 환경 변수나 저장된 키로 해결된 경우 `should_save = False`이고, 사용자가 직접 입력한 경우에만 `should_save = True`가 됩니다.

#### 3단계: 인증 검증
`_handle_login()`은 저장 전에 `Client(api_key=api_key).get_profile()`을 호출해서 입력된 API 키가 실제로 유효한지 확인합니다.

#### 4단계: `save_api_key()` — 저장
검증이 통과되고 `should_save`가 `True`인 경우(= 사용자가 새로 입력한 경우)에만 `save_api_key(api_key)`를 호출해 키를 저장합니다.

---

### 저장 위치

`save_api_key()`가 **어느 파일/경로에 저장하는지**는 제공된 코드 조각에 해당 함수의 구현이 포함되어 있지 않아 알 수 없습니다. 다만 `_handle_logout()`(`cli.py` 201~205행)에서 `clear_api_key()`가 저장된 키를 삭제하는 것으로 보아, 로컬 어딘가에 파일 형태로 영속 저장되는 구조임을 알 수 있습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): A
- 메모: 정답 청크 miss(config.py::save_api_key). 흐름 3단계는 정확하나 최종 저장 파일명(credentials.json)을 대지 못해 2점 기준 미달. 저장 함수 본문이 컨텍스트에 없다고 정직하게 밝힘.

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
4. `src/ctxd/async_client.py::AsyncClient.base_url`
5. `src/ctxd/secure_store.py::load_secret_bundle`

**정답 청크 순위: miss**

### 답변

## `Client.search()` 호출 경로

### 전체 흐름 요약

```
Client.search()
  → Client._run(...)          # 동기→비동기 변환
    → AsyncClient.search()    # 비동기 로직 시작
      → AsyncClient.call_tool("search", {...})  # 실제 HTTP 요청
        → (HTTP 응답)
      → SearchResult.model_validate(payload)   # 응답 파싱
```

---

### 단계별 설명

#### 1단계 — `Client.search()` (src/ctxd/client.py, 35–36행)

```python
def search(self, query: str) -> SearchResult:
    return self._run(self._async_client.search(query))
```

`Client`는 **동기(synchronous) 래퍼** 역할을 합니다.  
내부에 `_async_client`(AsyncClient 인스턴스)를 갖고 있으며,  
`_run()`을 통해 비동기 코루틴을 동기 방식으로 실행합니다.

---

#### 2단계 — `AsyncClient.search()` (src/ctxd/async_client.py, 40–42행)

```python
async def search(self, query: str) -> SearchResult:
    payload = await self.call_tool("search", {"query": query})
    return SearchResult.model_validate(payload)
```

비동기 로직의 핵심입니다.  
`call_tool("search", {"query": query})`를 호출하여 HTTP 요청을 보내고, 돌아온 응답을 `SearchResult.model_validate()`로 검증하여 반환합니다.

---

#### 3단계 — `AsyncClient.call_tool()` (실제 HTTP 요청 발생 지점)

`call_tool`이 HTTP 요청을 직접 수행하는 메서드입니다.  
`"search"`라는 도구 이름과 `{"query": query}` 파라미터를 전달받아 실제 네트워크 요청을 만들어 보냅니다.  
(내부 구현 코드는 제공된 코드 조각에 포함되어 있지 않습니다.)

---

### 정리

| 단계 | 파일 | 역할 |
|------|------|------|
| `Client.search()` | src/ctxd/client.py | 동기 진입점, `_run()`으로 비동기 실행 |
| `AsyncClient.search()` | src/ctxd/async_client.py | 비동기 로직, `call_tool` 호출 |
| `AsyncClient.call_tool()` | src/ctxd/async_client.py | 실제 HTTP 요청 발송 |
| `SearchResult.model_validate()` | (Pydantic 모델) | HTTP 응답을 구조화된 객체로 변환 |

`call_tool()` 내부의 구체적인 HTTP 라이브러리 사용 방식은 제공된 코드에 없어 확인할 수 없습니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 miss(Client._run)였으나 Client.search가 2등으로 들어와 _run 호출이 본문에 보였다. 경로 전체 정확.

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
3. `src/ctxd/config.py::save_api_key`
4. `src/ctxd/cli.py::_prompt_api_key`
5. `src/ctxd/config.py::clear_api_key`

**정답 청크 순위: 1**

### 답변

## API 키 탐색 순서

API 키를 찾는 함수는 두 가지가 있으며, 용도에 따라 순서가 약간 다릅니다.

---

### 1. 일반 API 호출 시 — `resolve_api_key` (`src/ctxd/config.py`, 24–41행)

| 순서 | 출처 | 설명 |
|------|------|------|
| 1 | **함수 인자** (`api_key` 파라미터) | 직접 전달된 값 |
| 2 | **환경 변수** `CTXD_API_KEY` | OS 환경에 설정된 값 |
| 3 | **저장된 시크릿** (`load_secret_bundle`) | `save_api_key`로 저장한 값 |

각 단계에서 값이 존재하고 공백이 아니면 즉시 반환하고, 끝까지 없으면 `None`을 반환합니다.

---

### 2. 로그인 명령 시 — `_resolve_login_api_key` (`src/ctxd/cli.py`, 227–243행)

| 순서 | 출처 | 설명 |
|------|------|------|
| 1 | **환경 변수** `CTXD_API_KEY` | OS 환경에 설정된 값 |
| 2 | **저장된 시크릿** (`resolve_api_key` 호출) | `save_api_key`로 저장한 값 |
| 3 | **사용자 직접 입력** (`_prompt_api_key`) | 터미널에서 `getpass`로 입력 |

1, 2번에서 찾으면 두 번째 반환값이 `False`(새로 입력되지 않음)이고, 3번에서 찾으면 `True`(새로 입력됨)를 함께 반환합니다. 이 플래그는 새로 입력된 키를 저장할지 여부를 판단하는 데 쓰이는 것으로 보입니다.

---

### 두 함수의 차이점 요약

- `resolve_api_key`는 **코드에서 직접 넘긴 인자**를 최우선으로 봅니다.
- `_resolve_login_api_key`는 인자 방식은 없는 대신, 마지막 수단으로 **터미널 입력**을 받습니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 1등. 우선순위 3단계 정확. CLI 전용 함수와의 차이까지 구분해 설명.

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
3. `src/ctxd/cli.py::_prompt_api_key`
4. `src/ctxd/cli.py::_handle_logout`
5. `src/ctxd/cli.py::_quote_shell_stripped_text_token`

**정답 청크 순위: 1**

### 답변

## ctxd CLI 명령어 목록

`src/ctxd/cli.py`의 `_build_parser` 함수(50–154행)에 정의된 명령어들입니다.

---

### 1. `ctxd login`
API 키를 입력받아 저장합니다. 이후 CLI와 SDK 호출에 사용됩니다.

### 2. `ctxd logout`
이 기기에 저장된 API 키를 삭제합니다.

### 3. `ctxd status`
현재 인증(API 키)이 설정되어 있는지 확인합니다. 환경 변수 또는 저장된 자격증명을 확인합니다.

### 4. `ctxd install-app`
Slack, Google Drive, GitHub, Google Calendar 등 외부 앱을 연결하는 설치 페이지를 엽니다.
- **옵션**: `--no-browser` — 브라우저를 열지 않고 URL만 출력합니다.

### 5. `ctxd search <QUERY>`
ctxd DSL(검색 문법)로 앱 콘텐츠를 검색하고 결과를 JSON으로 출력합니다.
- **인자**: 검색어 (하나 이상)
- **예시**: `ctxd search text:deployment application:slack`

### 6. `ctxd fetch <document_uid>`
검색 결과에서 얻은 문서 UID로 특정 문서 하나를 가져옵니다.
- **인자**: `document_uid` — 가져올 문서의 UID
- **옵션**: `--json` — 전체 응답을 JSON 형식으로 출력합니다.

### 7. `ctxd profile`
인증된 사용자의 연결된 앱 통합 목록과 인덱싱된 파일 트리를 보여줍니다.
- **옵션**: `--json` — 프로필 응답을 JSON 형식으로 출력합니다.

---

### 공통 옵션
- `--version` — 설치된 ctxd 버전을 출력하고 종료합니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 1등. 명령어 7개와 옵션까지 전부.

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
4. `src/ctxd/secure_store.py::load_secret_bundle`
5. `src/ctxd/config.py::_resolve_base_url_from_config`

**정답 청크 순위: miss**

### 답변

## 질문에 대한 답변

제공된 코드만으로는 **실제 요청 URL이 정확히 무엇인지 알 수 없습니다.**

그 이유를 설명드리겠습니다.

---

### 확인된 내용

`src/ctxd/config.py`의 `resolve_base_url` 함수를 보면, `https://ctxd.example.com`을 인자로 주면 그대로 `https://ctxd.example.com`이 `base_url`로 저장됩니다.

```python
def resolve_base_url(base_url: str | None = None) -> str:
    if base_url and base_url.strip():
        return base_url.strip()  # ← 공백만 제거하고 그대로 반환
    ...
```

즉, `base_url` 값 자체에는 별도의 변환이 없습니다.

---

### 알 수 없는 부분

실제 HTTP 요청을 보낼 때 **`base_url`에 어떤 경로(path)가 붙는지**는 제공된 코드에 나타나 있지 않습니다.

- `src/ctxd/async_client.py`의 `AsyncClient`가 `base_url`을 어떻게 사용해서 요청을 구성하는지 (예: `https://ctxd.example.com/api/v1/...` 같은 경로 조합 로직)
- 각 API 엔드포인트 경로가 무엇인지

이 부분은 제공된 코드 조각에 포함되어 있지 않아 확인이 불가능합니다. `AsyncClient` 내부에서 실제 요청을 보내는 메서드(예: `httpx`, `aiohttp` 등의 호출 코드)가 있어야 답할 수 있습니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: /mcp 정규화를 말하지 못함. 정답 청크(_normalize_base_url) miss. resolve_base_url만 보고 '변환 없음'이라 답했다. in_index=Y인데 기권했으므로 0점. 검색 실패가 답변 실패로 직결된 대표 사례.

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
4. `src/ctxd/async_client.py::AsyncClient.base_url`
5. `src/ctxd/secure_store.py::save_secret_bundle`

**정답 청크 순위: 5**

### 답변

## 결론: 아니요, base_url마다 따로 관리되지 않습니다.

---

### 근거

`src/ctxd/secure_store.py`의 `save_secret_bundle` 함수를 보면:

```python
def save_secret_bundle(
    bundle: dict[str, Any], *, base_url: str, client_id: str | None
) -> None:
    del base_url, client_id          # ← 파라미터를 즉시 삭제(무시)
    path = get_credentials_path()    # ← 항상 동일한 단일 경로 사용
    ...
    os.replace(tmp_path, path)       # ← 그 경로에 덮어씀
```

`base_url`과 `client_id`를 파라미터로 받기는 하지만, 함수 첫 줄에서 `del base_url, client_id`로 즉시 버립니다. 실제 저장 경로는 `get_credentials_path()`가 반환하는 **하나의 고정된 경로**이며, base_url에 따라 경로가 달라지지 않습니다.

---

### 어떤 일이 일어나는가

`src/ctxd/config.py`의 `save_api_key` 함수:

```python
def save_api_key(api_key: str, *, base_url: str | None = None) -> Path:
    resolved_base_url = resolve_base_url(base_url)
    config = load_config()
    config["base_url"] = resolved_base_url   # 설정 파일엔 base_url 기록
    save_secret_bundle(
        {"api_key": api_key.strip()},
        base_url=resolved_base_url,           # 전달되지만 실제론 무시됨
        client_id=None,
    )
```

- **API 키 자체**는 base_url과 무관하게 단일 파일에 저장됩니다. 다른 base_url로 키를 저장하면 이전 키는 **덮어써집니다**.
- 반면 **어떤 서버를 쓸지**(base_url)는 별도의 설정 파일(`config`)에 기록됩니다.

---

### 요약

| 항목 | 동작 |
|------|------|
| API 키 저장 위치 | base_url에 관계없이 **단일 파일** |
| base_url별 분리 | ❌ 지원 안 됨 |
| base_url 정보 | 설정 파일에 **별도로** 기록됨 |

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 정답 청크 5등. del base_url, client_id를 짚어 정확히 '아니오'. 관례로 유추하면 반드시 틀리는 문항인데 코드 근거로 맞혔다. 검색 기여가 가장 뚜렷한 문항.

---

## 집계

### 축 1 — 검색

| 지표 | 값 |
|---|---|
| Hit@1 | 5/15 (33.3%) |
| Hit@5 | 8/15 (53.3%) |
| MRR | 0.44 |

순위 분포: 1등 5개(Q02/Q06/Q09/Q12/Q13), 2등 1개(Q04), 5등 2개(Q03/Q15), miss 7개

### 축 2 — 답변 품질

| 유형 | 본 측정 | 컨트롤 | 차이 | 만점 |
|---|---|---|---|---|
| 개념 (Q01~Q03) | 5 | 0 | +5 | 6 |
| 식별자 (Q04~Q06) | 3 | 1 | +2 | 6 |
| 왜 (Q07~Q09) | 3 | 3 | 0 | 3 |
| 관계 (Q10~Q12) | 5 | 0 | +5 | 6 |
| 사실 (Q13~Q15) | 4 | 0 | +4 | 6 |
| **합계** | **20** | **4** | **+16** | **27** |

- 환각(H): 0건
- 기권(A): 3건 (Q05, Q10, Q14)

### 발견 1 — 검색 실패가 답변 실패로 직결되지 않는다

정답 청크를 놓친 7문항 중 Q01(2점)과 Q11(2점)은 만점을 받았다.
top_k=5가 완충 역할을 해, 정답 청크가 아니어도 인접 청크가 같은 결론에 이르게 했다.
answer() 독스트링의 "검색 1위가 정답이 아니어도 답변은 정확할 수 있다"가 외부 레포에서 실증되었다.

역으로 검색 성공이 답변 성공을 보장하지도 않는다.
Q04는 정답 청크가 2등에 있었으나, 1등으로 들어온 CLI 전용 함수
(_resolve_login_api_key)를 SDK 함수로 혼동해 우선순위를 틀렸다.
유사한 청크가 섞이면 정답 청크가 상위에 있어도 답이 오염된다.

### 발견 2 — 실패는 청크 경계에서 발생했다

Q02, Q05, Q14의 실패 원인이 모두 동일하다.
답이 AsyncClient.call_tool 본문에 있는데 그 청크가 top_k에 들지 못했다.
세 답변 모두 "call_tool 구현이 제공되지 않았다"고 스스로 지목했다.

이는 검색 알고리즘의 문제가 아니라 청킹 단위의 문제다.
call_tool은 HTTP 라이브러리, 요청 형식, 응답 파싱을 모두 담고 있어
여러 질문의 정답지 역할을 하는데, 청크 하나로 묶여 있어 함께 실패한다.

### 발견 3 — imports 주입은 청크가 검색되어야만 작동한다

Q05(HTTP 라이브러리)에서 httpx를 말하지 못했다.
Chunk.imports는 청크에 부착된 정보이므로, 그 청크가 검색되지 않으면 도달하지 못한다.
imports가 요약 품질을 높이는 것과, 질의 시점에 라이브러리명을 답하는 것은 별개의 문제다.
파일 수준(L1) 또는 레포 수준(L0) 요약에 의존성 정보를 올려야 해결된다.

### 발견 4 — "왜" 유형은 점수가 아니라 문장의 질에서 갈렸다

예상대로 점수 차이는 0이다(3 대 3). 그러나 답변의 성격이 완전히 다르다.

- 컨트롤: "openai, anthropic SDK가 이 패턴을 쓴다" — 일반론. 이 레포의 심볼 없음
- 본 측정: "Client.call_tool이 self._run(self._async_client.call_tool(...))을 호출한다" — 실제 코드 인용

Q08이 특히 명확하다. 컨트롤은 "보안상 분리하는 관행"이라는 일반론에 머물렀으나,
본 측정은 CTXD_CREDENTIALS_PATH라는 자격증명 전용 환경변수를 찾아내
경로를 독립 제어할 수 있다는 구조적 근거를 제시했다.

실험 B의 결론("버린 대안은 복원 불가")은 유지된다. 세 문항 모두 설계 의도 자체는
말하지 못했다. 다만 코드에 남은 구조로부터 도달 가능한 범위는 컨트롤보다 훨씬 넓었다.

### 발견 5 — 환각 0건

15문항 전부에서 없는 심볼을 지어내지 않았다.
답할 수 없을 때는 무엇이 없어서 답할 수 없는지를 지목했다(Q02, Q05, Q10, Q14).
프롬프트 개정(금지 규칙에 허용 규칙을 짝지음)이 과잉 유보로 기울지 않으면서
환각도 막았음을 확인했다.

### 한계

- 채점자가 1인이므로 채점자 간 일치도를 측정할 수 없다.
- __init__.py는 함수/클래스가 없어 청킹되지 않아 인덱스에 없다.
  패키지 공개 API 정보가 검색 대상에서 빠졌으며, Q01에 영향을 주었을 수 있다.
- 프롬프트를 개정한 뒤 측정했으므로 실험 B와 직접 비교할 수 없다.
- 문항 15개는 통계적 유의성을 논하기에 적은 표본이다.
