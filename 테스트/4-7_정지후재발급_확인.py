# 4-7 정지 후 재발급 연속 처리 (승인 2회) 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤 화면 출력과 data.json 을 보여줍니다.
#
# 실행 : uv run python 테스트/4-7_정지후재발급_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 한 요청     : "잃어버렸어 새로 만들어줘 집으로" 한 번에 분실 신고 승인 1 → 저장 → 재발급 승인 2 → 저장
#                   본인 확인은 처음 한 번만 묻는다. 재발급 처리안에 "앞 단계 : 분실 신고 완료" 가 나온다
#   2) 승인 2 거절 : 재발급을 거절해도 분실 정지는 저장되어 남는다
#   3) 승인 1 거절 : 분실 신고를 거절하면 재발급으로 넘어가지 않는다
#   4) 배송지 없음 : 배송지를 안 말하면 분실 신고는 되고, 재발급은 배송지 안내로 끝난다
#   5) 분실 신고만 : 재발급을 말하지 않으면 분실 신고만 하고 끝난다 (4-3 과 같음)
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
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


def show():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    for c in data["cards"]:
        if c["card_id"] in ("card-001", "card-002", "card-005", "card-006"):
            print("  %s  %-10s %s" % (c["card_id"], c["name"], c["status"]))
    for a in data["reissue_applications"]:
        print("  %s  %s  %s  %s" % (a["application_id"], a["card_id"], a["address_id"], a["status"]))
    print("  처리 기록 :", [(r["task_type"], r["status"]) for r in data["requests"]])
    print()


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 2) 한 요청으로 두 번 승인 / 승인 2 거절 =====")
run(["생활비 카드 잃어버렸어 새로 만들어줘 집으로", "1234", "승인", "승인",
     "여행 카드 도난당했어 분실 신고하고 재발급해줘 회사로", "승인", "거절"])
show()

print("===== 3) 4) 5) 승인 1 거절 / 배송지 없음 / 분실 신고만 =====")
run(["생활비 신용카드 잃어버렸어 재발급해줘 집으로", "1234", "거절",
     "생활비 신용카드 잃어버렸어 재발급도 해줘", "승인",
     "여행 신용카드 분실 신고해줘", "승인"])
show()

shutil.copy("data/initial_data.json", DATA)
