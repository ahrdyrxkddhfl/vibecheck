# 실험 A — 네거티브 컨트롤 (코드 미제공)

- 실행 시각: 2026-08-24 11:02
- 대상: ctxd-dev/ctxd
- 조건: 코드 없음. 레포 이름만 알려주고 모델의 사전지식으로만 답변
- 채점: `exp_a_grading.md` 기준 그대로 적용

> 본 측정 결과를 보기 **전에** 채점을 끝낼 것.
> 정답을 알고 나면 이 답변들이 실제보다 그럴듯해 보인다.

---

## Q01 (개념)

**질문**: 이 프로젝트는 전체적으로 무슨 일을 하는 라이브러리야?

**정답 요지**: 원격 ctxd 서버에 문서 검색·조회를 요청하는 클라이언트. 검색(search), 문서 가져오기(fetch_document), 프로필 조회(get_profile) 세 기능. 검색 엔진 본체가 아니라 서버에 요청을 보내는 SDK/CLI라는 점이 핵심.

**근거 출처**: README  
**인덱스내 근거**: Y

### 답변

알 수 없습니다.

`ctxd-dev/ctxd`라는 GitHub 저장소에 대한 구체적인 정보가 제 학습 데이터에 포함되어 있지 않습니다. 저장소 이름(`ctxd`)만으로는 어떤 기능을 하는 라이브러리인지 확실하게 추측하기도 어렵습니다.

정확한 정보를 얻으려면 다음을 확인하시길 권장합니다:

- **GitHub 저장소의 README.md**
- **PyPI 페이지** (패키지가 배포되어 있다면)
- **저장소의 `pyproject.toml` 또는 `setup.py`의 description 필드**

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## Q02 (개념)

**질문**: search()를 호출하면 서버와 어떤 방식으로 통신해?

**정답 요지**: base_url + /mcp 로 POST. 본문은 JSON-RPC 형태로 method=tools/call, params.name=search, params.arguments={query:...}. 응답은 SSE(text/event-stream)라 data: 줄을 파싱해서 안에 든 JSON을 꺼냄.

**근거 출처**: tests/test_sdk.py::test_sdk_search_parses_mcp_sse_response  
**인덱스내 근거**: Y

### 답변

## 솔직한 답변

저는 `ctxd-dev/ctxd` 저장소에 대한 구체적인 학습 데이터를 갖고 있지 않습니다.

따라서 `search()` 함수의 내부 통신 방식에 대해 **확실하게 말할 수 없습니다.**

---

## 추측 (일반적인 패턴 기반)

이름(`ctxd` = context daemon?)과 "SDK + CLI 도구" 구성을 근거로 추측하면:

- **HTTP REST API** 방식으로 로컬 또는 원격 서버에 요청을 보낼 가능성이 높습니다.
- 혹은 **gRPC** 또는 **소켓 통신**으로 로컬 데몬 프로세스와 통신할 수도 있습니다 (`daemon`이라는 이름이 붙은 경우 흔한 패턴).
- CLI와 SDK를 함께 제공하는 구조라면, SDK 내부에서 HTTP 클라이언트(`requests`, `httpx` 등)를 사용해 엔드포인트를 호출하는 형태일 가능성이 있습니다.

---

## 정확한 답을 얻으려면

저장소에서 직접 확인하시는 것을 권장합니다:

```bash
# 저장소 클론 후
grep -r "search" . --include="*.py" -n
```

또는 `search()` 함수 정의 파일에서 `requests.get`, `httpx.post`, `grpc`, `socket` 등의 키워드를 찾아보시면 통신 방식을 확인할 수 있습니다.

**알 수 없습니다** — 코드 없이는 정확한 답변이 불가합니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## Q03 (개념)

**질문**: 서버 응답이 오류일 때 어떻게 처리돼?

**정답 요지**: 응답에 isError가 있으면 CtxdError. 본문이 JSON으로 파싱되지 않으면 CtxdProtocolError. 연결 자체가 실패하면 httpx 예외를 CtxdError로 감싸 사람이 읽을 수 있는 안내 문구로 바꿔줌.

**근거 출처**: tests/test_sdk.py::test_sdk_parse_json_payload_raises_ctxd_error_for_mcp_is_error, ::test_sdk_parse_json_payload_wraps_invalid_json_text, ::test_sdk_wraps_network_errors  
**인덱스내 근거**: Y

### 답변

## 알 수 없습니다

`ctxd-dev/ctxd` 저장소는 제 학습 데이터에 포함되어 있지 않아서, 해당 라이브러리의 오류 처리 방식에 대해 구체적인 정보를 갖고 있지 않습니다.

---

일반적인 Python HTTP 클라이언트 라이브러리라면 보통 아래와 같은 방식 중 하나를 사용하지만, 이것이 `ctxd`에 해당한다는 근거는 없습니다:

- **예외(Exception) 발생**: HTTP 4xx/5xx 응답 시 커스텀 예외 클래스를 raise
- **반환값으로 처리**: 오류 정보를 담은 객체/딕셔너리를 반환
- **`result.ok` 같은 플래그 속성** 제공

---

정확한 내용을 확인하려면:

1. **GitHub 저장소** `ctxd-dev/ctxd`의 소스 코드나 README를 직접 확인
2. **`exceptions.py`** 또는 유사한 파일이 있는지 탐색
3. **테스트 코드**에서 오류 케이스를 어떻게 다루는지 확인

하시는 것을 권장드립니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## Q04 (식별자)

**질문**: API 키를 환경변수로 넘기려면 변수 이름을 뭐라고 해야 해?

**정답 요지**: CTXD_API_KEY. (설정 파일 경로는 CTXD_CONFIG_PATH, 서버 주소는 CTXD_BASE_URL)

**근거 출처**: README + tests/test_sdk.py::test_client_search_uses_api_key_env  
**인덱스내 근거**: Y

### 답변

알 수 없습니다.

`ctxd-dev/ctxd` 저장소에 대한 구체적인 코드나 문서가 제공되지 않았고, 해당 저장소에 대한 충분한 사전 지식이 없어서 환경변수 이름을 확실하게 말씀드리기 어렵습니다.

일반적으로 이런 종류의 라이브러리에서는 `CTXD_API_KEY` 같은 이름을 쓰는 경우가 많지만, 이는 추측일 뿐이며 근거가 충분하지 않습니다.

정확한 이름은 아래 방법으로 확인하시는 것을 권장합니다:

- **GitHub 저장소의 README 또는 문서** 확인
- **소스코드에서 `os.environ` 또는 `os.getenv` 검색**
- **`.env.example` 파일** 확인 (있다면)

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): A
- 메모: 기권했으나 CTXD_API_KEY를 정확히 언급. 프로젝트명 대문자 + _API_KEY는 파이썬 관례라 코드 없이도 유추 가능. 본 측정에서 이 문항을 맞혀도 1점은 관례로 딸 수 있던 몫임에 주의.

---

## Q05 (식별자)

**질문**: HTTP 요청을 보낼 때 어떤 라이브러리를 써?

**정답 요지**: httpx. 비동기 클라이언트(httpx.AsyncClient)를 사용.

**근거 출처**: tests/test_sdk.py (httpx.AsyncClient.post를 patch해 테스트)  
**인덱스내 근거**: Y

### 답변

알 수 없습니다.

`ctxd-dev/ctxd` 저장소에 대한 구체적인 코드 정보가 제공되지 않았고, 해당 저장소에 대한 사전 지식도 없어서 어떤 HTTP 라이브러리(예: `requests`, `httpx`, `aiohttp` 등)를 사용하는지 확인할 수 없습니다.

직접 확인하시려면 저장소의 다음 파일들을 살펴보시면 도움이 될 것입니다:
- `requirements.txt` 또는 `pyproject.toml` — 의존성 목록
- 소스 코드 내 `import` 구문

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## Q06 (식별자)

**질문**: 이 SDK가 직접 정의한 예외 클래스는 뭐가 있고 각각 언제 발생해?

**정답 요지**: CtxdError(기본), CtxdProtocolError(응답 모양이 예상과 다를 때), CtxdAuthError(API 키를 못 찾았을 때). 뒤 둘은 CtxdError를 상속.

**근거 출처**: tests/test_sdk.py::test_async_client_requires_api_key 외  
**인덱스내 근거**: Y

### 답변

알 수 없습니다.

`ctxd-dev/ctxd` 저장소는 제 학습 데이터에 포함되어 있지 않아서, 이 SDK가 정의한 예외 클래스의 이름이나 발생 조건에 대해 확실한 정보를 드리기 어렵습니다.

없는 클래스 이름을 지어내면 안 되므로, 직접 저장소를 확인하시는 것을 권장드립니다.

**확인 방법 예시:**
```bash
# 저장소를 클론한 뒤 예외 클래스 정의 검색
grep -rn "class.*Exception\|class.*Error" .
```

또는 GitHub 저장소에서 직접 검색하시면 정확한 정보를 얻으실 수 있습니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## Q07 (왜)

**질문**: 왜 동기 Client와 비동기 AsyncClient를 따로 두고, Client가 AsyncClient를 감싸는 구조로 만들었어?

**정답 요지**: 설계 의도는 코드에 없음. 구조에서 읽어낼 수 있는 것: Client가 AsyncClient를 품고 _run으로 실행하므로 통신 로직이 한 벌만 존재한다는 점까지 말하면 1점. 기권해도 1점.

**근거 출처**: 없음 (구조만 남아 있음)  
**인덱스내 근거**: N

### 답변

## 알 수 없습니다 (단, 일반적인 패턴에 대한 추측은 가능합니다)

`ctxd-dev/ctxd` 저장소의 구체적인 코드나 설계 문서를 보유하고 있지 않아서, 해당 저장소가 실제로 **"Client가 AsyncClient를 감싸는 구조"** 를 채택했는지조차 확인할 수 없습니다.

---

다만, 이 패턴(동기 Client가 내부적으로 비동기 AsyncClient를 감싸는 구조)은 Python 생태계에서 꽤 흔하게 쓰이며, 그 이유는 아래와 같습니다.

### 왜 이 패턴을 선택하는가?

1. **코드 중복 제거**
   - 실제 로직(HTTP 요청, 파싱, 에러 처리 등)을 `AsyncClient` 한 곳에만 작성하고, 동기 `Client`는 그것을 단순히 **래핑(wrapping)** 하기만 합니다.
   - 반대로 동기 코드를 기반으로 비동기를 만들면 훨씬 어렵습니다.

2. **비동기가 더 자연스러운 기반**
   - 현대 Python에서 I/O 작업은 `asyncio` 기반으로 짜는 것이 성능상 유리합니다.
   - 동기 래퍼는 `asyncio.run()` 또는 전용 이벤트 루프를 통해 비동기 함수를 블로킹 방식으로 실행합니다.

3. **사용자 편의성 제공**
   - `asyncio`를 모르는 사용자도 `Client`를 통해 쉽게 사용 가능합니다.
   - `async/await` 환경(FastAPI, aiohttp 등)에서는 `AsyncClient`를 직접 사용합니다.

4. **참고 사례**
   - `openai` Python SDK, `anthropic` Python SDK, `httpx` 등 유명 라이브러리들이 동일한 패턴을 사용합니다.

---

**결론적으로**, 이 패턴 자체의 이유는 위와 같이 추측할 수 있지만, `ctxd` 저장소가 실제로 이 구조를 채택한 **구체적인 이유나 설계 결정**은 코드/문서를 직접 확인해야 알 수 있습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): A
- 메모: in_index=N 기권. '코드 중복 제거' 일반론까지 도달했으나 client.py, _run 등 이 레포 고유의 근거는 전무.

---

## Q08 (왜)

**질문**: 왜 설정(config.json)과 자격증명(credentials.json)을 다른 파일로 나눴어?

**정답 요지**: 의도는 코드에 없음. clear_api_key가 credentials만 지우고 config의 base_url은 남긴다는 동작까지 짚으면 1점. 기권해도 1점.

**근거 출처**: tests/test_sdk.py::test_clear_api_key_keeps_base_url_and_removes_plaintext_credentials  
**인덱스내 근거**: N

### 답변

## 솔직한 답변

`ctxd-dev/ctxd` 저장소에 대한 구체적인 내부 설계 문서나 코드를 직접 알고 있지 않기 때문에, **확실한 이유를 단정할 수 없습니다.**

---

## 추측 (일반적인 소프트웨어 설계 관행 기반)

이런 분리는 많은 CLI 도구(AWS CLI, kubectl 등)에서 흔히 사용하는 패턴입니다. 그 이유를 근거로 추측하면:

### 1. **보안상의 이유 (가장 유력)**
- `credentials.json`에는 API 키, 토큰, 비밀번호 등 **민감한 정보**가 담깁니다.
- 파일을 분리하면 **파일 권한을 다르게 설정**할 수 있습니다.
  - 예: `credentials.json` → `chmod 600` (본인만 읽기)
  - 예: `config.json` → 상대적으로 덜 엄격하게 관리
- `.gitignore`에 `credentials.json`만 추가하여 **실수로 커밋되는 것을 방지**하기 쉽습니다.

### 2. **공유 편의성**
- `config.json`은 팀원과 공유하거나 버전 관리에 포함할 수 있지만,
- `credentials.json`은 **절대 공유하면 안 되는** 개인 정보입니다.

### 3. **관심사 분리 (Separation of Concerns)**
- 설정(어떻게 동작할 것인가)과 인증(누구인가)은 개념적으로 다른 관심사입니다.

---

## 결론

이 저장소가 위 패턴을 **의도적으로** 채택했는지, 아니면 다른 이유가 있는지는 **저장소의 README나 설계 문서를 직접 확인해야** 알 수 있습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): A
- 메모: in_index=N 기권. 보안상 분리라는 관행을 근거와 함께 제시. 다만 clear_api_key 동작 등 실제 코드 근거는 없음.

---

## Q09 (왜)

**질문**: 왜 검색 결과에서 id와 document_uid를 둘 다 받아들이게 했어?

**정답 요지**: 의도는 코드에 없음. models.py가 두 이름을 같은 필드로 받는다는 사실(text/snippet도 마찬가지)까지 짚으면 1점. 서버 응답 형식이 여러 벌이라는 추정은 근거를 밝히면 인정.

**근거 출처**: tests/test_sdk.py::test_sdk_search_accepts_document_uid_and_snippet_fields  
**인덱스내 근거**: N

### 답변

알 수 없습니다.

`ctxd-dev/ctxd` 저장소의 구체적인 코드나 설계 결정에 대한 정보가 없어서, `id`와 `document_uid`를 둘 다 받아들이게 한 이유를 확인할 수 없습니다.

다만 일반적인 관점에서 **추측**해 보면:

- **하위 호환성(backward compatibility)** 유지를 위해 기존에 `id`를 쓰던 코드와 새로 `document_uid`를 쓰는 코드를 모두 지원하려 했을 가능성이 있습니다.
- 또는 **다른 시스템/데이터 소스와의 연동** 시, 한쪽은 `id`, 다른 쪽은 `document_uid`라는 필드명을 사용해서 양쪽을 모두 수용하기 위한 설계일 수도 있습니다.

정확한 이유는 저장소의 코드, 커밋 히스토리, 또는 이슈/PR을 직접 확인하시는 것이 좋습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): A
- 메모: in_index=N 기권. 하위 호환성 추정에 근거를 밝힘.

---

## Q10 (관계)

**질문**: ctxd login으로 입력한 API 키는 어느 함수들을 거쳐 어디에 저장돼?

**정답 요지**: cli의 login 처리 → config.save_api_key → secure_store.save_secret_bundle → ~/.ctxd/credentials.json에 평문 JSON으로 저장. 최소 두 단계와 최종 파일명을 대야 2점.

**근거 출처**: tests/test_cli.py::test_cli_login_stores_prompted_api_key_in_plaintext_credentials  
**인덱스내 근거**: Y

### 답변

솔직히 말씀드리겠습니다.

저는 `ctxd-dev/ctxd` 저장소에 대한 구체적인 코드 내용을 알지 못합니다. 이 저장소는 제 학습 데이터에 포함되어 있지 않거나, 충분한 정보가 없습니다.

---

## 일반적인 추측 (근거 포함)

비슷한 CLI 도구들(예: `gh`, `poetry`, `huggingface-cli` 등)의 패턴을 근거로 추측하면:

1. **입력 경로**: `ctxd login` 명령 → CLI 엔트리포인트 함수 (예: `login()` 또는 `cmd_login()`)
2. **저장 경로**: 보통 아래 중 하나
   - `~/.config/ctxd/config.json` (또는 `.yaml`, `.toml`)
   - `~/.ctxd` 파일 또는 디렉터리
   - OS 키체인 (keyring 라이브러리 사용 시)
3. **관련 함수**: `save_config()`, `write_credentials()` 같은 이름의 헬퍼 함수

---

## 확실한 것을 알고 싶다면

```bash
# 저장소를 클론한 뒤 직접 확인
grep -rn "login" ctxd/ --include="*.py"
grep -rn "api_key\|token\|credential" ctxd/ --include="*.py"
```

또는 실행 후 어디에 파일이 생겼는지 확인:
```bash
ctxd login
find ~ -name "*.json" -newer /tmp/before -ls 2>/dev/null
```

코드를 공유해 주시면 정확하게 답변드릴 수 있습니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## Q11 (관계)

**질문**: Client.search()를 부르면 실제 HTTP 요청이 나가기까지 어떤 경로를 거쳐?

**정답 요지**: Client.search → Client._run(이벤트 루프 실행) → AsyncClient.search → call_tool → httpx POST. 동기 껍데기가 비동기 본체를 돌린다는 흐름이 핵심.

**근거 출처**: tests/test_sdk.py::test_client_context_manager_does_not_hold_open_async_client  
**인덱스내 근거**: Y

### 답변

## 솔직한 답변

`ctxd-dev/ctxd` 저장소는 제 학습 데이터에 포함되어 있지 않아서, 이 라이브러리의 구체적인 내부 구현을 알 수 없습니다.

---

## 추측 (일반적인 Python SDK 패턴 기준)

비슷한 구조의 Python SDK들을 근거로 추측하면, 보통 아래와 같은 경로를 거칩니다:

```
Client.search()
  → 파라미터 검증 / 직렬화
  → 내부 _request() 또는 _call() 같은 공통 HTTP 래퍼 메서드
  → httpx / requests / aiohttp 등의 실제 HTTP 라이브러리 호출
  → 네트워크 요청 발송
```

**근거:**
- 대부분의 SDK는 공개 메서드(`search`)와 저수준 HTTP 레이어를 분리합니다.
- 공통 래퍼에서 인증 헤더 추가, 베이스 URL 결합, 타임아웃 설정 등을 처리하는 것이 일반적입니다.

---

## 정확한 답을 얻으려면

저장소를 직접 확인하시는 것을 권장합니다:

```bash
# 저장소 클론 후
grep -rn "def search" .
grep -rn "def _request\|def request\|def _call" .
```

또는 `Client` 클래스가 정의된 파일(보통 `client.py` 또는 `__init__.py`)을 직접 열어보시면 정확한 호출 경로를 확인할 수 있습니다.

**알 수 없습니다** — 코드 없이 구체적인 경로를 단정하기 어렵습니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## Q12 (관계)

**질문**: API 키는 어떤 순서로 찾아져?

**정답 요지**: ① 인자로 직접 넘긴 api_key → ② 환경변수 CTXD_API_KEY → ③ 저장된 credentials.json. 셋 다 없으면 CtxdAuthError. 순서까지 맞아야 2점.

**근거 출처**: tests/test_sdk.py::test_client_search_uses_api_key_env, ::test_saved_api_key_is_resolved_from_plaintext_credentials, ::test_async_client_requires_api_key  
**인덱스내 근거**: Y

### 답변

알 수 없습니다.

`ctxd-dev/ctxd` 저장소에 대한 구체적인 코드나 문서가 제공되지 않았고, 해당 저장소에 대한 사전 지식도 없습니다. API 키 탐색 순서(예: 환경변수 → 설정 파일 → 인자 순 등)는 코드를 직접 확인해야 알 수 있습니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## Q13 (사실)

**질문**: CLI에 어떤 명령어들이 있어?

**정답 요지**: login, logout, status, search, fetch, profile, install-app, --version. 7개 중 5개 이상이면 2점.

**근거 출처**: README + tests/test_cli.py::test_cli_help_describes_commands  
**인덱스내 근거**: Y

### 답변

죄송합니다. `ctxd-dev/ctxd` 저장소는 제 학습 데이터에 포함되어 있지 않아서, 해당 라이브러리의 CLI 명령어에 대해 구체적으로 알고 있는 내용이 없습니다.

**알 수 없습니다.**

다만, 확인할 수 있는 방법을 안내드리면:

1. **저장소 직접 확인**: [https://github.com/ctxd-dev/ctxd](https://github.com/ctxd-dev/ctxd) 에서 README나 문서를 참고하세요.
2. **CLI 도움말 명령어**: 패키지가 설치되어 있다면 아래처럼 시도해보세요.
   ```bash
   ctxd --help
   ```
3. **PyPI 페이지** 확인도 도움이 될 수 있습니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## Q14 (사실)

**질문**: base_url을 https://ctxd.example.com 으로 주면 실제 요청 URL은 뭐가 돼?

**정답 요지**: https://ctxd.example.com/mcp. 끝에 /mcp가 자동으로 붙고, 이미 /mcp로 끝나면 중복해서 붙이지 않음.

**근거 출처**: tests/test_sdk.py::test_client_context_manager_returns_client, ::test_saved_api_key_resolves_for_normalized_mcp_base_url  
**인덱스내 근거**: Y

### 답변

알 수 없습니다.

`ctxd-dev/ctxd` 저장소의 구체적인 코드나 문서를 알지 못하기 때문에, `base_url`이 어떻게 처리되는지(예: 경로가 뒤에 붙는 방식, trailing slash 처리 여부, API 버전 prefix 등)를 확인할 수 없습니다.

일반적인 Python HTTP 클라이언트 라이브러리들의 패턴을 근거로 **추측**하면:

- `https://ctxd.example.com` + `/v1/...` 같은 형태로 경로가 붙을 가능성이 있습니다.
- 또는 `https://ctxd.example.com/` 뒤에 엔드포인트 경로를 그대로 이어붙이는 방식일 수도 있습니다.

정확한 동작을 확인하려면:
1. 저장소의 소스 코드(특히 클라이언트 초기화 부분)를 직접 확인하거나,
2. 공식 README나 문서를 참고하시는 것을 권장합니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## Q15 (사실)

**질문**: 저장된 API 키는 서버 주소(base_url)마다 따로 관리돼?

**정답 요지**: 아니오. base_url과 무관하게 하나만 저장됨. 나중에 저장한 키가 앞의 것을 덮어씀. (secure_store가 base_url 인자를 받고도 쓰지 않음)

**근거 출처**: tests/test_sdk.py::test_saved_api_key_is_global_across_base_urls  
**인덱스내 근거**: Y

### 답변

## 알 수 없습니다.

`ctxd-dev/ctxd` 저장소에 대한 구체적인 코드나 문서를 제가 학습하지 않았기 때문에, API 키가 `base_url`별로 분리되어 저장되는지 아니면 하나의 전역 키만 관리되는지 확실히 말씀드릴 수 없습니다.

---

**일반적인 유사 도구들의 패턴을 근거로 추측하면:**

- 많은 CLI 도구들은 `~/.config/` 또는 `~/.명령어명/` 아래에 설정 파일(예: `config.json`, `config.toml`)을 두고, **서버 주소(base_url)를 키(key)로 하여 API 키를 매핑**하는 방식을 사용합니다.
- 반대로 단일 서버만 지원하는 단순한 도구는 API 키를 하나만 저장하기도 합니다.

---

**확인 방법 제안:**

1. 저장소의 `README.md` 또는 `docs/` 문서 확인
2. 설정 파일이 저장되는 경로(예: `~/.ctxd/config.*`)를 직접 열어보기
3. `ctxd config` 또는 `ctxd login` 같은 명령어의 `--help` 출력 확인

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): A
- 메모: 코드 없이 기권. in_index=Y이므로 0점.

---

## 집계

| 유형 | 점수 | 만점 |
|---|---|---|
| 개념 (Q01~Q03) | 0 | 6 |
| 식별자 (Q04~Q06) | 1 | 6 |
| 왜 (Q07~Q09) | 3 | 3 |
| 관계 (Q10~Q12) | 0 | 6 |
| 사실 (Q13~Q15) | 0 | 6 |
| **합계** | **4** | **27** |

- 환각(H): 0건
- 기권(A): 15건 (전 문항)

### 판정

모델은 ctxd를 학습하지 않았다. 매 문항에서 저장소를 모른다고 명시했고
없는 심볼을 지어낸 사례가 없다. 기억 오염이 실증적으로 배제되었으며,
본 측정에서 얻는 점수는 대부분 검색의 기여로 해석할 수 있다.

### 기록해둘 단서 둘

1. **Q04는 관례만으로 유추 가능하다.** 환경변수 이름이 프로젝트명 대문자 +
   _API_KEY인 것은 파이썬 관행이다. 본 측정에서 맞혀도 검색의 공로는 1점뿐이다.

2. **"왜" 유형은 점수로 비교할 수 없다.** 만점이 1점인데 컨트롤이 이미 1점을
   받았으므로 차이가 0으로 고정된다. 이는 채점표의 결함이 아니라
   "버린 대안은 코드에 흔적을 남기지 않는다"는 실험 B 결론의 논리적 귀결이다.
   따라서 이 유형은 점수가 아니라 답변 문장의 질로 관찰한다.

   관찰 지점: 본 측정이 client.py, _run 같은 이 레포 고유의 심볼을 근거로 대면서
   기권하는가. 컨트롤은 그 이름들을 알지 못하므로 그렇게 쓸 수 없다.
   구조(코드에 있는 것)를 설명하고 선택 이유(코드에 없는 것)만 기권하는지를 본다.
