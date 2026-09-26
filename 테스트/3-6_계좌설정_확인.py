# 3-6 계좌 이름·용도 변경 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤, 화면 출력과 data.json 의 계좌 별명·용도를 보여줍니다.
#
# 실행 : uv run python 테스트/3-6_계좌설정_확인.py
#
# 확인할 것
#   1) 별명 변경   : "여행 자금 계좌 이름을 휴가비로 바꿔줘" → 본인 확인 → 처리안 → 승인
#                    → 여행 자금 → 휴가비. 이어서 계좌 조회에도 휴가비로 나온다
#   2) 승인 전 수정 : "저축 계좌 용도를 비상금으로 바꿔줘" → "아니 목돈 모으기로" → 새 값만 바뀐 처리안 → 승인
#   3) 중복        : "휴가비 계좌 이름을 생활비로 바꿔줘" → 다른 계좌의 별명이라 불가
#   4) 길이        : 20자 넘는 이름 → 불가
#   5) 거절        : 변경 처리안에 "아니 안 할래" → 바뀌지 않는다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "여행 자금 계좌 이름을 휴가비로 바꿔줘", "1234", "승인",
    "내 계좌 목록 보여줘",
    "저축 계좌 용도를 비상금으로 바꿔줘", "아니 목돈 모으기로", "승인",
    "휴가비 계좌 이름을 생활비로 바꿔줘",
    "생활비 계좌 이름을 아주아주아주아주아주아주아주아주긴생활비통장이름으로 바꿔줘",
    "생활비 계좌 이름을 용돈으로 바꿔줘", "아니 안 할래",
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
print("계좌 별명 / 용도")
for a in data["accounts"][:3]:
    print("  ", a["account_id"], a["nickname"], "/", a["purpose"])
print("처리 기록")
for r in data["requests"]:
    print("  ", r["request_id"], r["task_type"], r["status"])

shutil.copy("data/initial_data.json", DATA)
