# 12장 보완 — 카드 이름 후보 고르기 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤, 화면 출력과 data.json 의 카드 상태를 보여줍니다.
#
# 실행 : uv run python 테스트/보완_카드후보고르기_확인.py
#
# 확인할 것 (user-001 카드 : 생활비 카드 / 여행 카드 / 생활비 신용카드 / 여행 신용카드 / 구 생활비 카드 / 구 여행 카드)
#   1) 조회, 정확한 이름 : "생활비 카드 결제 계좌 알려줘" → 생활비 카드 1장만 나온다 (전에는 3장)
#   2) 조회, 일부 이름   : "이름에 생활비 들어간 카드 보여줘" → 3장 모두 나온다 (읽기라 고르지 않음)
#   3) 설정, 후보 고르기 : "신용카드 일시 잠금해줘" → 생활비 신용카드 / 여행 신용카드 중 고르기
#                         → 번호가 아닌 답("음")이면 다시 묻는다 → 2 → 본인 확인 → 승인 → 여행 신용카드만 잠김
#   4) 고르다 취소       : "구 카드 해지해줘" → 후보 2장 → "취소" → 아무것도 안 바뀐다
#   5) 재발급, 후보 고르기 : "구 카드 재발급 배송지 회사로 바꿔줘" → 후보 2장 → 1 → 구 생활비 카드로 진행
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "생활비 카드 결제 계좌 알려줘",
    "이름에 생활비 들어간 카드 보여줘",
    "신용카드 일시 잠금해줘", "음", "2", "1234", "승인",
    "구 카드 해지해줘", "취소",
    "구 카드 재발급 배송지 회사로 바꿔줘", "1", "승인",
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
    if c["owner_id"] == "user-001":
        print("  ", c["card_id"], c["name"], c["status"])
print("재발급 신청")
for a in data["reissue_applications"]:
    print("  ", a["application_id"], a["card_id"], a["address_id"], a["status"])
print("처리 기록")
for r in data["requests"]:
    print("  ", r["request_id"], r["task_type"], r["status"])

shutil.copy("data/initial_data.json", DATA)
