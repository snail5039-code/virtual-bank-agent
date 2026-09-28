# 카드 에이전트 그래프입니다. supervisor 그래프 안에 노드로 들어갑니다.
#
#   START → card_router ─┬─ 조회 → card_extract ─┬─ 카드 번호 → common_authenticate ─┐ (틀리면 다시 묻기)
#                        │                       └─ 그 밖 ───────────────────────────┴→ card_query ─┐
#                        ├─ 설정 → card_setting (카드 설정 에이전트 그래프) ─┬─────────────────────────┤
#                        │               분실 신고 완료 + 재발급도 원함 → card_to_reissue ─┐           │
#                        ├─ 재발급 → reissue (카드 재발급 에이전트 그래프) ←───────────────┘ ──────────┤
#                        └─ 결제 → billing (카드 요금 에이전트 그래프) ─────────────────────────────────┴→ END

from langgraph.graph import END, START, StateGraph

from agents.card.billing.graph import billing_graph
from agents.card.nodes import (card_extract_node, card_query_node, card_router_node, card_to_reissue_node,
                               route_after_authenticate, route_after_extract, route_after_setting,
                               route_by_task)
from agents.card.setting.graph import card_setting_graph
from agents.card.reissue.graph import reissue_graph
from agents.common.nodes import common_authenticate_node
from state import BankState

builder = StateGraph(BankState)

builder.add_node("card_router", card_router_node)
builder.add_node("card_extract", card_extract_node)
builder.add_node("common_authenticate", common_authenticate_node)
builder.add_node("card_query", card_query_node)
builder.add_node("card_setting", card_setting_graph)   # 카드 설정 에이전트 그래프를 노드로 넣습니다
builder.add_node("reissue", reissue_graph)             # 카드 재발급 에이전트 그래프를 노드로 넣습니다
builder.add_node("card_to_reissue", card_to_reissue_node)
builder.add_node("billing", billing_graph)             # 카드 요금 에이전트 그래프를 노드로 넣습니다

builder.add_edge(START, "card_router")
builder.add_conditional_edges("card_router", route_by_task, ["card_extract", "card_setting", "reissue", "billing"])
builder.add_conditional_edges("card_extract", route_after_extract, ["common_authenticate", "card_query"])
builder.add_conditional_edges("common_authenticate", route_after_authenticate, ["common_authenticate", "card_query"])
builder.add_edge("card_query", END)
builder.add_conditional_edges("card_setting", route_after_setting, ["card_to_reissue", END])
builder.add_edge("card_to_reissue", "reissue")      # 정지 후 재발급 : 승인 2 는 재발급 그래프에서 받습니다
builder.add_edge("reissue", END)
builder.add_edge("billing", END)

card_graph = builder.compile()
