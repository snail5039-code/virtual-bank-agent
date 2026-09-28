# 12장 보완 — 등록 계좌(상대 계좌 주소록)로 이체 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤, 화면 출력과 data.json 의 잔액·거래 내역을 보여줍니다.
#
# 실행 : uv run python 테스트/보완_등록계좌이체_확인.py
#
# 확인할 것 (초기 등록 계좌 : 동생 생활비 = 가상은행 acc-004 / 친구 민수 = 미래은행, 가상은행 계좌 없음)
#   1) 다른 은행   : "생활비에서 친구 민수한테 5만원" → 처리안에 미래은행·예금주 → 승인 → 출금 1건만 남는다
#   2) 가상은행    : "생활비에서 동생 생활비로 3만원" → 승인 → acc-004 잔액이 3만원 늘고 입금 1건
#   3) 후보 고르기 : "저축에서 생활비로 1만원" → 내 생활비 / 동생 생활비(등록 계좌) 둘 중 고르기 → 1번 → 승인
#   4) 나눠 이체   : "생활비에서 저축으로 1만원, 친구 민수한테 2만원" → 승인
#   5) 예약 실행   : 친구 민수로 가는 지난 예약을 넣고 run_due_schedules() → 완료, 이름이 '친구 민수' 로 나온다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "생활비에서 친구 민수한테 5만원 보내줘", "1234", "승인",
    "생활비에서 동생 생활비로 3만원 보내줘", "승인",
    "저축에서 생활비로 1만원 보내줘", "1", "승인",
    "생활비에서 저축으로 1만원, 친구 민수한테 2만원 보내줘", "승인",
    "종료",
]

shutil.copy("data/initial_data.json", DATA)
with open(DATA, encoding="utf-8") as f:
    before = {a["account_id"]: a["balance"] for a in json.load(f)["accounts"]}

result = subprocess.run(
    [sys.executable, "src/main.py"],
    input="\n".join(inputs) + "\n",
    capture_output=True, text=True, encoding="utf-8",
    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
)
print(result.stdout)
print(result.stderr)

with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
print("잔액 (전 → 후)")
for a in data["accounts"]:
    print("  ", a["account_id"], a["nickname"], format(before[a["account_id"]], ","), "→", format(a["balance"], ","))
print("새 거래 내역")
for tx in data["transactions"][-8:]:
    print("  ", tx["transaction_id"], tx["owner_id"], tx["account_id"], tx["type"], format(tx["amount"], ","))

# 5) 예약 실행 : 지난 시각의 예약을 직접 넣고 실행 함수를 부릅니다.
sys.path.insert(0, "src")
import functions                            # noqa: E402

data["scheduled_transfers"].append({
    "schedule_id": "sch-900", "owner_id": "user-001", "from_account": "acc-001", "to_account": "reg-002",
    "amount": 10000, "scheduled_at": "2026-01-01T09:00:00+09:00", "status": "예약"})
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("예약 실행")
for line in functions.run_due_schedules():
    print("  ", line)

shutil.copy("data/initial_data.json", DATA)
