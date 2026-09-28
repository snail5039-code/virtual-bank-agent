# 4-6 재발급 배송지 수정 / 신청 취소 (상태별 제한) 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤 화면 출력과 data.json 을 보여줍니다.
#
# 실행 : uv run python 테스트/4-6_재발급수정취소_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 제작중·배송중 : 구 생활비 카드(제작중), 구 여행 카드(배송중) 는 수정·취소가 안 된다 (승인까지 안 감)
#   2) 배송지 수정   : 접수 상태 신청은 집 → 회사 로 바뀐다. 같은 배송지로 바꾸면 거절
#   3) 신청 취소     : 접수 상태 신청은 취소됨이 된다. 목록에서 지우지 않는다. 카드의 분실 정지는 그대로다
#   4) 다시 신청     : 취소한 뒤에는 같은 카드로 다시 신청할 수 있다
#   5) 신청 없음     : 신청이 없는 카드를 취소하면 "진행 중인 재발급 신청이 없습니다"
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

print("===== 1) 제작중·배송중은 불가 =====")
run(["구 생활비 카드 재발급 배송지 회사로 바꿔줘",
     "구 여행 카드 재발급 신청 취소해줘"])

print("===== 2) 3) 4) 접수 상태 : 수정 → 같은 배송지 → 취소 → 다시 신청 =====")
run(["생활비 카드 분실 신고해줘", "1234", "승인",
     "생활비 카드 재발급해줘 집으로", "승인",
     "생활비 카드 재발급 배송지 회사로 바꿔줘", "승인",
     "생활비 카드 재발급 배송지 회사로 바꿔줘",
     "생활비 카드 재발급 신청 취소해줘", "승인",
     "생활비 카드 재발급해줘 집으로", "승인"])
show()

print("===== 5) 신청 없음 =====")
run(["여행 카드 재발급 취소해줘"])

shutil.copy("data/initial_data.json", DATA)
