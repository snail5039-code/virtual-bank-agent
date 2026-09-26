# 3-3 조건부 이체 확인용입니다.
# main.py 를 켜고 한 줄씩 입력하면서 화면 출력을 보여줍니다.
#
# 실행 : uv run python 테스트/3-3_조건부이체_확인.py
#
# 확인할 것 (초기 생활비 잔액 1,431,800원)
#   1) 조건부 이체 : "생활비에 40만원 남기고 나머지 저축해줘"
#                    → 처리안에 남길 금액 400,000원 / 금액 1,031,800원 → 승인 → 생활비 잔액 400,000원
#   2) 불가       : "생활비에 500만원 남기고 나머지 저축해줘" → 보낼 금액이 없다고 안내 (처리안까지 가지 않는다)
#   3) 재검증     : 처리안을 본 뒤 data.json 의 생활비 잔액을 바꾸고 승인
#                   → "잔액이 바뀌어 이체할 금액이 달라졌습니다" 로 실행하지 않는다
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


def start():
    proc = subprocess.Popen(
        [sys.executable, "src/main.py"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    out = []
    threading.Thread(target=lambda: [out.append(ch) for ch in iter(lambda: proc.stdout.read(1), "")],
                     daemon=True).start()
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


def set_balance(account_id, balance):
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    for account in data["accounts"]:
        if account["account_id"] == account_id:
            account["balance"] = balance
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


shutil.copy("data/initial_data.json", DATA)
proc, out = start()
while "요청을 입력하세요" not in "".join(out):
    time.sleep(0.2)

print("===== 1) 조건부 이체 =====")
send(proc, out, "생활비에 40만원 남기고 나머지 저축해줘")
send(proc, out, "응, 진행해")

print("===== 2) 불가 =====")
send(proc, out, "생활비에 500만원 남기고 나머지 저축해줘")

print("===== 3) 재검증 =====")
set_balance("acc-001", 1000000)
send(proc, out, "생활비에 40만원 남기고 나머지 저축해줘")
print("(처리안을 본 뒤 생활비 잔액을 1,000,000원 → 900,000원으로 바꿉니다)\n")
set_balance("acc-001", 900000)
send(proc, out, "승인")

proc.stdin.write("종료\n")
proc.stdin.flush()
proc.wait()
shutil.copy("data/initial_data.json", DATA)
