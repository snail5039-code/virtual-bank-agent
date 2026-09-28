# 4-5 재발급 신청 + 신청 조회 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤 화면 출력과 data.json 을 보여줍니다.
#
# 실행 : uv run python 테스트/4-5_재발급_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 조회       : 신청 목록(카드, 배송지, 상태, 신청일)이 나온다. 본인 확인은 묻지 않는다
#   2) 분실 아님  : 사용 가능한 카드는 "먼저 분실 신고를 해 주세요" 로 끝난다
#   3) 기존 신청  : 이미 신청이 있는 카드(구 생활비 카드, 제작중)는 새로 만들지 않고 기존 신청을 안내한다
#   4) 신청       : 분실 신고한 뒤 재발급 신청 → 본인 확인 → 처리안 → 승인 → [접수] 로 들어간다
#                   배송지를 안 말하면 배송지를 묻는 안내가 나온다
#                   신청해도 카드의 분실 정지는 그대로다
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
    card = next(c for c in data["cards"] if c["card_id"] == "card-001")
    print("  생활비 카드 상태 :", card["status"])
    for a in data["reissue_applications"]:
        print("  %s  %s  %s  %s" % (a["application_id"], a["card_id"], a["address_id"], a["status"]))
    print("  처리 기록 :", [(r["task_type"], r["status"]) for r in data["requests"]])
    print()


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 2) 3) 조회, 분실 아님, 기존 신청 =====")
run(["재발급 신청 내역 보여줘",
     "여행 카드 재발급해줘 집으로",
     "구 생활비 카드 재발급해줘 집으로"])

print("===== 4) 분실 신고 → 재발급 신청 (배송지 빠짐 → 회사로) =====")
run(["생활비 카드 잃어버렸어 분실 신고해줘", "1234", "승인",
     "생활비 카드 재발급해줘",
     "생활비 카드 재발급해줘 회사로", "승인",
     "재발급 어떻게 됐어?"])
show()

shutil.copy("data/initial_data.json", DATA)
