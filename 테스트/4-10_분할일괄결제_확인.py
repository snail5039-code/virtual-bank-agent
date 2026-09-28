# 4-10 분할 결제 / 일괄 결제 (건별 저장) 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤 화면 출력과 data.json 을 보여줍니다.
#
# 실행 : uv run python 테스트/4-10_분할일괄결제_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 분할 결제 : 9월 생활비 신용카드 452,000원을 3개월로 → 할부 계획(card_installments)이 생기고
#                 첫 회차 150,668원만 지금 빠진다 (나머지 2원은 첫 회차에 붙음). 청구서는 일부 납부
#   2) 분할 중복 : 같은 청구서를 또 분할하면 "이미 분할 결제 중" 으로 끝난다
#   3) 개월 수   : 1개월, 24개월은 거절 (2~12개월)
#   4) 일괄 결제 : "카드값 전부 한 번에 내줘" → 처리안에 4건과 합계 → 승인 한 번
#                 여행 자금 잔액을 150,000원으로 낮춰 둡니다. 여행 9월분(138,000원)을 내면 잔액이 12,000원이 되어
#                 여행 8월분(45,000원)은 실패. 앞에서 낸 건은 저장된 채 남고, 뒤 건(생활비 8월분)은 계속 냅니다
#   5) 결과 안내 : 완료 / 실패 / 미처리 건수가 나온다
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
    for a in data["accounts"]:
        if a["owner_id"] == "user-001":
            print("  %s  %-6s %s원" % (a["account_id"], a["nickname"], format(a["balance"], ",")))
    for s in data["card_statements"]:
        print("  %s  %s %s  낸 %s / 남은 %s  %s" % (s["statement_id"], s["card_id"], s["billing_month"],
                                                  s["paid_amount"], s["remaining_amount"], s["status"]))
    print("  분할 :", data["card_installments"])
    print("  처리 기록 :", [(r["task_type"], r["status"]) for r in data["requests"]])
    print()


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 2) 3) 분할 결제 =====")
run(["9월 생활비 신용카드 값 3개월로 나눠 내줘", "1234", "승인",
     "9월 생활비 신용카드 값 3개월로 나눠 내줘",
     "9월 여행 신용카드 값 1개월 할부로 내줘",
     "9월 여행 신용카드 값 24개월로 나눠 내줘"])
show()

print("===== 4) 5) 일괄 결제 (여행 자금 잔액 150,000원) =====")
with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
next(a for a in data["accounts"] if a["account_id"] == "acc-003")["balance"] = 150000
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
run(["카드값 전부 한 번에 내줘", "1234", "승인"])
show()

shutil.copy("data/initial_data.json", DATA)
