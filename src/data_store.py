# 원본 JSON의 복사본을 작업용 데이터로 준비합니다.
# 작업용 JSON을 읽고 변경된 데이터를 저장하는 함수를 구현합니다.
# 초기화가 필요할 때만 원본을 다시 복사합니다.
#
# 기획서 0-3 단계입니다.
#
#   ensure()    작업본이 없으면 원본에서 복사합니다
#   load()      작업본을 읽습니다
#   save(data)  작업본에 씁니다
#   reset()     원본을 다시 복사해 처음 상태로 되돌립니다
#
# 지키는 것 세 가지
#
#   1) 원본(initial_data.json)에는 절대 쓰지 않습니다.
#      쓰기는 _write_atomic() 한 곳만 지나가고, 그 안에서 경로를 막습니다.
#
#   2) 저장이 실패하면 이전 상태가 그대로 남습니다.
#      먼저 문자열로 다 만들고, 임시 파일에 전부 쓴 뒤, 마지막에 이름만 바꿉니다.
#      중간에 터지면 작업본 파일은 아직 손도 대지 않은 상태입니다.
#      (os.replace 는 같은 폴더 안에서 원자적으로 교체합니다. 그래서 임시 파일도
#       같은 폴더에 만듭니다. 다른 폴더에 만들면 볼륨이 달라져 교체가 복사가 됩니다.)
#
#   3) 밑줄(_)로 시작하는 키는 저장하지 않습니다.
#      실행 중에만 쓰는 값(잔액 스냅샷 등)을 담은 채로 그대로 넘겨도 파일에는
#      들어가지 않게 하려는 것입니다. 파일에 남으면 다음 실행이 지난 턴의
#      찌꺼기를 진짜 데이터로 읽습니다.
#
# 로그는 복사·읽기·저장·초기화와 그 실패를 남깁니다. 내용은 남기지 않고
# 건수만 남깁니다. 데이터 안에 비밀번호와 PIN 이 들어 있기 때문입니다.
#
# 저장 실패 시의 retry 는 여기가 아니라 저장 노드(2-3 단계)가 붙입니다.
# data_store 는 "실패했다"를 정확히 알려주는 데까지만 합니다.

from __future__ import annotations

import json
import os
from pathlib import Path

import logger as L

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
INITIAL_PATH = DATA_DIR / "initial_data.json"      # 원본. 읽기만 합니다
DATA_PATH = DATA_DIR / "data.json"                 # 작업본. 모든 변경은 여기에만


class DataStoreError(Exception):
    """작업본을 준비·읽기·저장하다 실패했을 때 냅니다.

    부르는 쪽은 이것만 잡으면 됩니다. 안에서 난 OSError 나 JSONDecodeError 는
    사유 문장으로 바꿔 이 예외에 담습니다.
    """


def _strip_private(value):
    """밑줄로 시작하는 키를 뺍니다. 중첩된 dict·list 안까지 훑습니다."""
    if isinstance(value, dict):
        return {k: _strip_private(v)
                for k, v in value.items() if not str(k).startswith("_")}
    if isinstance(value, list):
        return [_strip_private(item) for item in value]
    return value


def _private_keys(value) -> list:
    """빠진 키 이름을 모읍니다. 무엇이 빠졌는지 로그에 적으려는 것입니다."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).startswith("_"):
                found.append(str(key))
            else:
                found += _private_keys(item)
    elif isinstance(value, list):
        for item in value:
            found += _private_keys(item)
    return found


def _bytes(count: int) -> str:
    return "{:,} bytes".format(count)


class DataStore:
    """작업본 파일 하나를 맡습니다.

    경로를 인자로 받는 이유는 확인 스크립트가 임시 폴더에 따로 만들어
    실패 상황을 시험할 수 있게 하려는 것입니다. 실제 실행은 모듈 아래쪽의
    ensure() / load() / save() / reset() 을 그대로 쓰면 됩니다.
    """

    def __init__(self, data_path=DATA_PATH, initial_path=INITIAL_PATH):
        self.data_path = Path(data_path)
        self.initial_path = Path(initial_path)
        if self.data_path.resolve() == self.initial_path.resolve():
            raise DataStoreError(
                "작업본과 원본이 같은 파일입니다: %s" % self.data_path)

    # ------------------------------------------------------------ 내부
    @property
    def _log(self):
        return L.get_logger()

    def _write_atomic(self, blob: bytes) -> None:
        """임시 파일에 전부 쓰고 마지막에 이름만 바꿉니다.

        여기가 이 모듈에서 파일에 쓰는 유일한 자리입니다. 원본 경로가 들어오면
        그 자리에서 막습니다.
        """
        target = self.data_path
        if target.resolve() == self.initial_path.resolve():
            raise DataStoreError("원본에는 쓰지 않습니다: %s" % target)

        tmp = target.with_name(target.name + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "wb") as f:
                f.write(blob)
                f.flush()
                os.fsync(f.fileno())        # 캐시에만 남은 채로 교체되지 않게
            os.replace(tmp, target)         # 여기서부터가 새 내용
        except OSError as exc:
            # 교체 전에 터졌으면 작업본은 손도 대지 않은 상태입니다.
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass                        # 임시 파일 정리 실패는 삼킵니다
            raise DataStoreError("%s: %s" % (type(exc).__name__, exc)) from exc

    def _read_original(self) -> bytes:
        """원본을 바이트 그대로 읽습니다. JSON 으로 읽히는지 한 번 확인합니다."""
        try:
            blob = self.initial_path.read_bytes()
        except OSError as exc:
            raise DataStoreError(
                "원본을 읽지 못했습니다 %s: %s" % (self.initial_path.name, exc)) from exc
        try:
            json.loads(blob.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DataStoreError(
                "원본이 깨졌습니다 %s: %s" % (self.initial_path.name, exc)) from exc
        return blob

    def _copy_from_original(self, action: str) -> None:
        """원본을 작업본 자리에 통째로 옮겨 놓습니다. 형식을 손대지 않습니다."""
        try:
            blob = self._read_original()
            self._write_atomic(blob)
        except DataStoreError as exc:
            self._log.io(action, self.data_path, ok=False, error=str(exc))
            raise
        self._log.io(action, self.data_path)
        self._log.detail("원본 %s → %s" % (self.initial_path.name, _bytes(len(blob))))

    # ------------------------------------------------------------ 바깥
    def ensure(self) -> bool:
        """작업본이 없으면 원본에서 복사합니다. 복사했으면 True 입니다.

        이미 있으면 건드리지 않습니다. 있는 작업본을 덮어쓰는 것은 reset() 입니다.
        """
        if self.data_path.is_file():
            self._log.detail("작업본 있음 %s" % self.data_path.name)
            return False
        self._copy_from_original("복사")
        return True

    def load(self) -> dict:
        """작업본을 읽어 dict 로 돌려줍니다."""
        try:
            text = self.data_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            err = "작업본이 없습니다. ensure() 를 먼저 부르세요"
            self._log.io("읽기", self.data_path, ok=False, error=err)
            raise DataStoreError("%s: %s" % (err, self.data_path)) from exc
        except OSError as exc:
            self._log.io("읽기", self.data_path, ok=False, error=str(exc))
            raise DataStoreError("작업본을 읽지 못했습니다: %s" % exc) from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            self._log.io("읽기", self.data_path, ok=False, error="JSON 아님: %s" % exc)
            raise DataStoreError("작업본이 깨졌습니다: %s" % exc) from exc

        if not isinstance(data, dict):
            err = "최상위가 dict 가 아닙니다: %s" % type(data).__name__
            self._log.io("읽기", self.data_path, ok=False, error=err)
            raise DataStoreError(err)

        self._log.io("읽기", self.data_path)
        self._log.detail("배열 %d개 / %s" % (len(data), _bytes(len(text.encode("utf-8")))))
        return data

    def save(self, data: dict) -> None:
        """작업본에 씁니다. 실패하면 DataStoreError 를 내고 파일은 그대로 둡니다."""
        if not isinstance(data, dict):
            err = "저장할 데이터가 dict 가 아닙니다: %s" % type(data).__name__
            self._log.io("저장", self.data_path, ok=False, error=err)
            raise DataStoreError(err)

        dropped = _private_keys(data)
        cleaned = _strip_private(data)

        # 파일을 열기 전에 먼저 다 만듭니다.
        # 여기서 터지면 임시 파일조차 생기지 않습니다.
        try:
            text = json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n"
        except (TypeError, ValueError) as exc:
            err = "JSON 으로 만들지 못했습니다: %s" % exc
            self._log.io("저장", self.data_path, ok=False, error=err)
            raise DataStoreError(err) from exc

        blob = text.encode("utf-8")
        try:
            self._write_atomic(blob)
        except DataStoreError as exc:
            self._log.io("저장", self.data_path, ok=False, error=str(exc))
            self._log.detail("변경 전 상태 유지")
            raise

        self._log.io("저장", self.data_path)
        self._log.detail("배열 %d개 / %s" % (len(cleaned), _bytes(len(blob))))
        if dropped:
            self._log.detail("임시 키 %d개 제외 (%s)" % (
                len(dropped), ", ".join(sorted(set(dropped))[:5])))

    def reset(self) -> dict:
        """원본을 다시 복사해 처음 상태로 되돌리고, 되돌린 내용을 돌려줍니다."""
        self._copy_from_original("초기화")
        return self.load()


# ---------------------------------------------------------------- 전역 하나
_store = None


def setup(data_path=DATA_PATH, initial_path=INITIAL_PATH) -> DataStore:
    """경로를 바꿔 쓸 때만 부릅니다. 보통은 아래 함수들을 그대로 쓰면 됩니다."""
    global _store
    _store = DataStore(data_path, initial_path)
    return _store


def get_store() -> DataStore:
    global _store
    if _store is None:
        _store = DataStore()
    return _store


def ensure() -> bool:
    return get_store().ensure()


def load() -> dict:
    return get_store().load()


def save(data: dict) -> None:
    get_store().save(data)


def reset() -> dict:
    return get_store().reset()
