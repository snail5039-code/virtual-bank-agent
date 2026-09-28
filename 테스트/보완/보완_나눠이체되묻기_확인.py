# 12장 보완 — 나눠 이체에서 모자란 줄만 되묻기 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤, 화면 출력과 data.json 의 잔액을 보여줍니다.
#
# 실행 : uv run python 테스트/보완/보완_나눠이체되묻기_확인.py
#
# 확인할 것 (초기 잔액 생활비 1,431,800 / 저축 2,280,000 / 여행 자금 390,000 / 동생 생활비(acc-004) 850,000)
#   1) 금액 빠짐   : "생활비에서 저축으로 10만원, 여행 자금으로도" → 입금 2 금액이 ? 로 나오고 여행 자금 금액을 묻는다
#                    → "5만원" → 처리안 총액 150,000원 → 승인
#   2) 이름 애매   : "저축에서 여행 자금으로 1만원, 생활비로 2만원" → 생활비 / 동생 생활비 중 고르기 → 2 → 승인
#   3) 둘 다       : "여행 자금에서 저축으로 1만원, 생활비로도" → 고르기 1 → 생활비 금액 묻기 → "3만원" → 승인
#   4) 묻는 중 취소 : "생활비에서 저축으로 1만원, 여행 자금으로도" → "취소" → 아무것도 안 바뀐다
#   끝 잔액 : 생활비 1,311,800 / 저축 2,360,000 / 여행 자금 410,000 / acc-004 870,000
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "생활비에서 저축으로 10만원, 여행 자금으로도 보내줘", "5만원", "1234", "승인",
    "저축에서 여행 자금으로 1만원, 생활비로 2만원 보내줘", "2", "승인",
    "여행 자금에서 저축으로 1만원, 생활비로도 보내줘", "1", "3만원", "승인",
    "생활비에서 저축으로 1만원, 여행 자금으로도 보내줘", "취소",
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
print("잔액")
for a in data["accounts"][:4]:
    print("  ", a["account_id"], a["nickname"], format(a["balance"], ","))
print("처리 기록")
for r in data["requests"]:
    print("  ", r["request_id"], r["task_type"], r["status"], r["content"].get("총액"))

shutil.copy("data/initial_data.json", DATA)
