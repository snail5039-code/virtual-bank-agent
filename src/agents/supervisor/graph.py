# 노드를 연결해 그래프를 만듭니다.
#
#   START → supervisor ─┬─ 계좌 → account (계좌 에이전트 그래프) ─┐
#                       ├─ 카드 → card    (카드 에이전트 그래프) ─┤
#                       ├─ 결과 → result  (앞서 한 업무 결과 조회) ─┼→ END
#                       └─ 없음 → guide                           ─┘

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from agents.account.graph import account_graph
from agents.card.graph import card_graph
from agents.result.nodes import result_query_node
from agents.supervisor.nodes import guide_node, route_by_domain, supervisor_node
from state import BankState

builder = StateGraph(BankState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("account", account_graph)      # 계좌 에이전트 그래프를 노드로 넣습니다
builder.add_node("card", card_graph)            # 카드 에이전트 그래프를 노드로 넣습니다
builder.add_node("result", result_query_node)   # 후속 결과 조회 (처리 기록에서 찾음)
builder.add_node("guide", guide_node)

builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", route_by_domain, ["account", "card", "result", "guide"])
builder.add_edge("account", END)
builder.add_edge("card", END)
builder.add_edge("result", END)
builder.add_edge("guide", END)

bank_graph = builder.compile(checkpointer=InMemorySaver())
