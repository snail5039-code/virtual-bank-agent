# 12장 보완 — 분할 결제 남은 회차 자동 납부 확인용입니다.
# 예약 이체처럼, 다음 납부일(next_due_at)이 지난 회차를 켤 때·입력할 때 run_due_schedules 가 같이 냅니다.
#
# 실행 : uv run python 테스트/보완/보완_분할자동납부_확인.py
#
# 확인할 것 (9월 생활비 신용카드 452,000원 → 150,668 / 150,666 / 150,666, 9월 여행 신용카드 138,000원 → 46,000 × 3)
#   1) 분할 걸기   : 앱에서 두 청구서를 3개월로 분할 → 다음 납부일이 한 달 뒤로 잡힌다
#   2) 2회차       : 생활비 신용카드 분할의 납부일을 지난 시각으로 바꾸고 실행 → 2/3회, 150,666원, 다음 납부일 한 달 뒤
#   3) 3회차(끝)   : 한 번 더 → 3/3회, 남은 150,666원 → 청구서 납부 완료, 분할 끝(paid)
#   4) 잔액 부족   : 여행 자금 잔액을 1,000원으로 줄이고 여행 신용카드 분할 납부일을 지나게 → 실패, 내일 다시 시도
#                   바로 한 번 더 실행해도 (내일까지) 같은 실패가 또 뜨지 않는다
#   5) 기록·조회   : 처리 기록에 "분할 회차 결제" 완료·실패가 남고, 앱에서 "아까 분할 결제 됐어?" 로 볼 수 있다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, "src")
import functions            # noqa: E402

DATA = "data/data.json"
PAST = "2026-01-01T09:00:00+09:00"


def run_app(inputs):
    result = subprocess.run(
        [sys.executable, "src/main.py"],
        input="\n".join(inputs + ["종료"]) + "\n",
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    print(result.stdout)
    print(result.stderr)


def edit_data(change):
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    change(data)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_due(installment_id):
    def change(data):
        next(i for i in data["card_installments"] if i["installment_id"] == installment_id)["next_due_at"] = PAST
    edit_data(change)


def show():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    for i in data["card_installments"]:
        s = next(s for s in data["card_statements"] if s["statement_id"] == i["statement_id"])
        print("   %s  %s  %d/%d회  %s  다음 %s  | 청구서 남은 %s원 [%s]" % (
            i["installment_id"], i["statement_id"], i["paid_count"], i["months"], i["status"],
            i["next_due_at"][:16], format(s["remaining_amount"], ","), s["status"]))
    print("   잔액 :", {a["nickname"]: a["balance"] for a in data["accounts"][:3]})
    print()


def run_due(title):
    print(title)
    for line in functions.run_due_schedules():
        print("  ", line)
    show()


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 분할 걸기 =====")
run_app(["9월 생활비 신용카드 값 3개월로 나눠 내줘", "1234", "승인",
         "9월 여행 신용카드 값 3개월로 나눠 내줘", "승인"])
show()

make_due("inst-001")
run_due("===== 2) 생활비 신용카드 2회차 =====")
make_due("inst-001")
run_due("===== 3) 생활비 신용카드 3회차 (끝) =====")

edit_data(lambda data: next(a for a in data["accounts"] if a["account_id"] == "acc-003").update(balance=1000))
make_due("inst-002")
run_due("===== 4) 여행 신용카드 2회차 : 잔액 부족 =====")
run_due("===== 4) 바로 한 번 더 : 내일까지는 다시 안 뜬다 =====")

print("===== 5) 처리 기록과 조회 =====")
with open(DATA, encoding="utf-8") as f:
    for r in json.load(f)["requests"]:
        print("  ", r["request_id"], r["task_type"], r["status"], r["content"].get("청구서", ""))
print()
run_app(["아까 분할 결제 됐어?", "분할 결제한 거 다 됐어?"])

shutil.copy("data/initial_data.json", DATA)
