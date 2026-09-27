# 카드 에이전트 그래프입니다. supervisor 그래프 안에 노드로 들어갑니다.
#
#   START → card_router ─┬─ 조회 → card_extract ─┬─ 카드 번호 → common_authenticate ─┐ (틀리면 다시 묻기)
#                        │                       └─ 그 밖 ───────────────────────────┴→ card_query ─┐
#                        └─ 결제 / 설정 / 재발급 → card_todo ─────────────────────────────────────────┴→ END

from langgraph.graph import END, START, StateGraph

from agents.card.nodes import (card_extract_node, card_query_node, card_router_node, card_todo_node,
                               route_after_authenticate, route_after_extract, route_by_task)
from agents.common.nodes import common_authenticate_node
from state import BankState

builder = StateGraph(BankState)

builder.add_node("card_router", card_router_node)
builder.add_node("card_extract", card_extract_node)
builder.add_node("common_authenticate", common_authenticate_node)
builder.add_node("card_query", card_query_node)
builder.add_node("card_todo", card_todo_node)

builder.add_edge(START, "card_router")
builder.add_conditional_edges("card_router", route_by_task, ["card_extract", "card_todo"])
builder.add_conditional_edges("card_extract", route_after_extract, ["common_authenticate", "card_query"])
builder.add_conditional_edges("common_authenticate", route_after_authenticate, ["common_authenticate", "card_query"])
builder.add_edge("card_query", END)
builder.add_edge("card_todo", END)

card_graph = builder.compile()
