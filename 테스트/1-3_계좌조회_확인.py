# 1-3 계좌 목록 + 잔액 조회 확인용입니다.
#
# 실행 : uv run python 테스트/1-3_계좌조회_확인.py
#
# 확인할 것
#   1) get_accounts 가 user-001 의 계좌만 돌려준다 (다른 사람 계좌가 안 섞인다)
#   2) 계좌 조회 요청은 계좌 → 조회 로 가서 목록과 잔액이 나온다
#   3) 이체·설정 요청은 계좌 → 이체 / 설정 으로 가서 "준비 중" 이 나온다
#   4) 화면에 나온 잔액이 data.json 의 잔액과 같다

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import functions
from agents.supervisor.graph import bank_graph

# ============================================================ 1) 함수만
print("1) get_accounts('user-001')")
accounts = functions.get_accounts("user-001")
for account in accounts:
    print("  ", account["owner_id"], account["account_id"], account["nickname"], account["balance"])
print("   다른 사람 계좌 섞임:", any(a["owner_id"] != "user-001" for a in accounts))
print()

# ============================================================ 2) 3) 그래프
config = {"configurable": {"thread_id": "test-1-3"}}

queries = [
    "잔액 알려줘",
    "내 계좌 목록 보여줘",
    "생활비 통장에서 저축으로 10만원 보내줘",
    "생활비 통장 이름 바꿔줘",
]

for query in queries:
    result = bank_graph.invoke({"query": query}, config=config)
    print("요청 :", query)
    print("경로 :", result["domain"], "→", result.get("task"))
    print(result["answer"])
    print()
