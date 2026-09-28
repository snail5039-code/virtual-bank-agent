# 4-4 별칭 변경 / 카드 등록·해지 / 비밀번호 변경 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤 화면 출력과 data.json, 로그를 보여줍니다.
#
# 실행 : uv run python 테스트/단계별/4-4_카드설정_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 별칭 변경   : 여행 카드 → 휴가 카드. 다른 카드와 겹치는 별칭(생활비 카드)은 거절
#   2) 비밀번호    : 본인 확인 뒤 새 비밀번호를 따로 묻는다. 처리안에는 **** 로 나온다
#                   숫자 4자리가 아니면 거절, 지금과 같으면 거절
#   3) 해지        : cancelled 가 되고 목록에서 지워지지 않는다. 해지된 카드는 더 못 바꾼다
#                   분실 정지 카드도 해지는 된다
#   4) 등록        : 미래은행 체크카드를 생활비 계좌로 등록. 이미 있는 번호, 정보가 빠진 요청은 거절
#   5) 로그        : 새 카드 비밀번호가 로그 파일에 남지 않는다
#   (12장 보완) 카드 비밀번호는 해시로 저장되므로, 목록에는 해시 앞부분과 "9876 이 맞는지" 를 보여준다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import json
import os
import shutil
import subprocess
import sys
from datetime import date

sys.path.insert(0, "src")
from functions.common import check_secret   # noqa: E402

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
            password = c["card_password"]
            print("  %s  %-12s %-10s %-6s %s  %s  9876=%s" % (c["card_id"], c["name"], c["status"], c["card_type"],
                                                            c["card_number"], (password or "None")[:12] + "…",
                                                            check_secret("9876", password)))
    print("  처리 기록 :", [(r["task_type"], r["status"]) for r in data["requests"]])
    print()


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 별칭 변경 =====")
run(["여행 카드 별칭을 휴가 카드로 바꿔줘", "1234", "승인",
     "휴가 카드 이름을 생활비 카드로 바꿔줘"])
show_cards()

print("===== 2) 비밀번호 변경 (틀린 형식 → 같은 번호 → 제대로) =====")
run(["생활비 카드 비밀번호 바꿔줘", "1234", "12a4",
     "생활비 카드 비밀번호 바꿔줘", "1111",
     "생활비 카드 비밀번호 바꿔줘", "9876", "승인"])
show_cards()

print("===== 3) 해지 =====")
run(["여행 신용카드 해지해줘", "1234", "승인",
     "여행 신용카드 잠가줘",
     "구 여행 카드 해지해줘", "승인"])
show_cards()

print("===== 4) 등록 =====")
run(["미래은행 체크카드 1234-5678-1234-5678 생활비 계좌로 등록해줘", "1234", "승인",
     "미래은행 체크카드 1234567812345678 생활비 계좌로 등록해줘",
     "카드 등록해줘",
     "미래은행 카드 보여줘"])
show_cards()

print("===== 5) 로그에 새 비밀번호가 남았나 =====")
with open("logs/%s.log" % date.today(), encoding="utf-8") as f:
    log = f.read()
print('  "9876" 이 로그에 %s' % ("있음 (문제)" if "9876" in log else "없음"))

shutil.copy("data/initial_data.json", DATA)
