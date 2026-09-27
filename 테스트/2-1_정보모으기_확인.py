# 2-1 대상 찾기 · 맥락 · 사용자 확인 · 부족 정보 질문 확인용입니다.
# main.py 를 켜고 입력을 차례로 넣은 뒤, 화면에 나온 결과를 보여줍니다.
#
# 실행 : uv run python 테스트/2-1_정보모으기_확인.py
#
# 확인할 것 (입력 순서대로)
#   1) 다 말하면 바로 처리안이 나온다                      생활비 → 저축 50,000원
#   2) 맥락 : "방금 받은 계좌" 가 저축이 되고, 금액을 묻는다  → 3만원 → 저축 → 여행 자금
#   3) 사용자 확인 : "가상은행 계좌" 는 후보 3개를 보여준다
#                    잘못된 번호(5)면 다시 묻고, 2 를 고르면 저축으로 정해진다
#   4) 부족 정보 : 입금 계좌를 묻고, 금액을 묻는다. "취소" 하면 멈춘다
#   5) 대상 없음 : "비상금 통장" 은 찾을 수 없다고 한다
#   6) 질문 칸에 알아낸 것이 같이 나온다 : 입금 : 생활비 / 금액 : 50,000원
#      출금도 생활비라고 하면 "출금 계좌와 입금 계좌가 같습니다" 로 멈춘다
#
# 2-2 부터 인증·승인이 붙어서, 처리안이 나오면 승인하거나 취소하는 입력을 넣었습니다.
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

inputs = [
    "생활비에서 저축으로 5만원 보내줘",                 # 1)
    "1234",                                             #    본인 확인 (세션에서 한 번만)
    "승인",
    "방금 받은 계좌에서 여행 자금으로 보내줘",           # 2)
    "3만원",
    "승인",
    "가상은행 계좌에서 여행 자금으로 1만원 보내줘",      # 3)
    "5",
    "2",
    "취소",                                             #    처리안에서 취소
    "생활비에서 보내줘",                                 # 4)
    "저축",
    "취소",
    "비상금 통장에서 저축으로 1만원 보내줘",             # 5)
    "5만원 이체해줘",                                    # 6)
    "생활비 계좌로 보내줘",
    "생활비",
    "종료",
]

shutil.copy("data/initial_data.json", DATA)
result = subprocess.run(
    [sys.executable, "src/main.py"],
    input="\n".join(inputs) + "\n",
    capture_output=True,
    text=True,
    encoding="utf-8",
    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
)

print("넣은 입력 :")
for text in inputs:
    print("  ", text)
print()
print("===== 화면 출력 =====")
print(result.stdout)
print(result.stderr)

shutil.copy("data/initial_data.json", DATA)
