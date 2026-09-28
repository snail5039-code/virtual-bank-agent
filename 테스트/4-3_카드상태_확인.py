# 4-3 분실 신고 / 일시 잠금 / 잠금 해제 (상태 전이 검증) 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤 화면 출력과 data.json 을 보여줍니다.
#
# 실행 : uv run python 테스트/4-3_카드상태_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 잠금 → 해제 : 본인 확인 → 처리안 → 승인 뒤 상태가 바뀐다. 두 번째부터는 본인 확인을 묻지 않는다
#   2) 같은 상태   : 이미 잠긴 카드를 또 잠그면 "이미 일시 잠금 상태" 로 끝난다 (승인까지 안 감)
#   3) 분실 신고   : 사유(도난)와 신고 시각이 남고 분실 정지가 된다
#   4) 전이 불가   : 분실 정지 카드는 잠금 해제할 수 없다 (재발급 안내)
#   5) 여러 장     : "신용카드" 처럼 여러 장이 걸리면 후보를 보여주고 번호로 고르게 한다 (12장 보완)
#                   "생활비 카드" 는 이름이 정확히 같은 1장으로 정해진다
#   6) 거절        : 거절하면 상태가 바뀌지 않는다
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


def show_cards():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    for c in data["cards"]:
        if c["owner_id"] == "user-001":
            print("  %s  %-10s %s  %s" % (c["card_id"], c["status"], c["report_reason"], c["reported_at"]))
    print("  처리 기록 :", [(r["task_type"], r["status"]) for r in data["requests"]])
    print()


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 2) 잠금 → 또 잠금 → 해제 =====")
run(["여행 카드 잠가줘", "1234", "승인",
     "여행 카드 잠가줘",
     "여행 카드 잠금 풀어줘", "승인"])
show_cards()

print("===== 3) 4) 5) 분실 신고, 전이 불가, 여러 장 =====")
run(["생활비 카드 도난당했어 신고해줘", "1234", "승인",
     "구 여행 카드 잠금 해제해줘",
     "신용카드 잠가줘"])
show_cards()

print("===== 6) 거절 =====")
run(["여행 신용카드 일시 잠금해줘", "1234", "거절"])
show_cards()

shutil.copy("data/initial_data.json", DATA)
