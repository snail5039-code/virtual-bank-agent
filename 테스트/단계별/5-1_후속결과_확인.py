# 5-1 후속 결과 조회 ("아까 이체 됐어?") 확인용입니다.
# main.py 를 켜고 업무 몇 개를 한 뒤, 결과를 묻는 질문을 넣어 화면 출력을 보여줍니다.
#
# 실행 : uv run python 테스트/단계별/5-1_후속결과_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 기록 없음 : 아무것도 안 했을 때 "아까 이체 됐어?" → 처리한 기록이 없다
#   2) 이체      : 이체 → "아까 이체 됐어?" → 결과 로 가서 가장 최근 이체 기록 [완료] 과 내용이 나온다
#   3) 거절      : 카드 잠금을 거절 → "카드 잠근 거 됐어?" → [거절] 로 나온다
#   4) 여러 건   : "오늘 처리한 거 다 보여줘" → 최근 기록 여러 건
#   5) 재시작    : 프로그램을 껐다 켜도 원장(data.json)에 남아 있어 답할 수 있다
#   6) 새 요청   : "생활비에서 저축으로 1만원 이체해줘" 는 결과가 아니라 계좌 → 이체 로 간다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import os
import shutil
import subprocess
import sys

DATA = "data/data.json"


def run(inputs):
    result = subprocess.run(
        [sys.executable, "src/main.py", "--debug"],
        input="\n".join(inputs + ["종료"]) + "\n",
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    # --debug 로 켜서 1단 분류(1단 = 결과 / 계좌 …)도 화면에 같이 나옵니다.
    print(result.stdout)
    print(result.stderr)


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 기록 없음 =====")
run(["아까 이체 됐어?"])

print("===== 2) 3) 4) 이체 → 결과 / 잠금 거절 → 결과 / 여러 건 =====")
run(["생활비에서 저축으로 3만원 보내줘", "1234", "승인",
     "아까 이체 됐어?",
     "여행 카드 잠가줘", "거절",
     "방금 카드 잠근 거 됐어?",
     "오늘 처리한 거 다 보여줘"])

print("===== 5) 6) 재시작 뒤 / 새 요청은 이체로 =====")
run(["아까 이체 됐어?",
     "생활비에서 저축으로 1만원 이체해줘", "1234", "거절"])

shutil.copy("data/initial_data.json", DATA)
