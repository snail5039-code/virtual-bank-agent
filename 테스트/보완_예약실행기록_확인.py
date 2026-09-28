# 12장 보완 — 예약 이체 (3-8) 확인용입니다.
#   예약은 금액을 정한 한 곳 이체만 받습니다 (조건부·나눠 이체 예약은 "한 곳씩 따로 예약" 안내).
#   예약이 실행되면 처리 기록(requests)에 "예약 이체 실행" 이 남아 "아까 이체 됐어?" 에 나옵니다.
#
# 실행 : uv run python 테스트/보완_예약실행기록_확인.py
#
# 확인할 것
#   1) 나눠 이체 예약 : "내일 9시에 생활비에서 저축으로 1만원, 여행 자금으로 2만원" → 금액을 묻지 않고 바로 한 곳씩 안내
#   2) 조건부 예약    : "내일 9시에 생활비에서 100만원 남기고 나머지 저축으로" → 같은 안내
#   3) 실행 기록      : 시각이 지난 예약 2건(성공 1 / 잔액 부족 1)을 넣고 켜면 둘 다 실행되고,
#                       requests 에 "예약 이체 실행" 완료 1건 · 실패 1건(실패 사유 포함)이 남는다
#   4) 결과 조회      : "예약 이체 된 거 다 보여줘" → 두 기록이 나온다 / "아까 이체 됐어?" → 가장 최근 예약 실행 기록
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "내일 9시에 생활비에서 저축으로 1만원, 여행 자금으로 2만원 보내줘",
    "내일 9시에 생활비에서 100만원 남기고 나머지 저축으로 보내줘",
    "예약 이체 된 거 다 보여줘",
    "아까 이체 됐어?",
    "종료",
]

shutil.copy("data/initial_data.json", DATA)
# 3) 에 쓸 지난 예약 2건. 두 번째는 잔액보다 커서 실패합니다.
with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
data["scheduled_transfers"] += [
    {"schedule_id": "sch-001", "owner_id": "user-001", "from_account": "acc-001", "to_account": "acc-002",
     "amount": 10000, "scheduled_at": "2026-01-01T09:00:00+09:00", "status": "예약"},
    {"schedule_id": "sch-002", "owner_id": "user-001", "from_account": "acc-003", "to_account": "reg-002",
     "amount": 99990000, "scheduled_at": "2026-01-01T10:00:00+09:00", "status": "예약"},
]
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

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
print("예약")
for s in data["scheduled_transfers"]:
    print("  ", s["schedule_id"], s["amount"], s["status"])
print("처리 기록")
for r in data["requests"]:
    print("  ", r["request_id"], r["task_type"], r["status"], r["content"])

shutil.copy("data/initial_data.json", DATA)
