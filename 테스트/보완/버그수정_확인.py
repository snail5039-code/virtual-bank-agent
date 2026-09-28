# 3단계 뒤 버그 수정 확인용입니다.
#
# 실행 : uv run python 테스트/보완/버그수정_확인.py
#
# 확인할 것
#   A) 오류 뒤 다음 입력 (가짜 LLM 으로 예외를 일부러 냅니다)
#      이체 요청 중 LLM 이 실패한 다음 "잔액 보여줘" 를 치면,
#      고치기 전 : 대기 판정 = question → 실패했던 이체 요청을 다시 실행 (query 가 이전 요청 그대로)
#      고친 뒤   : 대기 판정 = None → "잔액 보여줘" 를 새 요청으로 처리
#   B) 실제 LLM 으로
#      1) 승인 대기 중 다른 요청 : 처리안에 "내 계좌 잔액 보여줘" → 진행 중이던 요청을 멈췄다고 안내 → 다음 입력은 새 요청
#      2) 부족 정보 질문에 "취소할게" → 이체를 취소했습니다 (예전에는 "취소" 한 단어만 알아들음)
#      3) 본인 확인에 "그만할래"   → 본인 확인을 취소했습니다
#      4) 부족 정보 질문에 다른 요청 : "[출금] 돈을 보낼 계좌" 에 "내 계좌 잔액 보여줘"
#         → 진행 중이던 이체를 멈췄다고 안내 (예전에는 그 말을 답으로 처리해 다시 물음)
#   C) 거래 내역 날짜 형식
#      1) 타입 고정 : start_date 가 date 타입이라 "9월 1일" 은 들어오지 못하고 "2026-09-01" 만 받는다
#      2) 그래도 LLM 이 형식을 어겨 검증 오류가 나면(가짜 LLM) → 오류 대신 "날짜를 알아듣지 못했습니다" 안내
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import os
import shutil
import subprocess
import sys

DATA = "data/data.json"

A = r'''
import os, sys
os.environ.setdefault("GOOGLE_API_KEY", "fake")     # 가짜 LLM 만 쓰므로 실제 키가 필요 없습니다
sys.path.insert(0, "src")
from types import SimpleNamespace as NS
import agents.supervisor.nodes as sn, agents.account.nodes as an
calls = {"n": 0}
class Flaky:
    def invoke(self, msgs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("LLM 호출 실패 (가짜)")
        return NS(domain="계좌", reason="t")
class Query:
    def invoke(self, msgs):
        return NS(task="조회", reason="t")
sn.llm_with_supervisor_output = Flaky()
an.llm_with_account_output = Query()
import main, logger, data_store
log = logger.setup(); data_store.ensure()
for text in ["생활비에서 저축으로 10만원 보내줘", "내 계좌 잔액 보여줘"]:
    print(">>", text, "| 대기 판정 =", main.common_pending_check(main.bank_graph, main.config))
    try:
        main.respond(text, log)
    except Exception as e:
        print("   예외 :", e)
    print("   처리한 요청(query) =", main.bank_graph.get_state(main.config).values.get("query"))
'''

C = r'''
import os, sys
os.environ.setdefault("GOOGLE_API_KEY", "fake")
sys.path.insert(0, "src")
from types import SimpleNamespace as NS
import agents.supervisor.nodes as sn, agents.account.nodes as an
from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError
class Fixed:
    def __init__(self, value): self.value = value
    def invoke(self, msgs): return self.value
class BadDate:
    # structured output 이 날짜 형식 검증에 실패한 상황을 흉내 냅니다.
    def invoke(self, msgs): raise OutputParserException("날짜 형식 오류 (가짜)")

# 1) 타입 고정 : "9월 1일" 은 date 칸에 들어가지 못한다
try:
    an.HistoryFilter(start_date="9월 1일")
    print("   타입 고정 : 통과됨 (문제)")
except ValidationError:
    print("   타입 고정 : '9월 1일' 은 받지 않음 (ValidationError)")
print("   타입 고정 : '2026-09-01' 은 →", an.HistoryFilter(start_date="2026-09-01").start_date)

# 2) 검증 실패 → 오류 대신 안내
sn.llm_with_supervisor_output = Fixed(NS(domain="계좌", reason="t"))
an.llm_with_account_output = Fixed(NS(task="거래내역", reason="t"))
an.llm_with_history_output = BadDate()
import main, logger, data_store
log = logger.setup(); data_store.ensure()
print(">> 9월 1일부터 내역 보여줘")
print("  ", main.respond("9월 1일부터 내역 보여줘", log))
'''


def run(args, stdin=None):
    result = subprocess.run(
        [sys.executable] + args, input=stdin,
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    print(result.stdout)
    print(result.stderr)


shutil.copy("data/initial_data.json", DATA)

print("===== A) 오류 뒤 다음 입력 =====")
run(["-c", A])

print("===== B) 실제 LLM =====")
inputs = [
    "생활비에서 저축으로 10만원 보내줘", "1234", "내 계좌 잔액 보여줘",   # 1) 승인 대기 중 다른 요청
    "내 계좌 잔액 보여줘",
    "저축으로 보내줘", "취소할게",                                     # 2) 부족 정보 질문에 취소
    "종료",
]
run(["src/main.py"], "\n".join(inputs) + "\n")

inputs = ["생활비에서 저축으로 1만원 보내줘", "그만할래",              # 3) 본인 확인에 그만 (새 세션)
          "저축으로 보내줘", "내 계좌 잔액 보여줘",                   # 4) 부족 정보 질문에 다른 요청
          "종료"]
run(["src/main.py"], "\n".join(inputs) + "\n")

print("===== C) 거래 내역 날짜 형식 =====")
run(["-c", C])

shutil.copy("data/initial_data.json", DATA)
