# 12장 보완 — 카드 조회(4-1)를 은행별로 나눠 보여주기 확인용입니다.
#
# 실행 : uv run python 테스트/보완_은행별카드조회_확인.py
#
# 확인할 것 (지금 데이터의 user-001 카드는 모두 가상은행입니다)
#   1) 한 은행, 있음      : "가상은행 카드 보여줘" → 가상은행 카드만 (지금과 같음)
#   2) 한 은행, 없음      : "미래은행 카드 보여줘" → "미래은행 카드는 없습니다."
#   3) 여러 은행          : "가상은행이랑 미래은행 카드 보여줘" → [가상은행] 카드 목록 + "미래은행 카드는 없습니다."
#   4) 다른 조건과 같이    : "가상은행이랑 미래은행 신용카드 보여줘" → [가상은행] 신용카드 2장 + "미래은행에는 조건에 맞는 카드가 없습니다."
#   5) 은행을 말하지 않음 : "다른 은행 카드는?" → 뺄 은행을 모르므로 전체 ("OO은행 말고" 는 보완_다른은행카드_확인)
#   6) 다른 볼 것         : "가상은행이랑 미래은행 카드 결제 계좌 알려줘" → 은행별로 결제 계좌
# 조회만 하므로 data.json 은 바뀌지 않습니다. 요청마다 새 세션으로 부릅니다.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agents.supervisor.graph import bank_graph      # noqa: E402
from state import new_request                       # noqa: E402

queries = [
    "가상은행 카드 보여줘",
    "미래은행 카드 보여줘",
    "가상은행이랑 미래은행 카드 보여줘",
    "가상은행이랑 미래은행 신용카드 보여줘",
    "다른 은행 카드는?",
    "가상은행이랑 미래은행 카드 결제 계좌 알려줘",
]

for number, query in enumerate(queries, start=1):
    config = {"configurable": {"thread_id": "test-card-bank-%d" % number}}
    result = bank_graph.invoke(new_request(query), config=config)
    print("요청 :", query)
    print("조건 : 은행 =", result["card_filter"]["bank_names"] if result.get("card_filter") else None)
    print(result["answer"])
    print()
