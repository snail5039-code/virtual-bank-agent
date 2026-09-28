# 12장 보완 — 계좌 설정(3-6, 3-7, 3-8 예약 취소)에서 되묻기·후보 고르기 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤, 화면 출력과 data.json 을 보여줍니다.
#
# 실행 : uv run python 테스트/보완/보완_계좌설정되묻기_확인.py
#
# 확인할 것 (내 계좌 : 생활비 / 저축 / 여행 자금, 등록 계좌 : 동생 생활비 / 친구 민수)
#   1) 계좌 애매     : "가상은행 계좌 용도 바꿔줘" → 3개 중 고르기 → 2(저축) → 새 값 묻기 → "비상금" → 승인
#   2) 계좌 빠짐     : "계좌 별명 바꿔줘" → 어느 계좌 묻기 → "여행 자금" → 새 값 묻기 → "휴가비" → 승인
#   3) 등록 정보 빠짐 : "미래은행 계좌 등록해줘 별명은 친구 영희" → 계좌번호·예금주 묻기 → "210-11-223344 이영희" → 승인
#   4) 삭제 애매     : "친구 계좌 삭제해줘" → 친구 민수 / 친구 영희 중 고르기 → 1 → 승인
#   5) 예약 여러 건  : 저축으로 가는 예약 2건을 넣어 두고 "저축으로 가는 예약 취소해줘" → 고르기 → 2 → 승인
#   6) 묻는 중 다른 요청 : "생활비 계좌 이름 바꿔줘" → 새 값 묻기 → "잔액 보여줘" → 계좌 설정을 멈춘다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "가상은행 계좌 용도 바꿔줘", "2", "비상금", "1234", "승인",
    "계좌 별명 바꿔줘", "여행 자금", "휴가비", "승인",
    "미래은행 계좌 등록해줘 별명은 친구 영희", "210-11-223344 이영희", "승인",
    "친구 계좌 삭제해줘", "1", "승인",
    "저축으로 가는 예약 취소해줘", "2", "승인",
    "생활비 계좌 이름 바꿔줘", "잔액 보여줘",
    "종료",
]

shutil.copy("data/initial_data.json", DATA)
# 5) 에 쓸 예약 2건을 미리 넣어 둡니다.
with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
for number, day in [(1, "2099-01-01T09:00:00+09:00"), (2, "2099-01-02T09:00:00+09:00")]:
    data["scheduled_transfers"].append({
        "schedule_id": "sch-%03d" % number, "owner_id": "user-001", "from_account": "acc-001",
        "to_account": "acc-002", "amount": 10000 * number, "scheduled_at": day, "status": "예약"})
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
print("계좌 별명 / 용도")
for a in data["accounts"][:3]:
    print("  ", a["account_id"], a["nickname"], "/", a["purpose"])
print("등록 계좌")
for r in data["registered_accounts"]:
    print("  ", r["registered_id"], r["nickname"], r["bank_name"], r["account_number"], r["holder_name"])
print("예약")
for s in data["scheduled_transfers"]:
    print("  ", s["schedule_id"], s["amount"], s["status"])
print("처리 기록")
for r in data["requests"]:
    print("  ", r["request_id"], r["task_type"], r["status"])

shutil.copy("data/initial_data.json", DATA)
