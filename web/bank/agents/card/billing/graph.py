# 카드 결제(요금) 에이전트 그래프입니다. 카드 에이전트 그래프 안에 노드로 들어갑니다.
#
#   START → billing_extract ─┬─ 요금 조회   → billing_fee       → END   (읽기만. 승인 없음)
#              ↑             ├─ 명세서 조회 → billing_statement → END
#              │             ├─ 알아듣지 못함 → billing_fail    → END
#              │             └─ 결제 → billing_check ─┬─ 할 수 없음 → billing_fail → END
#              │                                      └─ 할 수 있음 → authenticate → propose → approve → interpret
#              │                                                                          ↑         │
#              │                                                                          └─ 모름 ──┤
#              └─────────────────────────────────────────────────────────────────────────── 수정 ──┤
#                                                              승인 → execute ─┐                    │
#                                                         거절·취소 → reject  ─┴→ log_request → save → report → END

from langgraph.graph import END, START, StateGraph

from agents.card.billing.nodes import (billing_check_node, billing_execute_node, billing_extract_node, billing_fail_node,
                                  billing_fee_node, billing_propose_node, billing_statement_node,
                                  route_after_authenticate, route_after_check, route_after_extract,
                                  route_after_interpret)
from agents.common.nodes import (common_approve_node, common_authenticate_node, common_interpret_node,
                                 common_log_request_node, common_reject_node,
                                 common_report_node, common_save_node)
from state import BankState

builder = StateGraph(BankState)

builder.add_node("billing_extract", billing_extract_node)
builder.add_node("billing_fee", billing_fee_node)
builder.add_node("billing_statement", billing_statement_node)
builder.add_node("billing_check", billing_check_node)
builder.add_node("common_authenticate", common_authenticate_node)
builder.add_node("billing_propose", billing_propose_node)
builder.add_node("common_approve", common_approve_node)
builder.add_node("common_interpret", common_interpret_node)
builder.add_node("billing_execute", billing_execute_node)
builder.add_node("common_reject", common_reject_node)
builder.add_node("common_log_request", common_log_request_node)
builder.add_node("common_save", common_save_node)
builder.add_node("common_report", common_report_node)
builder.add_node("billing_fail", billing_fail_node)

builder.add_edge(START, "billing_extract")
builder.add_conditional_edges("billing_extract", route_after_extract,
                              ["billing_fee", "billing_statement", "billing_check", "billing_fail"])
builder.add_edge("billing_fee", END)
builder.add_edge("billing_statement", END)
builder.add_conditional_edges("billing_check", route_after_check, ["billing_fail", "common_authenticate"])
builder.add_conditional_edges("common_authenticate", route_after_authenticate,
                              ["billing_fail", "billing_propose", "common_authenticate"])
builder.add_edge("billing_propose", "common_approve")
builder.add_edge("common_approve", "common_interpret")
builder.add_conditional_edges("common_interpret", route_after_interpret,
                              ["billing_execute", "common_reject", "billing_extract", "common_approve"])
builder.add_edge("billing_execute", "common_log_request")
builder.add_edge("common_reject", "common_log_request")
builder.add_edge("common_log_request", "common_save")
builder.add_edge("common_save", "common_report")
builder.add_edge("common_report", END)
builder.add_edge("billing_fail", END)

billing_graph = builder.compile()
