# 12장 보완 — 번호 고르기에서 번호가 아닌 답을 쳤을 때 안내 확인용입니다.
# 번호가 아니면 LLM 으로 판단하지 않고, 같은 질문 위에 "현재 'OO' 업무 중입니다 ... '취소' 후 다시" 를 붙여 다시 묻습니다.
#
# 실행 : uv run python 테스트/보완_번호고르기안내_확인.py
#
# 확인할 것
#   1) 이체       : "저축에서 생활비로 1만원" → 후보 → "잔액 보여줘" → 현재 '이체' 업무 중 안내 + 같은 후보 → "취소"
#   2) 카드       : "신용카드 일시 잠금" → 후보 → "여행 카드 보여줘" → 현재 '카드 일시 잠금' 안내 → 2 → 인증 → 승인
#                   (번호를 고르면 안내가 사라지고 그대로 진행된다)
#   3) 계좌 설정  : "가상은행 계좌 용도 바꿔줘" → 후보 → "음" → 현재 '계좌 별명·용도 변경' 안내 → "취소"
#   4) 취소한 뒤  : "잔액 보여줘" → 새 요청으로 잘 처리된다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "저축에서 생활비로 1만원 보내줘", "잔액 보여줘", "취소",
    "신용카드 일시 잠금해줘", "여행 카드 보여줘", "2", "1234", "승인",
    "가상은행 계좌 용도 바꿔줘", "음", "취소",
    "잔액 보여줘",
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
print("카드 상태")
for c in data["cards"]:
    if c["owner_id"] == "user-001" and c["card_type"] == "credit":
        print("  ", c["card_id"], c["name"], c["status"])
print("처리 기록")
for r in data["requests"]:
    print("  ", r["request_id"], r["task_type"], r["status"])

shutil.copy("data/initial_data.json", DATA)
