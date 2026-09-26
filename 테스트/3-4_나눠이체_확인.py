# 3-4 여러 계좌로 나눠 이체 확인용입니다.
# main.py 를 켜고 한 줄씩 입력하면서 화면 출력을 보여줍니다.
#
# 실행 : uv run python 테스트/3-4_나눠이체_확인.py
#
# 확인할 것 (초기 잔액 생활비 1,431,800 / 저축 2,280,000 / 여행 자금 390,000)
#   1) 나눠 이체   : "생활비에서 저축으로 20만원, 여행 자금으로 10만원 보내줘"
#                    → 처리안에 입금 1·2, 총액 300,000원 → "저축은 5만원으로" 수정 → 총액 150,000원 → 승인
#                    → 생활비 1,281,800 / 저축 2,330,000 / 여행 자금 490,000, 거래 내역 +4
#   2) 잔액 부족   : 총액이 잔액보다 크면 처리안까지 가지 않는다
#   3) 전부 아니면 전무 : 처리안을 본 뒤 생활비 잔액을 150,000원으로 줄이고 승인
#                    → 첫 번째(10만원)는 되지만 두 번째(10만원)에서 막힘 → 아무것도 저장되지 않는다
#   4) 한 곳 이체  : 기존 즉시이체도 그대로 된다
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


def load():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def show():
    data = load()
    print("잔액 :", ", ".join("%s %s" % (a["nickname"], format(a["balance"], ",")) for a in data["accounts"][:3]))
    print("거래 내역 %d건 / 처리 기록 %d건" % (len(data["transactions"]), len(data["requests"])))
    print()


def set_balance(account_id, balance):
    data = load()
    for account in data["accounts"]:
        if account["account_id"] == account_id:
            account["balance"] = balance
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


shutil.copy("data/initial_data.json", DATA)
proc, out = start()
while "요청을 입력하세요" not in "".join(out):
    time.sleep(0.2)

print("===== 1) 나눠 이체 + 승인 전 수정 =====")
send(proc, out, "생활비에서 저축으로 20만원, 여행 자금으로 10만원 보내줘")
send(proc, out, "1234")                   # 본인 확인 (세션에서 한 번만)
send(proc, out, "저축은 5만원으로 해줘")
send(proc, out, "승인")
show()

print("===== 2) 잔액 부족 =====")
send(proc, out, "생활비에서 저축으로 100만원, 여행 자금으로 100만원 보내줘")

print("===== 3) 전부 아니면 전무 =====")
send(proc, out, "생활비에서 저축으로 10만원, 여행 자금으로 10만원 보내줘")
print("(처리안을 본 뒤 생활비 잔액을 150,000원으로 줄입니다)\n")
set_balance("acc-001", 150000)
send(proc, out, "승인")
show()

print("===== 4) 한 곳 이체 =====")
set_balance("acc-001", 1000000)
send(proc, out, "생활비에서 저축으로 3만원 보내줘")
send(proc, out, "응")

proc.stdin.write("종료\n")
proc.stdin.flush()
proc.wait()
shutil.copy("data/initial_data.json", DATA)
