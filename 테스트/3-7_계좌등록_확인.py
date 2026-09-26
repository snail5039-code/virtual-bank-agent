# 3-7 등록 계좌(상대 계좌 주소록) 등록·조회·삭제 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤, 화면 출력과 data.json 의 registered_accounts 를 보여줍니다.
#
# 실행 : uv run python 테스트/3-7_계좌등록_확인.py
#
# 확인할 것 (초기 등록 계좌 : 동생 생활비 / 친구 민수)
#   1) 조회     : "등록한 계좌 보여줘" → 본인 확인·승인 없이 2개가 나온다
#   2) 등록     : "미래은행 210-11-223344 이영희 계좌 등록해줘" → 본인 확인 → 처리안(별명은 예금주 이름) → 승인
#   3) 수정     : 등록 처리안에서 "별명은 영희로" → 별명만 바뀐 처리안 → 승인
#   4) 중복     : 같은 계좌번호를 또 등록 → "이미 등록한 계좌입니다"
#   5) 정보 부족 : "계좌 등록해줘" → 은행·계좌번호·예금주가 필요하다고 안내
#   6) 삭제     : "친구 민수 계좌 삭제해줘" → 처리안 → 승인 → 조회하면 빠져 있다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "등록한 계좌 보여줘",
    "미래은행 210-11-223344 이영희 계좌 등록해줘", "1234", "승인",
    "미래은행 210-22-334455 최지훈 계좌 등록해줘", "별명은 지훈이로", "승인",
    "미래은행 210-11-223344 이영희 계좌 등록해줘",
    "계좌 등록해줘",
    "친구 민수 계좌 삭제해줘", "승인",
    "등록 계좌 목록 보여줘",
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
print("registered_accounts")
for r in data["registered_accounts"]:
    print("  ", r["registered_id"], r["nickname"], r["bank_name"], r["account_number"], r["holder_name"], r["account_id"])
print("처리 기록")
for r in data["requests"]:
    print("  ", r["request_id"], r["task_type"], r["status"])

shutil.copy("data/initial_data.json", DATA)
