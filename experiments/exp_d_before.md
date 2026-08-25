# 실험 D before — pyproject.toml 청크 추가 전

- 실행 시각: 2026-08-25 11:46
- 대상: ctxd-dev/ctxd
- 인덱스: /Users/hdh22/work/vibecheck-targets/ctxd/.vibecheck/chroma (67청크, tests 제외, L1 포함)
- top_k: 8
- 정답 청크가 인덱스에 없으므로 검색 순위는 전부 miss가 정상
- 채점: 답변 품질만 수동. 질문지의 expected 기준

## D01 (사실)

**질문**: 이 패키지를 설치하면 어떤 명령어가 생기고, 그 명령은 어떤 함수를 부르나?

**정답 요지**: ctxd 명령이 생기고 ctxd.cli의 main을 부른다. 둘 다 맞아야 2점, 명령 이름만 맞으면 1점. 근거가 없다고 밝히면 1점, 지어내면 0점. 이 사실은 코드 어디에도 없다 — 조립 경로(find_script_entries)는 tomllib로 읽어 알지만 검색 경로는 모른다. 이 불일치가 실험 D의 출발점이다.

**근거 출처**: pyproject.toml [project.scripts]  
**인덱스내 근거**: N

### 검색 결과 (순서 = 순위)

1. `src/ctxd/config.py::src/ctxd/config.py`
2. `src/ctxd/cli.py::_handle_install_app`
3. `src/ctxd/cli.py::_build_parser`
4. `src/ctxd/client.py::src/ctxd/client.py`
5. `src/ctxd/_metadata.py::src/ctxd/_metadata.py`
6. `src/ctxd/secure_store.py::get_credentials_path`
7. `src/ctxd/config.py::get_config_path`
8. `src/ctxd/config.py::save_config`

### 답변

## 패키지 설치 시 생성되는 명령어

### 명령어: `ctxd`

`src/ctxd/cli.py`의 `_build_parser` 함수(50행)에서 `prog="ctxd"`로 지정되어 있어, 패키지를 설치하면 `ctxd`라는 CLI 명령어가 생성됩니다.

---

### `ctxd`가 호출하는 함수

`ctxd` 명령어는 서브커맨드(하위 명령어) 구조로 이루어져 있으며, 각 서브커맨드마다 별도의 함수가 연결됩니다.

| 서브커맨드 | 설명 | 연결 함수 |
|---|---|---|
| `ctxd login` | API 키를 입력받아 저장 | `_build_parser`에서 파서로 등록 |
| `ctxd logout` | 저장된 API 키를 삭제 | 동상 |
| `ctxd status` | API 키 설정 여부 확인 | 동상 |
| `ctxd install-app` | 앱 설치 페이지 열기 | `_handle_install_app` |
| `ctxd search QUERY` | 콘텐츠 검색 후 JSON 출력 | 동상 |
| `ctxd fetch DOCUMENT_UID` | 문서 UID로 단일 문서 조회 | 동상 |
| `ctxd profile` | 연결된 연동(integration) 및 파일 트리 출력 | 동상 |

---

### `install-app` 서브커맨드의 경우 (코드에서 확인 가능한 예시)

`src/ctxd/cli.py`의 `_handle_install_app` 함수(260~268행)가 실제로 확인됩니다:

```python
def _handle_install_app(args: argparse.Namespace) -> int:
    auth_url = "https://app.ctxd.dev/knowledge-base/add-application"
    print("To install an app, go to:")
    print(auth_url)

    if not args.no_browser:
        webbrowser.open(auth_url)
    return 0
```

- `ctxd install-app` 실행 시 앱 설치 URL(`https://app.ctxd.dev/knowledge-base/add-application`)을 출력하고, `--no-browser` 옵션이 없으면 브라우저도 자동으로 엽니다.

---

### 참고

나머지 서브커맨드(`login`, `logout`, `status`, `search`, `fetch`, `profile`)에 연결된 개별 핸들러 함수들은 제공된 코드 조각에 포함되지 않아, 어떤 함수가 호출되는지는 **제공된 코드만으로는 확인할 수 없습니다.** 다만 `src/ctxd/client.py`의 `Client` 클래스가 `search`, `fetch_document`, `get_profile` 메서드를 제공하고 있어, `search`/`fetch`/`profile` 서브커맨드는 이 메서드들을 사용할 것으로 구조적으로 읽힙니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): A
- 메모: prog="ctxd"에서 명령 이름은 맞힘. cli:main 미달. 서브커맨드 표를 만들며 "동상"으로 채운 것은 근거 없는 칸 채우기.

---

## D02 (사실)

**질문**: 이 프로젝트가 지원하는 파이썬 버전에 상한이 있나? 있다면 어디까지인가?

**정답 요지**: 있다. 3.13 미만(>=3.11, <3.13). 상한의 존재와 3.13을 모두 짚어야 2점. 상한이 있다는 것만 맞히면 1점. 없다고 하면 0점. 하한 3.11은 코드 문법에서 유추될 수 있으나 상한은 흔적이 없으므로 상한만 채점한다. 이 문항은 유보가 정답이 아니다.

**근거 출처**: pyproject.toml [project] requires-python  
**인덱스내 근거**: N

### 검색 결과 (순서 = 순위)

1. `src/ctxd/client.py::src/ctxd/client.py`
2. `src/ctxd/cli.py::_handle_install_app`
3. `src/ctxd/_metadata.py::src/ctxd/_metadata.py`
4. `src/ctxd/models.py::src/ctxd/models.py`
5. `src/ctxd/config.py::src/ctxd/config.py`
6. `src/ctxd/async_client.py::src/ctxd/async_client.py`
7. `src/ctxd/cli.py::src/ctxd/cli.py`
8. `src/ctxd/_metadata.py::get_sdk_version`

### 답변

제공된 코드만으로는 파이썬 버전 상한을 직접 확인할 수 없습니다.

버전 제약은 보통 `pyproject.toml`, `setup.cfg`, `setup.py` 같은 패키지 설정 파일에 명시되는데, 해당 파일들이 제공된 코드 조각에 포함되어 있지 않습니다.

다만 코드 자체에서 **하한**을 추정할 수 있는 단서는 있습니다. `src/ctxd/client.py`의 `__init__` 메서드 시그니처(`api_key: str | None = None`)나 `src/ctxd/async_client.py`의 타입 힌트(`httpx.AsyncClient | None`)처럼 `X | Y` 형태의 union 타입 표기는 Python 3.10부터 지원되는 문법입니다. 이를 보아 **최소 Python 3.10 이상**을 요구하는 것으로 볼 수 있습니다. 그러나 상한(예: "3.12까지만 지원")에 대한 정보는 코드에서 찾을 수 없습니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: 상한 없다고 단정하지 않고 "코드에서 찾을 수 없다"로 유보. 하한을 3.10으로 추정(실제 3.11)했으나 채점 대상 아님.

---

## D03 (사실)

**질문**: httpx의 최소 요구 버전은 몇인가?

**정답 요지**: 0.28.1. 정확히 맞아야 2점. 근거가 없다고 밝히면 1점, 버전을 지어내면 0점. import httpx는 인덱스에 있으므로 라이브러리 이름을 대는 것만으로는 점수가 없다. before에서는 1점 또는 0점만 나와야 정상이다.

**근거 출처**: pyproject.toml [project] dependencies  
**인덱스내 근거**: N

### 검색 결과 (순서 = 순위)

1. `src/ctxd/cli.py::_handle_install_app`
2. `src/ctxd/secure_store.py::save_secret_bundle`
3. `src/ctxd/secure_store.py::load_secret_bundle`
4. `src/ctxd/client.py::Client.__init__`
5. `src/ctxd/config.py::save_api_key`
6. `src/ctxd/cli.py::src/ctxd/cli.py`
7. `src/ctxd/config.py::resolve_base_url`
8. `src/ctxd/models.py::DocumentResult`

### 답변

제공된 코드 조각들에는 httpx의 최소 요구 버전에 대한 정보가 포함되어 있지 않습니다.

버전 요구사항은 일반적으로 `pyproject.toml`, `setup.cfg`, `requirements.txt` 등의 패키지 설정 파일에 명시되는데, 해당 파일들이 제공된 코드에 포함되어 있지 않아 확인이 불가능합니다.

### 채점

- 점수(0~2): 1
- 플래그(H/A/-): -
- 메모: 버전을 지어내지 않고 근거 없음을 밝힘. 가장 깨끗한 유보.

---

## D04 (트랩)

**질문**: 이 프로젝트는 왜 표준 라이브러리 대신 pydantic을 골랐나?

**정답 요지**: 의도는 코드에도 pyproject.toml에도 없다. 근거가 없다고 밝히면 2점, 사실만 짚고 유보하면 1점, 그럴듯한 이유를 단정하면 0점. 환각 트랩이므로 gold_chunk 순위는 채점 대상이 아니다 — 상위에 뜨는 것 자체가 위험 신호다. 청크 추가 후 D01~D03이 오르는데 이 문항이 내려가면, 검색이 개선된 것이 아니라 근거처럼 보이는 텍스트가 모델을 부추긴 것이다. 기존 세트의 '왜' 문항(Q07~Q09)과는 성격이 다르므로 type을 분리했다.

**근거 출처**: 없음  
**인덱스내 근거**: N

### 검색 결과 (순서 = 순위)

1. `src/ctxd/models.py::src/ctxd/models.py`
2. `src/ctxd/models.py::DocumentResult`
3. `src/ctxd/models.py::SearchResult`
4. `src/ctxd/models.py::ProfileResult`
5. `src/ctxd/models.py::SearchItem`
6. `src/ctxd/async_client.py::src/ctxd/async_client.py`
7. `src/ctxd/exceptions.py::src/ctxd/exceptions.py`
8. `src/ctxd/client.py::src/ctxd/client.py`

### 답변

## Pydantic을 선택한 근거

제공된 코드에서 Pydantic을 사용하는 구체적인 이유를 세 가지 측면에서 확인할 수 있습니다.

---

### 1. 필드 별칭(Alias) 처리

`src/ctxd/models.py`의 `SearchItem` 클래스를 보면:

```python
id: str = Field(validation_alias=AliasChoices("id", "document_uid"))
text: str = Field(
    default="",
    validation_alias=AliasChoices("text", "snippet"),
)
```

서버 응답에서 `id` 또는 `document_uid`라는 이름으로 오든, `text` 또는 `snippet`이라는 이름으로 오든 모두 같은 필드로 받아낼 수 있습니다. 표준 라이브러리의 `dataclasses`나 `TypedDict`로는 이런 **여러 입력 이름을 하나의 필드로 매핑하는 기능**을 직접 구현해야 합니다.

---

### 2. 예상 외 필드 허용(extra="allow")

모든 모델(`SearchItem`, `SearchResult`, `DocumentResult`, `ProfileResult`)에 공통적으로 설정되어 있습니다:

```python
model_config = ConfigDict(extra="allow")
```

서버 응답에 코드에 정의되지 않은 필드가 추가로 포함되더라도 오류 없이 그대로 보존합니다. 표준 라이브러리로는 이 동작을 자동으로 처리하기 어렵습니다.

---

### 3. 검증과 역직렬화를 한 번에 처리

`src/ctxd/async_client.py`의 각 메서드에서:

```python
return SearchResult.model_validate(payload)
return DocumentResult.model_validate(payload)
return ProfileResult.model_validate(payload)
```

JSON을 파싱한 딕셔너리(`payload`)를 `model_validate()`에 넘기는 것만으로 타입 검증과 객체 변환이 동시에 이루어집니다. 표준 라이브러리의 `dataclasses`는 이 과정을 별도로 직접 구현해야 합니다.

---

### 요약

코드 구조로 보아, 이 프로젝트는 **외부 API 응답의 불확실성**(필드 이름 변형, 예상 외 필드 포함 가능성)을 안전하게 다루기 위해 Pydantic을 선택한 것으로 보입니다. 별칭 매핑, 추가 필드 허용, 단일 호출 검증이라는 세 기능이 그 근거입니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): H
- 메모: 코드에서 실재하는 근거 셋을 찾았으나 "이래서 골랐다"는 인과로 확장. "~로 보입니다"가 붙었어도 앞에서 근거를 세 번 못 박아 유보로 읽히지 않음. 사실 밀도가 높을수록 인과를 확신하는 패턴.

---

## 집계 (before)

| 문항 | 점수 | 플래그 |
|---|---|---|
| D01 | 1 | A |
| D02 | 1 | - |
| D03 | 1 | - |
| D04 | 0 | H |
| **합계** | **3 / 8** | H 1건 |