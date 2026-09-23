# 이체 에이전트 그래프입니다. 계좌 에이전트 그래프 안에 노드로 들어갑니다.
#
#   START → extract → check ─┬─ 다 모임       → ready ─→ END
#              ↑             ├─ 후보 여러 개  → confirm ─→ check 로
#              │             ├─ 정보 부족     → ask ─────→ extract 로
#              └─────────────┤
#                            └─ 계좌 없음·취소 → fail ──→ END

from langgraph.graph import END, START, StateGraph

from agents.transfer.nodes import (route_after_ask, route_after_check, route_after_confirm,
                                   transfer_ask_node, transfer_check_node,
                                   transfer_confirm_node, transfer_extract_node,
                                   transfer_fail_node, transfer_ready_node)
from state import BankState

builder = StateGraph(BankState)

builder.add_node("transfer_extract", transfer_extract_node)
builder.add_node("transfer_check", transfer_check_node)
builder.add_node("transfer_confirm", transfer_confirm_node)
builder.add_node("transfer_ask", transfer_ask_node)
builder.add_node("transfer_ready", transfer_ready_node)
builder.add_node("transfer_fail", transfer_fail_node)

builder.add_edge(START, "transfer_extract")
builder.add_edge("transfer_extract", "transfer_check")
builder.add_conditional_edges("transfer_check", route_after_check,
                              ["transfer_fail", "transfer_confirm", "transfer_ask", "transfer_ready"])
builder.add_conditional_edges("transfer_confirm", route_after_confirm, ["transfer_fail", "transfer_check"])
builder.add_conditional_edges("transfer_ask", route_after_ask, ["transfer_fail", "transfer_extract"])
builder.add_edge("transfer_ready", END)
builder.add_edge("transfer_fail", END)

transfer_graph = builder.compile()
