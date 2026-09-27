# 4-2 결제 계좌 / 카드 번호 / 멤버십 / 이용 내역 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤 화면 출력을 보여줍니다.
#
# 실행 : uv run python 테스트/4-2_카드상세조회_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 함수       : get_card_history 가 체크카드(transactions) + 신용카드(card_usages) 를 합치고,
#                   get_memberships 가 카드에 붙은 멤버십만 돌려준다
#   2) 결제 계좌  : 카드마다 결제 계좌(별명, 은행, 계좌번호)가 나온다. 본인 확인은 묻지 않는다
#   3) 멤버십     : 멤버십 이름, 등급, 포인트가 나온다
#   4) 이용 내역  : 기간·카드 조건으로 걸러지고 합계가 나온다
#   5) 카드 번호  : 본인 확인을 먼저 묻고, 틀리면 다시 묻고, 맞으면 전체 번호가 나온다
#                   같은 세션에서 다시 물으면 본인 확인 없이 나온다
#   6) 취소       : 카드 번호 본인 확인에서 "취소" 하면 번호를 보여주지 않는다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import functions

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


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 함수 =====")
debit = functions.get_card_history("user-001", ["card-001"])
credit = functions.get_card_history("user-001", ["card-005"])
print("  생활비 카드(체크) %d건 / 생활비 신용카드 %d건" % (len(debit), len(credit)))
print("  멤버십 :", [(m["card_id"], m["name"]) for m in functions.get_memberships("user-001", ["card-001", "card-005", "card-006"])])
print()

print("===== 2) 3) 4) 결제 계좌, 멤버십, 이용 내역 =====")
run(["신용카드 결제 계좌 알려줘",
     "카드 포인트 얼마나 있어?",
     "생활비 신용카드 7월 이용 내역 보여줘",
     "생활비 카드 사용 내역 보여줘"])

print("===== 5) 카드 번호 (틀림 → 맞음 → 같은 세션에서 다시) =====")
run(["여행 카드 번호 알려줘", "0000", "1234",
     "생활비 카드 번호 알려줘"])

print("===== 6) 카드 번호 취소 =====")
run(["카드 번호 보여줘", "취소"])

shutil.copy("data/initial_data.json", DATA)
