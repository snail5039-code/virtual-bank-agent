# 4-9 전체 결제 / 부분 결제 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤 화면 출력과 data.json 을 보여줍니다.
#
# 실행 : uv run python 테스트/4-9_카드값결제_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 전체 결제 : 8월 생활비 신용카드 320,000원 → 카드의 결제 계좌(생활비)에서 빠지고 납부 완료가 된다
#   2) 부분 결제 : 9월 생활비 신용카드 10만원만 → 남은 금액만 줄고 일부 납부가 된다
#   3) 계좌 수정 : 처리안에서 "아니 저축에서" 라고 하면 저축 계좌로 바뀐 처리안이 다시 나온다
#   4) 거절 조건 : 이미 납부 완료 / 남은 금액보다 많이 / 여러 건이 걸림 / 잔액 부족
#   5) 거래 내역 : 계좌 거래 내역에 "카드값 ..." 출금이 남는다
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
    print("  카드값 출금 :", [(t["account_id"], t["amount"], t["merchant"]) for t in data["transactions"]
                             if (t["merchant"] or "").startswith("카드값")])
    print("  처리 기록 :", [(r["task_type"], r["status"]) for r in data["requests"]])
    print()


shutil.copy("data/initial_data.json", DATA)
print("===== 처음 상태 =====")
show()

print("===== 1) 2) 3) 전체 결제 / 부분 결제 / 계좌 수정 =====")
run(["8월 생활비 신용카드 값 내줘", "1234", "승인",
     "9월 생활비 신용카드 값 10만원만 내줘", "아니 저축에서", "승인"])
show()

print("===== 4) 거절 조건 =====")
# 잔액 부족을 보려고 여행 자금 잔액을 10,000원으로 낮춰 둡니다.
with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
next(a for a in data["accounts"] if a["account_id"] == "acc-003")["balance"] = 10000
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
run(["8월 생활비 신용카드 값 내줘",
     "8월 여행 신용카드 값 100만원 내줘",
     "카드값 내줘",
     "9월 여행 신용카드 값 내줘"])

shutil.copy("data/initial_data.json", DATA)
