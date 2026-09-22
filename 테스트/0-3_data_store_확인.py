# 0-3 data_store 동작 확인용입니다.
#
# 실행 :  uv run python 테스트/0-3_data_store_확인.py
#         uv run python 테스트/0-3_data_store_확인.py --debug
#
# 확인하는 것
#
#   1) 작업본이 없으면 원본에서 복사한다 (ensure)
#   2) 작업본이 있으면 건드리지 않는다
#   3) 읽고 쓴 내용이 그대로 남는다 (load / save)
#   4) 밑줄(_)로 시작하는 키는 파일에 들어가지 않는다
#   5) 저장이 실패하면 이전 상태가 그대로 남는다 (임시 파일도 안 남는다)
#   6) reset 하면 원본 상태로 돌아온다
#   7) 원본(initial_data.json)은 어떤 경우에도 바뀌지 않는다
#   8) 복사·읽기·저장·실패가 로그에 남는다
#
# 검사는 임시 폴더에 따로 만든 작업본으로 합니다.
# 진짜 data/data.json 은 읽기만 하고 쓰지 않습니다.
#
# 확인 하나가 로그의 턴 하나가 되게 묶었습니다. 그래야 로그만 보고도
# 어느 확인에서 무엇이 일어났는지 따라갈 수 있습니다.
#
# --debug 를 붙이면 로그가 콘솔에도 뜹니다.

import hashlib
import json
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import logger as L
import data_store as D

debug = "--debug" in sys.argv
log = L.setup(debug=debug)

REAL_INITIAL = ROOT / "data" / "initial_data.json"
REAL_DATA = ROOT / "data" / "data.json"

passed = 0
failed = 0


@contextmanager
def turn(title, result="완료"):
    """확인 한 묶음을 로그의 턴 하나로 만듭니다."""
    print()
    print(title)
    log.turn_start(title)
    try:
        yield
    finally:
        log.turn_end(result)


def check(title, ok, note=""):
    """확인 한 줄입니다. 화면과 로그 양쪽에 남깁니다."""
    global passed, failed
    if ok:
        passed += 1
        mark = "OK "
    else:
        failed += 1
        mark = "실패"
        log.expand()                       # 틀린 턴은 로그를 전부 펼칩니다
    print("  %s %s%s" % (mark, title, ("   %s" % note) if note else ""))
    log.note("%s %s%s" % (mark, title, ("   %s" % note) if note else ""))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


print("로그 파일 :", log.path)
print("모드      :", "--debug (콘솔에도 출력)" if debug else "기본 (파일에만)")

# 원본이 끝까지 그대로인지 보려고 시작할 때 값을 적어 둡니다.
initial_before = digest(REAL_INITIAL)
real_data_before = digest(REAL_DATA) if REAL_DATA.exists() else None

work = Path(tempfile.mkdtemp(prefix="data_store_확인_"))
data_path = work / "data.json"
initial_path = work / "initial_data.json"
shutil.copyfile(REAL_INITIAL, initial_path)     # 검사용 원본 사본
store = D.DataStore(data_path=data_path, initial_path=initial_path)


# ============================================================ 1) ensure - 복사
with turn("1) ensure — 작업본이 없으면 원본에서 복사"):
    with log.node("data_store.ensure"):
        copied = store.ensure()

    check("복사했다고 알려준다", copied is True, "반환 %s" % copied)
    check("작업본 파일이 생겼다", data_path.is_file())
    check("원본과 내용이 같다", digest(data_path) == digest(initial_path))


# ============================================================ 2) ensure - 두 번째
with turn("2) ensure — 이미 있으면 건드리지 않는다"):
    data = json.loads(data_path.read_text(encoding="utf-8"))
    data["accounts"][0]["balance"] = 777
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    touched = digest(data_path)

    with log.node("data_store.ensure"):
        again = store.ensure()

    check("복사하지 않는다", again is False, "반환 %s" % again)
    check("바꿔 둔 내용이 그대로다", digest(data_path) == touched)


# ============================================================ 3) load / save
with turn("3) load / save — 읽고 쓴 내용이 그대로 남는다"):
    with log.node("data_store.load"):
        data = store.load()

    check("dict 로 읽힌다", isinstance(data, dict))
    check("배열 14개가 다 있다", len(data) == 14, "%d개" % len(data))
    check("아까 바꾼 값이 읽힌다", data["accounts"][0]["balance"] == 777)

    data["accounts"][0]["balance"] = 1234500
    with log.node("data_store.save"):
        store.save(data)

    with log.node("확인 읽기"):
        reread = store.load()

    check("저장한 값이 다시 읽힌다", reread["accounts"][0]["balance"] == 1234500)
    check("나머지 배열은 그대로다", len(reread) == 14)
    check("한글이 그대로 저장된다", "김도윤" in data_path.read_text(encoding="utf-8"))


# ============================================================ 4) 밑줄 키
with turn("4) 밑줄(_)로 시작하는 키는 파일에 들어가지 않는다"):
    with log.node("확인 읽기"):
        data = store.load()

    data["_balance_snapshot"] = {"acc-001": 1234500}    # 최상위
    data["accounts"][0]["_before"] = 777                # 배열 안쪽
    data["users"][0]["_tmp"] = "실행 중에만 쓰는 값"    # 한 번 더 안쪽

    with log.node("data_store.save"):
        store.save(data)

    saved_text = data_path.read_text(encoding="utf-8")
    saved = json.loads(saved_text)
    check("최상위 임시 키가 빠졌다", "_balance_snapshot" not in saved)
    check("배열 안쪽 임시 키가 빠졌다", "_before" not in saved["accounts"][0])
    check("더 안쪽 임시 키도 빠졌다", "_tmp" not in saved["users"][0])
    check("밑줄 글자가 파일에 아예 없다", '"_' not in saved_text)
    check("진짜 데이터는 남았다", saved["accounts"][0]["balance"] == 1234500)
    check("넘긴 dict 는 그대로다", "_balance_snapshot" in data,
          "저장 때문에 호출자 데이터가 지워지면 안 됩니다")


# ============================================================ 5-1) 저장 실패 - 직렬화
# JSON 으로 만들 수 없는 값입니다. 파일을 열기도 전에 막힙니다.
with turn("5-1) 저장 실패 — JSON 으로 만들 수 없는 값", result="실패"):
    before = digest(data_path)
    with log.node("확인 읽기"):
        broken = store.load()
    broken["accounts"][0]["balance"] = {1, 2, 3}        # set 은 JSON 이 아닙니다

    with log.node("data_store.save"):
        try:
            store.save(broken)
            raised = None
        except D.DataStoreError as exc:
            raised = exc

    check("DataStoreError 가 난다", raised is not None, str(raised)[:60])
    check("작업본이 그대로다", digest(data_path) == before)
    check("임시 파일이 안 남았다", not (work / "data.json.tmp").exists())


# ============================================================ 5-2) 저장 실패 - 쓰기 불가
# 임시 파일 자리를 폴더로 막아 둡니다. 파일을 쓰다 실패하는 상황입니다.
with turn("5-2) 저장 실패 — 파일을 쓸 수 없는 상태", result="실패"):
    blocker = work / "data.json.tmp"
    blocker.mkdir()
    with log.node("확인 읽기"):
        ok_data = store.load()
    ok_data["accounts"][0]["balance"] = 99999999

    with log.node("data_store.save"):
        try:
            store.save(ok_data)
            raised = None
        except D.DataStoreError as exc:
            raised = exc

    check("DataStoreError 가 난다", raised is not None, str(raised)[:60])
    check("작업본이 그대로다", digest(data_path) == before)
    with log.node("확인 읽기"):
        check("바뀐 값이 반영되지 않았다",
              store.load()["accounts"][0]["balance"] == 1234500)


# ============================================================ 5-3) 실패 뒤 복구
with turn("5-3) 막은 것을 치우면 다시 저장된다"):
    blocker.rmdir()
    with log.node("data_store.save"):
        store.save(ok_data)
    with log.node("확인 읽기"):
        check("저장된다", store.load()["accounts"][0]["balance"] == 99999999)


# ============================================================ 6) reset
with turn("6) reset — 원본 상태로 되돌린다"):
    with log.node("data_store.reset"):
        fresh = store.reset()

    check("원본과 내용이 같아진다", digest(data_path) == digest(initial_path))
    check("되돌린 내용을 돌려준다", isinstance(fresh, dict) and len(fresh) == 14)
    check("바꿔 둔 값이 사라졌다",
          fresh["accounts"][0]["balance"] != 99999999,
          "잔액 %s" % format(fresh["accounts"][0]["balance"], ","))


# ============================================================ 7) 원본 보호
with turn("7) 원본은 어떤 경우에도 바뀌지 않는다", result="실패"):
    check("검사용 원본 사본이 그대로다", digest(initial_path) == initial_before)

    with log.node("같은 파일로 만들기"):
        try:
            D.DataStore(data_path=initial_path, initial_path=initial_path)
            blocked = False
        except D.DataStoreError:
            blocked = True
    check("작업본 자리에 원본을 넣으면 거부한다", blocked)

    # 만든 뒤에 몰래 바꿔치기해도 쓰기 직전에 한 번 더 막습니다
    sneaky = D.DataStore(data_path=data_path, initial_path=initial_path)
    sneaky.data_path = initial_path
    with log.node("원본에 쓰기 시도"):
        try:
            sneaky.save({"users": []})
            blocked = False
        except D.DataStoreError:
            blocked = True
    check("만든 뒤에 경로를 바꿔도 쓰기가 막힌다", blocked)
    check("그래도 원본이 그대로다", digest(initial_path) == initial_before)


# ============================================================ 8) 진짜 데이터 (읽기만)
with turn("8) 진짜 data/ — 읽기만 한다"):
    with log.node("data_store.load"):
        real = D.load()

    check("data/data.json 이 읽힌다", isinstance(real, dict) and len(real) == 14,
          "배열 %d개" % len(real))
    check("data/initial_data.json 이 안 바뀌었다",
          digest(REAL_INITIAL) == initial_before)
    check("data/data.json 도 안 바뀌었다",
          real_data_before is None or digest(REAL_DATA) == real_data_before)
    check("임시 파일이 안 남았다", not (ROOT / "data" / "data.json.tmp").exists())


# ============================================================ 마무리
shutil.rmtree(work, ignore_errors=True)

print()
print("결과 :  통과 %d / 실패 %d" % (passed, failed))
print()
print("로그에서 확인할 것")
print("  - 복사 / 읽기 / 저장 / 초기화 줄이 남았는지")
print("  - 실패한 턴(5-1 · 5-2 · 7)만 전부 펼쳐졌는지")
print("  - 저장 실패에 '변경 전 상태 유지' 가 붙었는지")
print("  - 임시 키를 제외했다는 줄이 남았는지")
print("  - 데이터 내용(비밀번호·PIN)은 로그에 안 찍혔는지")
print()
print("로그 파일 :", log.path)
if not debug:
    print("콘솔에서 보려면 : uv run python 테스트/0-3_data_store_확인.py --debug")

sys.exit(1 if failed else 0)
