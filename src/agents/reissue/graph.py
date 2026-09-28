# 카드 재발급 에이전트 그래프입니다. 카드 에이전트 그래프 안에 노드로 들어갑니다.
# 계좌 설정 그래프와 같은 모양입니다.
#
#   START → extract ─┬─ 조회 → list → END                             (읽기만. 승인 없음)
#              ↑     └─ 신청 → check ─┬─ 할 수 없음 → fail → END     (분실 정지 아님 / 기존 신청 있음 / 배송지 모름)
#              │                      └─ 할 수 있음 → authenticate → propose → approve → interpret
#              │                                                                 ↑         │
#              │                                                                 └─ 모름 ──┤
#              └────────────────────────────────────────────────────────────────── 수정 ──┤
#                                                     승인 → execute ─┐                    │
#                                                거절·취소 → reject  ─┴→ log_request → save → report → END

from langgraph.graph import END, START, StateGraph

from agents.common.nodes import (common_approve_node, common_authenticate_node, common_interpret_node,
                                 common_log_request_node, common_reject_node,
                                 common_report_node, common_save_node)
from agents.reissue.nodes import (reissue_check_node, reissue_execute_node, reissue_extract_node, reissue_fail_node,
                                  reissue_list_node, reissue_propose_node,
                                  route_after_authenticate, route_after_check, route_after_extract,
                                  route_after_interpret)
from state import BankState

builder = StateGraph(BankState)

builder.add_node("reissue_extract", reissue_extract_node)
builder.add_node("reissue_list", reissue_list_node)
builder.add_node("reissue_check", reissue_check_node)
builder.add_node("common_authenticate", common_authenticate_node)
builder.add_node("reissue_propose", reissue_propose_node)
builder.add_node("common_approve", common_approve_node)
builder.add_node("common_interpret", common_interpret_node)
builder.add_node("reissue_execute", reissue_execute_node)
builder.add_node("common_reject", common_reject_node)
builder.add_node("common_log_request", common_log_request_node)
builder.add_node("common_save", common_save_node)
builder.add_node("common_report", common_report_node)
builder.add_node("reissue_fail", reissue_fail_node)

builder.add_edge(START, "reissue_extract")
builder.add_conditional_edges("reissue_extract", route_after_extract, ["reissue_list", "reissue_check"])
builder.add_edge("reissue_list", END)
builder.add_conditional_edges("reissue_check", route_after_check, ["reissue_fail", "common_authenticate"])
builder.add_conditional_edges("common_authenticate", route_after_authenticate,
                              ["reissue_fail", "reissue_propose", "common_authenticate"])
builder.add_edge("reissue_propose", "common_approve")
builder.add_edge("common_approve", "common_interpret")
builder.add_conditional_edges("common_interpret", route_after_interpret,
                              ["reissue_execute", "common_reject", "reissue_extract", "common_approve"])
builder.add_edge("reissue_execute", "common_log_request")
builder.add_edge("common_reject", "common_log_request")
builder.add_edge("common_log_request", "common_save")
builder.add_edge("common_save", "common_report")
builder.add_edge("common_report", END)
builder.add_edge("reissue_fail", END)

reissue_graph = builder.compile()
