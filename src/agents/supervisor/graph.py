# 노드를 연결해 그래프를 만듭니다.
#
#   START → supervisor ─┬─ 계좌 → account (계좌 에이전트 그래프) ─┐
#                       ├─ 카드 → card    (카드 에이전트 그래프) ─┤
#                       ├─ 결과 → result  (앞서 한 업무 결과 조회) ─┼→ END
#                       └─ 없음 → guide                           ─┘
#
#   도메인 반송 (5-3) : account / card 가 "내 도메인 아님" 으로 끝나면
#                       → bounce (반대쪽으로 1회) → card / account
#                       → 두 번째도 아니면 bounce_fail (안내)

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agents.account.graph import account_graph
from agents.card.graph import card_graph
from agents.result.nodes import result_query_node
from agents.supervisor.nodes import (bounce_fail_node, bounce_node, guide_node, route_after_domain, route_by_domain,
                                     supervisor_node)
from state import BankState

builder = StateGraph(BankState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("account", account_graph)      # 계좌 에이전트 그래프를 노드로 넣습니다
builder.add_node("card", card_graph)            # 카드 에이전트 그래프를 노드로 넣습니다
builder.add_node("result", result_query_node)   # 후속 결과 조회 (처리 기록에서 찾음)
builder.add_node("guide", guide_node)
builder.add_node("bounce", bounce_node)             # 도메인 반송 (1회)
builder.add_node("bounce_fail", bounce_fail_node)

builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", route_by_domain, ["account", "card", "result", "guide"])
# 2단이 "내 도메인 아님" 으로 나오면 반송, 아니면 끝
builder.add_conditional_edges("account", route_after_domain, ["bounce", "bounce_fail", END])
builder.add_conditional_edges("card", route_after_domain, ["bounce", "bounce_fail", END])
builder.add_conditional_edges("bounce", route_by_domain, ["account", "card", "result", "guide"])
builder.add_edge("bounce_fail", END)
builder.add_edge("result", END)
builder.add_edge("guide", END)

bank_graph = builder.compile(checkpointer=InMemorySaver())
