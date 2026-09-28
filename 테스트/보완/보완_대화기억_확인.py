# 12장 보완 — 대화 기억 (최근 5턴) 확인용입니다.
# 새 요청이 들어오면 rewrite 노드가 최근 대화를 보고 "그 카드", "그거", "거기서" 를 실제 이름으로 바꾼 뒤 평소처럼 처리합니다.
#
# 실행 : uv run python 테스트/보완/보완_대화기억_확인.py
#
# 확인할 것
#   1) "여행 카드 결제 계좌 알려줘" → "그 카드 잠가줘" → 여행 카드 잠금 처리안 → 인증 → 승인 → 여행 카드(card-002) locked
#   2) "그거 다시 풀어줘"          → 여행 카드 잠금 해제 처리안 → 승인 → 다시 active
#   3) "여행 자금 계좌 잔액 알려줘" → "거기서 저축으로 5만원 보내줘" → 여행 자금 → 저축 이체 처리안 → 승인
#                                    → 여행 자금 340,000 / 저축 2,330,000
#   4) "잔액 보여줘"               → 가리키는 말이 없으면 바꾸지 않는다
#   5) "가상은행 카드 보여줘"(6장) → "그 카드 잠가줘" → 어느 카드인지 분명하지 않으므로 바꾸지 않는다 → "어느 카드인지 말해 주세요" (아무 카드도 안 잠김)
#   6) 바꾼 문장은 로그(--debug)에 "다듬기  그 카드 잠가줘 → 여행 카드 잠가줘" 처럼 남는다
#
# --debug 로 켜서 노드 로그도 같이 받고, 화면에는 로그를 뺀 대화만 보여줍니다.
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import re
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "여행 카드 결제 계좌 알려줘",
    "그 카드 잠가줘", "1234", "승인",
    "그거 다시 풀어줘", "승인",
    "여행 자금 계좌 잔액 알려줘",
    "거기서 저축으로 5만원 보내줘", "승인",
    "잔액 보여줘",
    "가상은행 카드 보여줘",
    "그 카드 잠가줘",
    "종료",
]

shutil.copy("data/initial_data.json", DATA)
result = subprocess.run(
    [sys.executable, "src/main.py", "--debug"],
    input="\n".join(inputs) + "\n",
    capture_output=True, text=True, encoding="utf-8",
    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
)
log_line = re.compile(r"^\s*(>|━|\[분기)|^\s{10,}|^TURN ")
print("\n".join(line for line in result.stdout.splitlines() if not log_line.search(line)))
print(result.stderr)

print("다듬기 로그")
for line in result.stdout.splitlines():
    if "다듬기" in line:
        print("  ", line.strip())
print()

with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
print("카드 상태 (user-001)")
for c in data["cards"]:
    if c["owner_id"] == "user-001":
        print("  ", c["card_id"], c["name"], c["status"])
print("잔액")
for a in data["accounts"][:3]:
    print("  ", a["account_id"], a["nickname"], format(a["balance"], ","))
print("처리 기록")
for r in data["requests"]:
    print("  ", r["request_id"], r["task_type"], r["status"])

shutil.copy("data/initial_data.json", DATA)
