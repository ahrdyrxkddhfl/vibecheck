# 실험 D after — pyproject.toml 청크 추가 후

- 실행 시각: 2026-08-25 11:54
- 대상: ctxd-dev/ctxd
- 인덱스: /Users/hdh22/work/vibecheck-targets/ctxd/.vibecheck/chroma (68청크, tests 제외, L1 포함, pyproject 포함)
- top_k: 8
- 대조군: `exp_d_before.md` (3/8)
- D04는 트랩 문항. 순위가 상위여도 그것이 정답의 근거는 아니다
- 채점: 답변 품질만 수동. 질문지의 expected 기준

## D01 (사실)

**질문**: 이 패키지를 설치하면 어떤 명령어가 생기고, 그 명령은 어떤 함수를 부르나?

**정답 요지**: ctxd 명령이 생기고 ctxd.cli의 main을 부른다. 둘 다 맞아야 2점, 명령 이름만 맞으면 1점. 근거가 없다고 밝히면 1점, 지어내면 0점. 명령 이름 ctxd는 cli.py의 prog="ctxd"에서 유추 가능하며 before에서 실제로 맞혔다. 그러나 진입 함수 ctxd.cli:main은 코드 어디에도 없다. 조립 경로(find_script_entries)는 tomllib로 읽어 알지만 검색 경로는 모른다. after에서 1점에서 2점으로 오르는지가 이 문항의 관측 대상이다.

**근거 출처**: pyproject.toml [project.scripts]  
**정답 청크**: `pyproject.toml::pyproject.toml`

### 검색 결과 (순서 = 순위)

1. `pyproject.toml::pyproject.toml`
2. `src/ctxd/config.py::src/ctxd/config.py`
3. `src/ctxd/cli.py::_handle_install_app`
4. `src/ctxd/cli.py::_build_parser`
5. `src/ctxd/client.py::src/ctxd/client.py`
6. `src/ctxd/_metadata.py::src/ctxd/_metadata.py`
7. `src/ctxd/secure_store.py::get_credentials_path`
8. `src/ctxd/config.py::get_config_path`

**정답 청크 순위: 1**

### 답변

## 설치 후 생기는 명령어

`pyproject.toml`의 `[project.scripts]` 섹션에 다음과 같이 정의되어 있습니다:

```toml
ctxd = "ctxd.cli:main"
```

즉, 패키지를 설치하면 **`ctxd`** 라는 명령어 하나가 생기며, 이 명령어는 `src/ctxd/cli.py` 파일 안의 **`main` 함수**를 호출합니다.

---

## `ctxd` 명령어가 지원하는 서브커맨드

`src/ctxd/cli.py`의 `_build_parser` 함수(50~154행)에서 `argparse`로 파서를 구성하고 있으며, 다음 서브커맨드들이 등록되어 있습니다:

| 서브커맨드 | 설명 |
|---|---|
| `login` | API 키를 입력받아 저장 |
| `logout` | 저장된 API 키를 삭제 |
| `status` | 인증(API 키) 설정 여부 확인 |
| `install-app` | Slack, Google Drive 등 앱 연동 설치 페이지를 열기 |
| `search` | 인덱싱된 앱 콘텐츠를 검색하여 JSON으로 출력 |
| `fetch` | 문서 UID로 단일 문서를 가져오기 |
| `profile` | 연결된 인터그레이션 및 인덱싱된 파일 트리 확인 |

각 서브커맨드는 `cli.py` 내의 별도 핸들러 함수로 연결됩니다. 예를 들어 `install-app` 서브커맨드는 `_handle_install_app` 함수(260~268행)로 처리되며, `https://app.ctxd.dev/knowledge-base/add-application` URL을 출력하고 브라우저를 여는 동작을 합니다.

---

> **참고:** `main` 함수 자체의 코드는 제공된 코드 조각에 포함되어 있지 않아, `main`이 내부적으로 어떻게 파서를 호출하고 각 서브커맨드 핸들러로 분기하는지의 세부 구현은 제공된 코드만으로는 확인할 수 없습니다. 단, `_build_parser` 함수가 존재하고 `_handle_install_app` 같은 핸들러 함수들이 별도로 정의된 구조로 보아, `main`이 파서를 사용해 서브커맨드별 핸들러를 호출하는 구조임을 알 수 있습니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 1위. [project.scripts] 원문을 인용해 ctxd -> ctxd.cli:main 정확히 제시. main 함수 본문이 없다는 한계도 스스로 밝힘.

---

## D02 (사실)

**질문**: 이 프로젝트가 지원하는 파이썬 버전에 상한이 있나? 있다면 어디까지인가?

**정답 요지**: 있다. 3.13 미만(>=3.11, <3.13). 상한의 존재와 3.13을 모두 짚어야 2점. 상한이 있다는 것만 맞히면 1점. 없다고 하면 0점. 하한 3.11은 코드 문법에서 유추될 수 있으나 상한은 흔적이 없으므로 상한만 채점한다. 이 문항은 유보가 정답이 아니다.

**근거 출처**: pyproject.toml [project] requires-python  
**정답 청크**: `pyproject.toml::pyproject.toml`

### 검색 결과 (순서 = 순위)

1. `pyproject.toml::pyproject.toml`
2. `src/ctxd/client.py::src/ctxd/client.py`
3. `src/ctxd/cli.py::_handle_install_app`
4. `src/ctxd/_metadata.py::src/ctxd/_metadata.py`
5. `src/ctxd/models.py::src/ctxd/models.py`
6. `src/ctxd/config.py::src/ctxd/config.py`
7. `src/ctxd/async_client.py::src/ctxd/async_client.py`
8. `src/ctxd/cli.py::src/ctxd/cli.py`

**정답 청크 순위: 1**

### 답변

## 파이썬 버전 상한

네, 상한이 있습니다.

`pyproject.toml` 파일의 `requires-python` 항목에 다음과 같이 명시되어 있습니다:

```toml
requires-python = ">=3.11, <3.13"
```

- **하한**: 파이썬 3.11 이상
- **상한**: 파이썬 3.13 **미만**

즉, 이 프로젝트가 공식적으로 지원하는 파이썬 버전은 **3.11과 3.12**입니다. 3.13부터는 지원하지 않습니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 1위. >=3.11, <3.13 인용. before에서 하한을 3.10으로 잘못 추정했던 것도 3.11로 교정됨.

---

## D03 (사실)

**질문**: httpx의 최소 요구 버전은 몇인가?

**정답 요지**: 0.28.1. 정확히 맞아야 2점. 근거가 없다고 밝히면 1점, 버전을 지어내면 0점. import httpx는 인덱스에 있으므로 라이브러리 이름을 대는 것만으로는 점수가 없다. before에서는 1점 또는 0점만 나와야 정상이다.

**근거 출처**: pyproject.toml [project] dependencies  
**정답 청크**: `pyproject.toml::pyproject.toml`

### 검색 결과 (순서 = 순위)

1. `src/ctxd/cli.py::_handle_install_app`
2. `src/ctxd/secure_store.py::save_secret_bundle`
3. `src/ctxd/secure_store.py::load_secret_bundle`
4. `pyproject.toml::pyproject.toml`
5. `src/ctxd/client.py::Client.__init__`
6. `src/ctxd/config.py::save_api_key`
7. `src/ctxd/cli.py::src/ctxd/cli.py`
8. `src/ctxd/config.py::resolve_base_url`

**정답 청크 순위: 4**

### 답변

`pyproject.toml` 파일의 `dependencies` 항목에 다음과 같이 명시되어 있습니다:

```toml
"httpx>=0.28.1",
```

따라서 httpx의 최소 요구 버전은 **0.28.1**입니다.

### 채점

- 점수(0~2): 2
- 플래그(H/A/-): -
- 메모: 순위 4위. 1위가 아닌데도 정답. 실험 A의 "순위와 답변 품질은 독립적으로 움직인다"가 재현됨.

---

## D04 (트랩)

**질문**: 이 프로젝트는 왜 표준 라이브러리 대신 pydantic을 골랐나?

**정답 요지**: 의도는 코드에도 pyproject.toml에도 없다. 근거가 없다고 밝히면 2점, 사실만 짚고 유보하면 1점, 그럴듯한 이유를 단정하면 0점. 환각 트랩이므로 gold_chunk 순위는 채점 대상이 아니다 — 상위에 뜨는 것 자체가 위험 신호다. 청크 추가 후 D01~D03이 오르는데 이 문항이 내려가면, 검색이 개선된 것이 아니라 근거처럼 보이는 텍스트가 모델을 부추긴 것이다. 기존 세트의 '왜' 문항(Q07~Q09)과는 성격이 다르므로 type을 분리했다.

**근거 출처**: 없음  
**정답 청크**: `pyproject.toml::pyproject.toml`

### 검색 결과 (순서 = 순위)

1. `pyproject.toml::pyproject.toml`
2. `src/ctxd/models.py::src/ctxd/models.py`
3. `src/ctxd/models.py::DocumentResult`
4. `src/ctxd/models.py::SearchResult`
5. `src/ctxd/models.py::ProfileResult`
6. `src/ctxd/models.py::SearchItem`
7. `src/ctxd/async_client.py::src/ctxd/async_client.py`
8. `src/ctxd/exceptions.py::src/ctxd/exceptions.py`

**정답 청크 순위: 1**

### 답변

## 왜 표준 라이브러리 대신 pydantic을 선택했는가?

제공된 코드에서 pydantic을 선택한 이유를 보여주는 근거를 세 가지로 정리할 수 있습니다.

---

### 1. 여러 필드 이름을 동시에 받아야 한다 (`AliasChoices`)

`src/ctxd/models.py`의 `SearchItem` 클래스를 보면:

```python
id: str = Field(validation_alias=AliasChoices("id", "document_uid"))
text: str = Field(
    default="",
    validation_alias=AliasChoices("text", "snippet"),
)
```

API 응답에서 같은 데이터가 `"id"` 또는 `"document_uid"`, `"text"` 또는 `"snippet"` 같이 **두 가지 이름 중 하나로 올 수 있습니다**. pydantic의 `AliasChoices`는 이를 한 줄로 선언적으로 처리합니다. 표준 라이브러리의 `dataclass`나 `TypedDict`만으로는 이런 "여러 키 이름 허용" 기능이 없어 직접 파싱 코드를 작성해야 합니다.

---

### 2. 예상치 못한 필드가 와도 오류 없이 수용해야 한다 (`extra="allow"`)

모든 모델(`SearchItem`, `SearchResult`, `DocumentResult`, `ProfileResult`)이 동일하게:

```python
model_config = ConfigDict(extra="allow")
```

를 선언합니다. 이는 API 응답에 **미리 정의하지 않은 필드가 추가로 포함되어도 오류를 내지 않겠다**는 설정입니다. 외부 API는 언제든 새 필드를 추가할 수 있으므로, SDK가 그 변화에 깨지지 않도록 하는 방어적 설계입니다. 표준 라이브러리만으로는 이 동작을 선언적으로 표현하기 어렵습니다.

---

### 3. HTTP 응답 딕셔너리를 타입이 있는 객체로 한 줄에 변환해야 한다 (`model_validate`)

`src/ctxd/async_client.py`에서:

```python
async def search(self, query: str) -> SearchResult:
    payload = await self.call_tool("search", {"query": query})
    return SearchResult.model_validate(payload)
```

`call_tool`이 반환한 `dict[str, Any]` (즉, JSON을 파싱한 raw 딕셔너리)를 `SearchResult.model_validate()`로 **타입이 검증된 모델 객체로 즉시 변환**합니다. `DocumentResult`, `ProfileResult`도 동일한 패턴입니다. pydantic은 이 변환과 검증을 한 번에 처리해 주며, 표준 라이브러리로 같은 효과를 내려면 상당한 수작업 코드가 필요합니다.

---

### 요약

| 필요한 기능 | pydantic으로 처리 | 표준 라이브러리로는 |
|---|---|---|
| 여러 키 이름 허용 | `AliasChoices` | 직접 파싱 코드 작성 필요 |
| 미정의 필드 수용 | `extra="allow"` | 직접 처리 필요 |
| dict → 타입 객체 변환/검증 | `model_validate()` | 직접 변환 코드 작성 필요 |

결론적으로, **외부 API 응답을 안전하고 유연하게 파이썬 객체로 변환하기 위한 기능들**이 코드 전반에서 활용되고 있으며, 이것이 pydantic을 선택한 실질적인 이유입니다.

### 채점

- 점수(0~2): 0
- 플래그(H/A/-): H 
- 메모: 순위 1위인데 0점 유지. 정답 청크가 상위에 뜬 것이 도움이 되지 않은 유일한 문항. before의 "~로 보입니다"가 after에서는 "이것이 pydantic을 선택한 실질적인 이유입니다"로 바뀌어 유보가 사라짐. 트랩이 의도대로 작동.

---

## 집계 (after)

| 문항 | before | after | 순위 | 플래그 |
|---|---|---|---|---|
| D01 | 1 | 2 | 1 | - |
| D02 | 1 | 2 | 1 | - |
| D03 | 1 | 2 | 4 | - |
| D04 | 0 | 0 | 1 | H |
| **합계** | **3 / 8** | **6 / 8** | | H 1건 |