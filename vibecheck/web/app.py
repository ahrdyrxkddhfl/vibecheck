"""VibeCheck 로컬 웹앱의 FastAPI 진입점.

공개 서비스가 아니라 로컬 전용이다. 인증도 업로드도 없고, 사용자가
자기 디스크의 경로를 직접 지정한다. 그래서 CORS도 개발 서버에만 연다.

라우터를 파일별로 나누는 이유는 화면 단위로 늘어날 것이기 때문이다.
리포트, 질문, 연습, 타자, 진단이 각각 붙는다.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vibecheck.web.routers import history, report

STATIC_DIR = Path(__file__).parent / "static"
"""화면 파일이 있는 디렉터리.

패키지 안에 두는 이유는 어디서 서버를 띄우든 같은 경로를 가리키게 하기 위해서다.
실행 디렉터리 기준 상대 경로로 두면 프로젝트 밖에서 실행할 때 화면이 사라진다.
"""

app = FastAPI(
    title="VibeCheck",
    description="바이브코딩 레포를 읽고 설명할 수 있게 만드는 로컬 도구",
    version="0.1.0",
)

app.include_router(report.router, prefix="/api", tags=["report"])
app.include_router(history.router, prefix="/api", tags=["history"])

@app.middleware("http")
async def revalidate_static(request, call_next):
    """화면 파일에 매번 서버에 확인하고 쓰라는 헤더를 붙인다.

    StaticFiles는 수정 시각과 ETag만 붙이고 캐시 지시는 붙이지 않는다. 그러면
    브라우저가 최근에 바뀐 파일은 한동안 확인 없이 써도 된다고 스스로 판단해,
    index.html을 고치고 서버를 다시 띄워도 옛 화면이 떴다. 사파리에서 실제로
    그렇게 떠서 강력 새로고침을 해야 새 화면이 보였다.

    no-cache는 저장을 막는 것이 아니라 쓰기 전에 확인하라는 뜻이다. 파일이
    그대로면 서버는 304로 "그대로"라고만 답하므로 다시 받지 않는다.

    /api는 건드리지 않는다. 수정 시각이 없어 브라우저가 스스로 캐시하지 않는다.

    Args:
        request: 들어온 요청.
        call_next: 다음 처리 단계.

    Returns:
        헤더를 붙인 응답.
    """
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response

@app.get("/health")
def health() -> dict[str, str]:
    """서버가 떴는지만 확인하는 엔드포인트.

    인덱스도 레포도 건드리지 않는다. 라우터가 깨졌을 때
    "서버가 안 뜬 것"과 "특정 경로가 깨진 것"을 구분하기 위해 둔다.

    Returns:
        dict[str, str]: 상태 문자열.
    """
    return {"status": "ok"}



# 마운트를 맨 마지막에 하는 이유는 순서가 곧 우선순위이기 때문이다.
# 루트에 먼저 마운트하면 /api와 /health까지 정적 파일 서빙이 가로챈다.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")