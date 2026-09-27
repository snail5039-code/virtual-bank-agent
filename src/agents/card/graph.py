# 카드 에이전트 그래프입니다. supervisor 그래프 안에 노드로 들어갑니다.
#
#   START → card_router ─┬─ 조회              → card_query ─┐
#                        └─ 결제 / 설정 / 재발급 → card_todo  ─┴→ END

from langgraph.graph import END, START, StateGraph

from agents.card.nodes import card_query_node, card_router_node, card_todo_node, route_by_task
from state import BankState

builder = StateGraph(BankState)

builder.add_node("card_router", card_router_node)
builder.add_node("card_query", card_query_node)
builder.add_node("card_todo", card_todo_node)

builder.add_edge(START, "card_router")
builder.add_conditional_edges("card_router", route_by_task, ["card_query", "card_todo"])
builder.add_edge("card_query", END)
builder.add_edge("card_todo", END)

card_graph = builder.compile()
