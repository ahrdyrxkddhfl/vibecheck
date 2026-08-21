"""파일 해시 기반으로 요약을 캐시해 재인덱싱 비용을 줄인다.

인덱싱의 대부분 비용은 LLM 요약 호출이다. 청크는 매번 새로 생성되어 summary가 항상 None이므로,
캐시가 없으면 파일이 바뀌지 않아도 전체를 다시 요약한다.
실제로 실험 중 재인덱싱 4회에서 매번 전 청크를 재요약했다.

파일 내용의 해시를 키로 쓰는 이유는 수정 시각이 신뢰할 수 없기 때문이다.
git 브랜치 전환은 내용이 같아도 mtime을 바꾸고, 반대로 내용이 바뀌어도 mtime이 유지되는 경우가 있다.
내용 자체를 지문으로 삼아야 정확하다.

파일 단위로 묶는 이유는 파일이 바뀌면 그 안의 청크 대부분이 영향을 받기 때문이다.
줄 번호가 밀리는 것만으로도 청크 경계가 달라진다.
"""

import hashlib
import json
from pathlib import Path

from vibecheck.models import Chunk

def file_hash(path: str) -> str:
        """파일 내용의 SHA-256 해시를 계산한다.

        바이너리로 읽는 이유는 인코딩 해석을 거치지 않기 위해서다.
        줄바꿈 문자 처리 등으로 같은 파일이 다른 해시를 갖는 것을 막는다.

        Args:
            path (str): 해시를 계산할 파일 경로.

        Returns:
            str: 16진수 해시 문자열.
        """
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class Manifest:
    """파일별 해시와 청크 요약을 보관하는 캐시 장부.

    Attributes:
        path: manifest.json 파일 경로
        data: 파일 경로를 키로 하는 캐시 내용.
    """

    def __init__(self, persist_dir: str = ".vibecheck"):
        """장부를 읽어들인다. 파일이 없으면 빈 상태로 시작한다.

        읽기 실패 시 예외를 던지지 않고 빈 장부로 시작하는 이유는
        캐시가 없거나 손상되어도 인덱싱 자체는 성공해야 하기 때문이다.
        캐시는 속도를 위한 것이지 정확성의 근거가 아니다.

        Args:
            persis_dir (str): 장부를 저장할 디렉토리.
        """
        self.path = Path(persist_dir) / "manifest.json"
        self.data: dict = {}

        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def apply(self, chunks: list[Chunk], source_path: str) -> int:
        """캐시된 요약을 청크에 채워넣는다.

        파일 해시가 일치할 때만 적용한다.
        해시가 다르면 파일이 수정된 것이므로 캐시를 무시하고 새로 요약하게 둔다.

        심볼명이 일치하는 청크에만 요약을 넣는 이유는 파일이 같아도 새 함수가 추가되었을 수 있기 때문이다.
        없는 항목은 그냥 넘어가고 요약 단계에서 채워진다.

        Args:
            chunks (list[Chunk]): 요약을 채울 청크 목록.
            source_path (str): 해시를 계산할 실제 파일 경로.

        Returns:
            int: 캐시가 적용된 청크 수.
        """
        if not chunks:
            return 0

        key = chunks[0].file
        entry = self.data.get(key)

        if not entry or entry.get("hash") != file_hash(source_path):
            return 0

        cached = entry.get("chunks", {})
        hits = 0

        for c in chunks:
            if c.id in cached:
                c.summary = cached[c.id]
                hits += 1

        return hits

    def update(self, chunks: list[Chunk], source_path: str) -> None:
        """요약이 채워진 청크를 장부에 기록한다.

        Args:
            chunks (list[Chunk]): 요약이 완료된 청크 목록.
            source_path (str): 해시를 계산할 실제 파일 경로.
        """
        if not chunks:
            return

        self.data[chunks[0].file] = {
            "hash": file_hash(source_path),
            "chunks": {c.id: c.summary for c in chunks if c.summary},
        }

    def save(self) -> None:
        """장부를 디스크에 기록한다.

        ensure_ascii=False로 저장하는 이유는 한국어 요약이 유니코드 이스케이프로 저장되면
        사람이 직접 열어 확인할 수 없기 때문이다.
        캐시 문제를 디버깅할 때 내용을 읽을 수 있어야 한다.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )