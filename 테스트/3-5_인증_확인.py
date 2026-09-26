# 3-5 인증(본인 확인) 확인용입니다.
# main.py 를 켜고 입력을 넣은 뒤, 화면 출력과 로그 파일을 보여줍니다.
#
# 실행 : uv run python 테스트/3-5_인증_확인.py
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 처음 이체   : 처리안 전에 본인 확인을 묻는다. 틀리면(0000) "일치하지 않습니다 (1/3)" 로 다시 묻고
#                    맞으면(1234) 처리안이 나온다
#   2) 같은 세션   : 두 번째 이체는 본인 확인을 묻지 않고 바로 처리안이 나온다
#   3) 3번 실패    : 새로 켠 프로그램(새 세션)에서 3번 틀리면 멈춘다
#   4) 취소        : 본인 확인에서 "취소" 하면 멈춘다
#   5) 로그        : 로그 파일에 입력한 비밀번호가 남지 않고 **** 로 남는다
#   6) 조회        : 잔액 조회는 본인 확인 없이 된다 (쓰기만 인증)
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import os
import shutil
import subprocess
import sys
from datetime import date

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

print("===== 1) 처음 이체, 2) 같은 세션, 6) 조회 =====")
run(["생활비에서 저축으로 1만원 보내줘", "0000", "1234", "승인",
     "생활비에서 저축으로 2만원 보내줘", "승인",
     "내 계좌 잔액 보여줘"])

print("===== 3) 3번 실패 (새 세션) =====")
run(["생활비에서 저축으로 1만원 보내줘", "0000", "1111", "9999"])

print("===== 4) 취소 =====")
run(["생활비에서 저축으로 1만원 보내줘", "취소"])

print("===== 5) 로그에 비밀번호가 남았나 =====")
with open("logs/%s.log" % date.today(), encoding="utf-8") as f:
    log = f.read()
for word in ['"1234"', '"0000"', '"1111"', '"9999"']:
    print("  %s 가 로그에 %s" % (word, "있음 (문제)" if word in log else "없음"))
print('  "****" 가 로그에 %s' % ("있음" if '"****"' in log else "없음"))

shutil.copy("data/initial_data.json", DATA)
