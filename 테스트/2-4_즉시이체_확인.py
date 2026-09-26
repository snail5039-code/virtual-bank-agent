# 2-4 즉시이체 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤, 화면 출력과 data.json 의 잔액·거래 내역·처리 기록을 보여줍니다.
#
# 실행 : uv run python 테스트/2-4_즉시이체_확인.py
#
# 확인할 것
#   1) 이체     : 생활비 → 저축 10만원 승인 → 생활비 1,331,800 / 저축 2,380,000
#                 이어서 잔액 조회에도 바뀐 잔액이 나온다
#                 거래 내역에 tx-021 출금 / tx-022 입금 이 붙는다
#   2) 불가     : -1만원 → "0원보다 커야 합니다"
#                 1억원  → "잔액이 부족합니다"  (처리안까지 가지 않는다)
#   3) 재검증   : 승인한 뒤 잔액이 줄어든 경우 functions.transfer 가 막는다 (함수로 직접 확인)
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

DATA = "data/data.json"


def run(inputs):
    result = subprocess.run(
        [sys.executable, "src/main.py"],
        input="\n".join(inputs + ["종료"]) + "\n",
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    print(result.stdout)
    print(result.stderr)


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 이체, 2) 불가 =====")
run(["생활비에서 저축으로 10만원 보내줘", "1234", "응, 진행해",
     "내 계좌 잔액 보여줘",
     "생활비에서 저축으로 -1만원 보내줘",
     "생활비에서 저축으로 1억 보내줘"])

with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
print("잔액")
for a in data["accounts"][:3]:
    print("  ", a["account_id"], a["nickname"], format(a["balance"], ","))
print("거래 내역 마지막 2건")
for t in data["transactions"][-2:]:
    print("  ", t["transaction_id"], t["account_id"], t["type"], format(t["amount"], ","))
print("처리 기록")
for r in data["requests"]:
    print("  ", r["request_id"], r["task_type"], r["status"])
print()

print("===== 3) 재검증 =====")
sys.path.insert(0, "src")
import functions
data["accounts"][0]["balance"] = 1000          # 승인한 뒤 생활비 잔액이 1,000원으로 줄었다고 칩니다
print("  ", functions.transfer(data, "acc-001", "acc-002", 100000))

shutil.copy("data/initial_data.json", DATA)
