# 3-8 예약 이체 + 예약 조회·취소 확인용입니다.
# main.py 를 켜고 한 줄씩 입력하면서 화면 출력을 보여줍니다.
# 예약 시각을 기다릴 수 없으니, 중간에 data.json 의 예약 시각을 과거로 바꿔 "시각이 됐다" 고 칩니다.
#
# 실행 : uv run python 테스트/3-8_예약이체_확인.py
#
# 확인할 것 (초기 생활비 잔액 1,431,800원)
#   1) 예약      : "내일 오전 9시에 생활비에서 저축으로 10만원 보내줘" → 본인 확인 → 처리안(예약 시각) → 승인
#                  → 예약만 되고 잔액은 그대로
#   2) 예약 조회 : "예약 목록 보여줘" → sch-001 [예약]
#   3) 시각 도래 : 예약 시각을 과거로 바꾼 뒤 아무 입력 → 요청보다 먼저 "[예약 이체 완료]" 가 나오고 잔액이 줄어 있다
#   4) 결과 확인 : "예약 이체 됐어?" → [완료]
#   5) 예약 취소 : 예약을 하나 더 걸고 "sch-002 예약 취소해줘" → 승인 → [취소]
#   6) 과거 시각 : "어제 9시에 …" → 이미 지났다고 불가
#   7) 켤 때 처리 : 프로그램을 끈 뒤 잔액보다 큰 예약을 과거 시각으로 넣고 다시 켜면
#                  첫 화면에 "[예약 이체 실패] … 잔액이 부족합니다" 가 나온다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys
import threading
import time

DATA = "data/data.json"
PAST = "2026-01-01T09:00:00+09:00"


def start():
    proc = subprocess.Popen(
        [sys.executable, "src/main.py"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    out = []
    threading.Thread(target=lambda: [out.append(ch) for ch in iter(lambda: proc.stdout.read(1), "")],
                     daemon=True).start()
    while "요청을 입력하세요" not in "".join(out):
        time.sleep(0.2)
    print("".join(out).replace("요청을 입력하세요 : ", "").strip())
    print()
    return proc, out


def send(proc, out, text):
    # 한 줄 넣고, 다음 입력 안내가 나올 때까지 기다린 뒤 그 사이 출력을 보여줍니다.
    before = len("".join(out))
    print(">>", text)
    proc.stdin.write(text + "\n")
    proc.stdin.flush()
    while "요청을 입력하세요" not in "".join(out)[before:]:
        time.sleep(0.2)
    print("".join(out)[before:].replace("요청을 입력하세요 : ", "").strip())
    print()


def stop(proc):
    proc.stdin.write("종료\n")
    proc.stdin.flush()
    proc.wait()


def edit_data(change):
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    change(data)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_due(schedule_id):
    def change(data):
        for s in data["scheduled_transfers"]:
            if s["schedule_id"] == schedule_id:
                s["scheduled_at"] = PAST
    edit_data(change)


shutil.copy("data/initial_data.json", DATA)
proc, out = start()

print("===== 1) 예약, 2) 예약 조회 =====")
send(proc, out, "내일 오전 9시에 생활비에서 저축으로 10만원 보내줘")
send(proc, out, "1234")
send(proc, out, "승인")
send(proc, out, "예약 목록 보여줘")

print("===== 3) 시각 도래 (예약 시각을 과거로 바꿉니다) =====\n")
make_due("sch-001")
send(proc, out, "내 계좌 잔액 보여줘")

print("===== 4) 결과 확인 =====")
send(proc, out, "예약 이체 됐어?")

print("===== 5) 예약 취소 =====")
send(proc, out, "내일 오전 10시에 생활비에서 저축으로 5만원 보내줘")
send(proc, out, "승인")
send(proc, out, "sch-002 예약 취소해줘")
send(proc, out, "승인")
send(proc, out, "예약 목록 보여줘")

print("===== 6) 과거 시각 =====")
send(proc, out, "어제 오전 9시에 생활비에서 저축으로 1만원 보내줘")
stop(proc)

print("===== 7) 켤 때 처리 (꺼진 동안 잔액보다 큰 예약이 시각을 넘김) =====\n")
edit_data(lambda data: data["scheduled_transfers"].append({
    "schedule_id": "sch-003", "owner_id": "user-001", "from_account": "acc-001", "to_account": "acc-002",
    "amount": 100000000, "scheduled_at": PAST, "status": "예약"}))
proc, out = start()
send(proc, out, "예약 목록 보여줘")
stop(proc)

shutil.copy("data/initial_data.json", DATA)
