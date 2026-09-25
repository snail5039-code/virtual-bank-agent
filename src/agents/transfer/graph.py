# 이체 에이전트 그래프입니다. 계좌 에이전트 그래프 안에 노드로 들어갑니다.
#
#   START → extract → check ─┬─ 다 모임        → propose → approve → interpret ─┬─ 승인      → approved → END
#              ↑       ↑     ├─ 후보 여러 개   → confirm → check 로     ↑        ├─ 거절·취소 → reject   → END
#              │       │     ├─ 정보 부족      → ask ───→ extract 로    └─ 모름 ─┤
#              │       │     └─ 계좌 없음·취소 → fail → END                      │
#              │       └──────────────────────────────── revise ←──── 수정 ─────┘

from langgraph.graph import END, START, StateGraph

from agents.common.nodes import common_approve_node, common_interpret_node, common_reject_node
from agents.transfer.nodes import (route_after_ask, route_after_check, route_after_confirm,
                                   route_after_interpret, transfer_approved_node,
                                   transfer_ask_node, transfer_check_node,
                                   transfer_confirm_node, transfer_extract_node,
                                   transfer_fail_node, transfer_propose_node,
                                   transfer_revise_node)
from state import BankState

builder = StateGraph(BankState)

builder.add_node("transfer_extract", transfer_extract_node)
builder.add_node("transfer_check", transfer_check_node)
builder.add_node("transfer_confirm", transfer_confirm_node)
builder.add_node("transfer_ask", transfer_ask_node)
builder.add_node("transfer_propose", transfer_propose_node)
builder.add_node("common_approve", common_approve_node)
builder.add_node("common_interpret", common_interpret_node)
builder.add_node("transfer_revise", transfer_revise_node)
builder.add_node("transfer_approved", transfer_approved_node)
builder.add_node("common_reject", common_reject_node)
builder.add_node("transfer_fail", transfer_fail_node)

builder.add_edge(START, "transfer_extract")
builder.add_edge("transfer_extract", "transfer_check")
builder.add_conditional_edges("transfer_check", route_after_check,
                              ["transfer_fail", "transfer_confirm", "transfer_ask", "transfer_propose"])
builder.add_conditional_edges("transfer_confirm", route_after_confirm, ["transfer_fail", "transfer_check"])
builder.add_conditional_edges("transfer_ask", route_after_ask, ["transfer_fail", "transfer_extract"])
builder.add_edge("transfer_propose", "common_approve")
builder.add_edge("common_approve", "common_interpret")
builder.add_conditional_edges("common_interpret", route_after_interpret,
                              ["transfer_approved", "common_reject", "transfer_revise", "common_approve"])
builder.add_edge("transfer_revise", "transfer_check")
builder.add_edge("transfer_approved", END)
builder.add_edge("common_reject", END)
builder.add_edge("transfer_fail", END)

transfer_graph = builder.compile()
