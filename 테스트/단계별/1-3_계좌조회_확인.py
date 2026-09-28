# 1-3 계좌 목록 + 잔액 조회 확인용입니다.
#
# 실행 : uv run python 테스트/단계별/1-3_계좌조회_확인.py
#
# 확인할 것
#   1) get_accounts 가 user-001 의 계좌만 돌려준다 (다른 사람 계좌가 안 섞인다)
#   2) 계좌 조회 요청은 계좌 → 조회 로 가서 목록과 잔액이 나온다
#   3) 이체·설정 요청은 계좌 → 이체 / 설정 으로 간다. 이체는 본인 확인, 설정은 새 이름을 묻고 멈춘다
#      (이 스크립트는 멈춘 곳까지만 봅니다. 끝까지 하는 확인은 2-4, 3-6 테스트)
#   4) 화면에 나온 잔액이 data.json 의 잔액과 같다

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import functions
from agents.supervisor.graph import bank_graph
from state import new_request

# ============================================================ 1) 함수만
print("1) get_accounts('user-001')")
accounts = functions.get_accounts("user-001")
for account in accounts:
    print("  ", account["owner_id"], account["account_id"], account["nickname"], account["balance"])
print("   다른 사람 계좌 섞임:", any(a["owner_id"] != "user-001" for a in accounts))
print()

# ============================================================ 2) 3) 그래프
THREAD = "test-1-3"


def run_one(number, query):
    # 요청마다 새 세션(thread_id)과 new_request 로 부릅니다. 앞 요청의 값이 섞이지 않게 하려는 것입니다.
    # 본인 확인·질문에서 멈추면 답이 아직 없으므로, 멈춘 질문과 경로를 보여주고 이 요청은 여기서 끝냅니다.
    # (멈춘 동안 2단이 고른 업무는 바깥 State 에 아직 없어서 안쪽 그래프의 State 에서 꺼냅니다)
    config = {"configurable": {"thread_id": "%s-%d" % (THREAD, number)}}
    result = bank_graph.invoke(new_request(query), config=config)
    print("요청 :", query)
    if "__interrupt__" in result:
        inner = bank_graph.get_state(config, subgraphs=True).tasks[0].state
        print("경로 :", result["domain"], "→", inner.values.get("task") if inner else None, " (여기서 멈춤)")
        print(result["__interrupt__"][0].value["text"])
    else:
        print("경로 :", result["domain"], "→", result.get("task"))
        print(result["answer"])
    print()


queries = [
    "잔액 알려줘",
    "내 계좌 목록 보여줘",
    "생활비 통장에서 저축으로 10만원 보내줘",
    "생활비 통장 이름 바꿔줘",
]

for number, query in enumerate(queries, start=1):
    run_one(number, query)
