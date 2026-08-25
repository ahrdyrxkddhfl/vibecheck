"""VibeCheck 로컬 웹앱의 FastAPI 진입점.

공개 서비스가 아니라 로컬 전용이다. 인증도 업로드도 없고, 사용자가
자기 디스크의 경로를 직접 지정한다. 그래서 CORS도 개발 서버에만 연다.

라우터를 파일별로 나누는 이유는 화면 단위로 늘어날 것이기 때문이다.
리포트, 질문, 연습, 타자, 진단이 각각 붙는다.
"""

from fastapi import FastAPI

from vibecheck.web.routers import report

app = FastAPI(
    title="VibeCheck",
    description="바이브코딩 레포를 읽고 설명할 수 있게 만드는 로컬 도구",
    version="0.1.0",
)

app.include_router(report.router, prefix="/api", tags=["report"])


@app.get("/health")
def health() -> dict[str, str]:
    """서버가 떴는지만 확인하는 엔드포인트.

    인덱스도 레포도 건드리지 않는다. 라우터가 깨졌을 때
    "서버가 안 뜬 것"과 "특정 경로가 깨진 것"을 구분하기 위해 둔다.

    Returns:
        dict[str, str]: 상태 문자열.
    """
    return {"status": "ok"}