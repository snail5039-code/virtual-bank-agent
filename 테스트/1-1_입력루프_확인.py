# 1-1 입력 루프 확인용입니다.
# main.py 를 켜고 입력을 자동으로 넣은 뒤, 화면에 나온 결과를 보여줍니다.
#
# 실행 : uv run python 테스트/1-1_입력루프_확인.py
#
# 확인할 것
#   - "안녕", "잔액 알려줘" 에 각각 응답이 나온다
#   - 빈 입력(엔터만)은 아무 반응이 없다
#   - "종료" 를 넣으면 "시스템을 종료합니다." 가 나오고 끝난다
#   - 종료 뒤에 넣은 "이건 안 나와야 함" 은 처리되지 않는다

import os
import subprocess
import sys

inputs = ["안녕", "", "잔액 알려줘", "종료", "이건 안 나와야 함"]

result = subprocess.run(
    [sys.executable, "src/main.py"],
    input="\n".join(inputs) + "\n",
    capture_output=True,
    text=True,
    encoding="utf-8",
    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
)

print("넣은 입력 :", inputs)
print()
print("===== 화면 출력 =====")
print(result.stdout)
print(result.stderr)
