"""파일 해시 기반으로 요약을 캐시하고, 인덱싱 조건을 함께 기록한다.

인덱싱의 대부분 비용은 LLM 요약 호출이다. 청크는 매번 새로 생성되어 summary가 항상 None이므로,
캐시가 없으면 파일이 바뀌지 않아도 전체를 다시 요약한다.
실제로 실험 중 재인덱싱 4회에서 매번 전 청크를 재요약했다.

파일 내용의 해시를 키로 쓰는 이유는 수정 시각이 신뢰할 수 없기 때문이다.
git 브랜치 전환은 내용이 같아도 mtime을 바꾸고, 반대로 내용이 바뀌어도 mtime이 유지되는 경우가 있다.
내용 자체를 지문으로 삼아야 정확하다.

파일 단위로 묶는 이유는 파일이 바뀌면 그 안의 청크 대부분이 영향을 받기 때문이다.
줄 번호가 밀리는 것만으로도 청크 경계가 달라진다.

캐시와 함께 인덱싱 조건(exclude_dirs, 수집 파일 수)도 기록한다.
이 정보가 없으면 리포트를 만들 때마다 사용자가 --exclude를 다시 쳐야 하고,
빼먹으면 인덱스와 어긋난 숫자가 조용히 나온다. 웹에는 넘길 방법조차 없다.
장부는 인덱싱이 여는 유일한 파일이므로 이 정보가 있어야 할 자리도 여기다.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from vibecheck.models import Chunk

MANIFEST_VERSION = 2
"""장부 형식 판.

1판은 최상위가 파일 경로 딕셔너리여서 메타데이터를 넣을 자리가 없었다.
2판은 files와 index로 나눈다. 파일 경로와 메타데이터 키가 섞이면
경로 이름에 따라 충돌할 수 있고, 파일 수를 세는 코드도 틀린다.
"""


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
    """파일별 해시·청크 요약과 인덱싱 조건을 보관하는 캐시 장부.

    Attributes:
        path: manifest.json 파일 경로.
        data: 파일 경로를 키로 하는 캐시 내용.
        meta: 인덱싱 조건. exclude_dirs, file_count, indexed_at.
    """

    def __init__(self, persist_dir: str = ".vibecheck"):
        """장부를 읽어들인다. 파일이 없으면 빈 상태로 시작한다.

        읽기 실패 시 예외를 던지지 않고 빈 장부로 시작하는 이유는
        캐시가 없거나 손상되어도 인덱싱 자체는 성공해야 하기 때문이다.
        캐시는 속도를 위한 것이지 정확성의 근거가 아니다.

        1판 장부는 형식을 알아보고 옮겨 담는다.
        버려도 인덱싱은 성공하지만 전 청크가 재요약되어 비용이 나간다.
        1판은 파일 딕셔너리 그 자체였으므로 files에 그대로 넣으면 된다.

        Args:
            persist_dir (str): 장부를 저장할 디렉토리.
        """
        self.path = Path(persist_dir) / "manifest.json"
        self.data: dict = {}
        self.meta: dict = {}

        if not self.path.exists():
            return

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        if not isinstance(raw, dict):
            return

        if "files" in raw:
            self.data = raw.get("files") or {}
            self.meta = raw.get("index") or {}
        else:
            # 1판: 최상위가 곧 파일 딕셔너리였다. 요약은 그대로 살린다.
            self.data = raw

    def set_index_meta(
        self, exclude_dirs: set[str] | None, file_count: int
    ) -> None:
        """이번 인덱싱의 조건을 기록한다.

        exclude_dirs를 정렬해 저장하는 이유는 집합의 순회 순서가
        실행마다 달라 장부 파일에 의미 없는 차이가 생기기 때문이다.

        Args:
            exclude_dirs (set[str] | None): 기본 제외 목록에 더한 디렉토리 이름.
            file_count (int): collect_files가 수집한 파일 수.
                청크가 생긴 파일이 아니라 수집된 파일 전부다.
        """
        self.meta = {
            "exclude_dirs": sorted(exclude_dirs or ()),
            "file_count": file_count,
            "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

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

    def prune(self, kept: set[str]) -> list[str]:
        """이번 인덱싱에서 수집되지 않은 파일의 캐시를 지운다.

        update는 처리한 파일만 덮어쓰고 save는 data를 통째로 쓴다.
        지우는 자리가 없어 한 번 들어온 항목은 제외 대상이 되어도
        영구히 남는다. 실제로 기본 제외 목록에 넣은 뒤 여러 번
        재인덱싱한 디렉토리가 그대로 남아 있었다.

        기준을 update를 탄 파일이 아니라 수집된 파일로 잡는 이유는
        요약이 실패하거나 건너뛴 파일의 멀쩡한 캐시를 날리지 않기
        위해서다. 수집 목록에 있으면 이번에도 인덱싱 대상이다.

        VectorStore.prune과 같은 이름을 쓴다. 청크와 장부는 짝을
        이루므로 같은 일에 같은 이름이 붙어 있어야 한다.

        Args:
            kept (set[str]): 이번에 수집한 파일의 상대 경로 집합.
                장부 키와 같은 형태여야 한다.

        Returns:
            list[str]: 지운 항목의 경로 목록.
        """
        gone = [key for key in self.data if key not in kept]

        for key in gone:
            del self.data[key]

        return gone

    def save(self) -> None:
        """장부를 디스크에 기록한다.

        ensure_ascii=False로 저장하는 이유는 한국어 요약이 유니코드 이스케이프로 저장되면
        사람이 직접 열어 확인할 수 없기 때문이다.
        캐시 문제를 디버깅할 때 내용을 읽을 수 있어야 한다.
        """
        payload = {
            "version": MANIFEST_VERSION,
            "index": self.meta,
            "files": self.data,
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )