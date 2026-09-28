# 12장 보완 — 실시간 스케줄러 확인용입니다. (1분 30초쯤 걸립니다)
# 입력을 기다리는 동안에도 스케줄러 스레드가 30초마다 예약 이체·분할 회차를 확인해 시각이 되면 바로 실행하는지 봅니다.
#
# 실행 : uv run python 테스트/보완_실시간스케줄러_확인.py
#
# 미리 넣어 두는 것 (둘 다 켜고 35초 뒤가 시각)
#   sch-001  : 생활비 → 저축 10,000원 예약
#   inst-001 : 여행 신용카드 9월분 분할 1/3회 낸 상태, 2회차 46,000원 (여행 자금에서)
#
# 확인할 것
#   1) 켤 때      : 시각 전이라 아무것도 실행하지 않는다
#   2) 입력 없이   : "잔액 보여줘" 한 번 치고 75초 동안 아무것도 안 친다
#                   → 그동안 data.json 을 직접 열어 보면 예약은 완료, 분할은 2/3회로 이미 바뀌어 있다 (입력 없이 실행됨)
#                   → 거래 시각이 예약 시각에서 30초 안쪽이다
#   3) 화면       : 다음 입력("잔액 보여줘") 때 답보다 먼저 [예약 이체 완료] [분할 회차 완료] 가 나온다
#   4) 로그       : 스케줄러 줄은 실제로 실행한 한 번만 남는다 (30초마다 읽기만 한 것은 안 남음)
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta

DATA = "data/data.json"
LOG = "logs/%s.log" % date.today()


def load():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


shutil.copy("data/initial_data.json", DATA)
data = load()
due = (datetime.now().astimezone() + timedelta(seconds=35)).replace(microsecond=0)
data["scheduled_transfers"].append({
    "schedule_id": "sch-001", "owner_id": "user-001", "from_account": "acc-001", "to_account": "acc-002",
    "amount": 10000, "scheduled_at": due.isoformat(), "status": "예약"})
statement = next(s for s in data["card_statements"] if s["statement_id"] == "stmt-005")
statement.update(paid_amount=46000, remaining_amount=92000, status="partial", paid_account="acc-003")
data["card_installments"].append({
    "installment_id": "inst-001", "statement_id": "stmt-005", "card_id": "card-006", "total_amount": 138000,
    "months": 3, "paid_count": 1, "monthly_amount": 46000, "next_due_at": due.isoformat(), "status": "active"})
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("시각 :", due.strftime("%H:%M:%S"), "(켜고 35초 뒤)")

log_before = open(LOG, encoding="utf-8").read().count("--- 스케줄러") if os.path.exists(LOG) else 0

app = subprocess.Popen(
    [sys.executable, "src/main.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
app.stdin.write("잔액 보여줘\n")
app.stdin.flush()

print("입력 없이 75초 기다립니다 ...")
time.sleep(75)

data = load()
s = data["scheduled_transfers"][0]
i = data["card_installments"][0]
last = data["transactions"][-1]
print("2) 앱이 입력을 기다리는 중에 data.json 을 직접 열어 봄")
print("   예약 sch-001 :", s["status"])
print("   분할 inst-001 : %d/%d회" % (i["paid_count"], i["months"]))
print("   잔액 :", {a["nickname"]: a["balance"] for a in data["accounts"][:3]})
gap = (datetime.fromisoformat(last["occurred_at"]) - due).total_seconds()
print("   마지막 거래 시각 %s (예약 시각보다 %d초 뒤)" % (last["occurred_at"][11:19], gap))
print()

out, err = app.communicate("잔액 보여줘\n종료\n", timeout=120)
print("3) 화면")
print(out)
print(err)

log_after = open(LOG, encoding="utf-8").read().count("--- 스케줄러")
print("4) 로그의 스케줄러 줄 : %d번 남음" % (log_after - log_before))

shutil.copy("data/initial_data.json", DATA)
