# 5-2 재시작 복구 (이전 승인만으로 자동 실행하지 않음) 확인용입니다.
# main.py 를 켜서 승인 대기 중에 끄고, 다시 켜서 어떻게 되는지 봅니다.
#
# 실행 : uv run python 테스트/5-2_재시작복구_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 기록 남기기 : 처리안(승인 대기)에서 끄면 data.json 의 pending 에 원래 요청이 남는다. 돈은 안 움직인다
#   2) 켤 때 묻기  : 다시 켜면 "진행 중이던 업무" 를 알려주고 다시 할지 묻는다
#   3) 다시 하기   : "예" → 원래 요청을 처음부터 다시 돌린다. 본인 확인과 승인을 다시 받는다 (자동 실행 안 함)
#                   그 사이 잔액이 바뀌었으면 바뀐 잔액으로 처리안이 나온다
#   4) 끝나면 지움 : 승인해서 저장되면 pending 이 지워지고, 다시 켜도 묻지 않는다
#   5) 안 하기     : "아니오" → 기록만 지우고 바뀐 것은 없다
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
        input="\n".join(inputs) + "\n",
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    print(result.stdout)
    print(result.stderr)


def show():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    balances = {a["nickname"]: a["balance"] for a in data["accounts"] if a["owner_id"] == "user-001"}
    print("  pending :", data.get("pending"))
    print("  잔액    :", balances)
    print("  처리 기록 :", [(r["task_type"], r["status"]) for r in data["requests"]])
    print()


def set_balance(account_id, balance):
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    next(a for a in data["accounts"] if a["account_id"] == account_id)["balance"] = balance
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 승인 대기 중에 끄기 =====")
run(["생활비에서 저축으로 50만원 보내줘", "1234", "종료"])
show()

print("===== 2) 3) 4) 켜서 다시 하기 (그 사이 생활비 잔액을 100만원으로 바꿔 둠) =====")
set_balance("acc-001", 1000000)
run(["예", "1234", "승인", "종료"])
show()

print("===== 4) 다시 켜도 묻지 않음 =====")
run(["종료"])

print("===== 5) 끄고 → 켜서 아니오 =====")
run(["여행 카드 잠가줘", "1234", "종료"])
show()
run(["아니오", "종료"])
show()

shutil.copy("data/initial_data.json", DATA)
