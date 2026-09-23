# 1-2 Supervisor 라우터 확인용입니다.
# 요청을 그래프에 넣고, supervisor 가 어느 분야를 골랐는지 보여줍니다.
#
# 실행 : uv run python 테스트/1-2_supervisor_확인.py
#
# 확인할 것
#   - 계좌 요청은 계좌, 카드 요청은 카드, 인사·잡담은 없음으로 간다
#   - 표의 "맞음" 칸이 전부 O 이다

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agents.supervisor.graph import bank_graph

# (요청, 기대하는 분야)
cases = [
    ("잔액 알려줘", "계좌"),
    ("생활비 통장에서 저축으로 10만원 보내줘", "계좌"),
    ("이번 달 거래 내역 보여줘", "계좌"),
    ("카드 분실 신고할래", "카드"),
    ("이번 달 카드값 얼마야", "카드"),
    ("카드 결제 계좌가 뭐야", "카드"),
    ("안녕", "없음"),
    ("오늘 날씨 어때", "없음"),
]

config = {"configurable": {"thread_id": "test-1-2"}}

ok_count = 0
for query, expected in cases:
    result = bank_graph.invoke({"query": query}, config=config)
    ok = result["domain"] == expected
    ok_count += ok
    print("%s  기대=%s  결과=%s  | %s" % ("O" if ok else "X", expected, result["domain"], query))
    print("     이유:", result["reason"])

print()
print("맞음 %d / %d" % (ok_count, len(cases)))
