# 4-8 요금 조회 / 명세서 조회 확인용입니다.
#
# 실행 : uv run python 테스트/단계별/4-8_요금명세서_확인.py
#
# 확인할 것
#   1) 함수       : get_statements 가 카드·청구 월로 거르고, get_statement_items 가 items 를 card_usages 로 바꾼다
#   2) 요금 조회  : 낼 돈이 남은 청구서(미납·일부 납부)만 나오고 남은 금액 합계가 나온다. 납부 완료는 빠진다
#   3) 명세서     : 청구서 하나와 상세 내역(날짜, 가맹점, 금액)이 나온다. 상세 내역 합이 청구 총액과 같다
#                   청구 월을 안 말하면 가장 최근 달 명세서가 나온다
#   4) 체크카드   : 체크카드는 청구서가 없다
#   5) 결제       : 결제 요청은 카드 → 결제 → 결제 로 간다. 8월 청구서가 2건이라 다시 요청하게 한다 (결제 자체는 4-9 테스트)
# 조회만 하므로 인증·승인이 없고 data.json 은 바뀌지 않습니다.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import functions
from agents.supervisor.graph import bank_graph
from state import new_request

# ============================================================ 1) 함수만
print("1) 함수")
statements = functions.get_statements("user-001")
print("   청구서 %d건 :" % len(statements), [(s["statement_id"], s["billing_month"]) for s in statements])
s = functions.get_statements("user-001", ["card-005"], "2026-08")[0]
items = functions.get_statement_items("user-001", s)
print("   %s 상세 %d건, 합계 %s / 청구 총액 %s" % (s["statement_id"], len(items), sum(u["amount"] for u in items), s["total_amount"]))
print()

# ============================================================ 2) ~ 5) 그래프
queries = [
    "카드값 얼마 내야 돼?",
    "여행 신용카드 요금 알려줘",
    "8월 생활비 신용카드 명세서 보여줘",
    "여행 신용카드 명세서 보여줘",
    "생활비 카드 명세서 보여줘",
    "8월 카드값 결제해줘",
]

for i, query in enumerate(queries):
    result = bank_graph.invoke(new_request(query), config={"configurable": {"thread_id": "test-4-8-%d" % i}})
    print("요청 :", query)
    print("경로 :", result["domain"], "→", result.get("task"), "→", (result.get("billing_info") or {}).get("action"))
    print(result["answer"])
    print()
