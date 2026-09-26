# 2-3 처리 기록 · 저장 · 결과 안내 · 저장 실패 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤, 화면 출력과 data.json 의 requests 를 보여줍니다.
#
# 실행 : uv run python 테스트/2-3_저장_확인.py
#
# 확인할 것
#   1) 승인 → "승인되었습니다" 가 나오고, requests 에 req-0001 (완료) 이 남는다
#   2) 거절 → "진행하지 않았습니다" 가 나오고, requests 에 req-0002 (거절) 이 남는다
#   3) 저장 실패 : data.json 을 읽기 전용으로 바꾸고 승인하면
#                  "저장에 실패해 처리하지 못했습니다" 가 나오고 requests 는 늘지 않는다
#                  (로그에 "저장 실패 1/3 ~ 3/3" 이 남는다)
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다. 잔액은 아직 바뀌지 않습니다 (2-4).

import json
import os
import shutil
import stat
import subprocess
import sys

DATA = "data/data.json"


def run(inputs):
    result = subprocess.run(
        [sys.executable, "src/main.py"],
        input="\n".join(inputs + ["종료"]) + "\n",
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    print(result.stdout)
    print(result.stderr)


def show_requests():
    with open(DATA, encoding="utf-8") as f:
        requests = json.load(f)["requests"]
    print("requests %d건" % len(requests))
    for r in requests:
        print("  ", r["request_id"], r["task_type"], r["status"], r["content"])
    print()


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 승인, 2) 거절 =====")
run(["생활비에서 저축으로 10만원 보내줘", "응, 진행해",
     "생활비에서 저축으로 3만원 보내줘", "아니 안 할래"])
show_requests()

print("===== 3) 저장 실패 (data.json 읽기 전용) =====")
os.chmod(DATA, stat.S_IREAD)
try:
    run(["생활비에서 저축으로 5만원 보내줘", "승인"])
finally:
    os.chmod(DATA, stat.S_IREAD | stat.S_IWRITE)
show_requests()

shutil.copy("data/initial_data.json", DATA)
