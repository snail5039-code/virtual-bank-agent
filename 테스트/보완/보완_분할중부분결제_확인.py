# 12장 보완 — 분할 결제 중인 청구서의 부분 결제 막기 확인용입니다.
# 분할 중에 일부만 내면 남은 금액과 분할 계획의 회차 금액이 맞지 않게 되므로, 남은 금액을 다 낼 때만 받습니다.
#
# 실행 : uv run python 테스트/보완/보완_분할중부분결제_확인.py
#
# 확인할 것 (9월 생활비 신용카드 452,000원 / 8월 여행 신용카드 남은 45,000원)
#   1) 분할 걸기     : "9월 생활비 신용카드 값 3개월로 나눠 내줘" → 승인 → 첫 회차 150,668원, 남은 301,332원
#   2) 분할 중 부분  : "9월 생활비 신용카드 값 10만원만 내줘" → "분할 결제 중인 청구서입니다 ... 한 번에 다 낼 때만" 으로 끝난다
#   3) 분할 중 전체  : "9월 생활비 신용카드 값 전부 내줘" → 승인 → 납부 완료, 분할 계획도 끝(paid)
#   4) 다른 청구서   : "8월 여행 신용카드 값 1만원 내줘" → 분할이 아니므로 부분 결제가 그대로 된다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "9월 생활비 신용카드 값 3개월로 나눠 내줘", "1234", "승인",
    "9월 생활비 신용카드 값 10만원만 내줘",
    "9월 생활비 신용카드 값 전부 내줘", "승인",
    "8월 여행 신용카드 값 1만원 내줘", "승인",
    "종료",
]

shutil.copy("data/initial_data.json", DATA)
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
print("청구서")
for s in data["card_statements"]:
    print("  ", s["statement_id"], s["card_id"], s["billing_month"], "낸", format(s["paid_amount"], ","),
          "남은", format(s["remaining_amount"], ","), s["status"])
print("분할 계획")
for i in data["card_installments"]:
    print("  ", i["installment_id"], i["statement_id"], "%d/%d회" % (i["paid_count"], i["months"]), i["status"])
print("처리 기록")
for r in data["requests"]:
    print("  ", r["request_id"], r["task_type"], r["status"])

shutil.copy("data/initial_data.json", DATA)
