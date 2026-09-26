# 계좌 설정 에이전트 그래프입니다. 계좌 에이전트 그래프 안에 노드로 들어갑니다.
#
#   START → extract ─┬─ 조회           → list → END                    (읽기만. 승인 없음)
#              ↑     └─ 변경·등록·삭제 → check ─┬─ 할 수 없음 → fail → END
#              │                                └─ 할 수 있음 → authenticate → propose → approve → interpret
#              │                                                                           ↑         │
#              │                                                                           └─ 모름 ──┤
#              └──────────────────────────────────────────────────────────────────────────── 수정 ──┤
#                                                               승인 → execute ─┐                    │
#                                                          거절·취소 → reject  ─┴→ log_request → save → report → END

from langgraph.graph import END, START, StateGraph

from agents.common.nodes import (common_approve_node, common_authenticate_node, common_interpret_node,
                                 common_log_request_node, common_reject_node,
                                 common_report_node, common_save_node)
from agents.setting.nodes import (route_after_authenticate, route_after_check, route_after_extract,
                                  route_after_interpret, setting_check_node, setting_list_node, setting_execute_node, setting_extract_node,
                                  setting_fail_node, setting_propose_node)
from state import BankState

builder = StateGraph(BankState)

builder.add_node("setting_extract", setting_extract_node)
builder.add_node("setting_list", setting_list_node)
builder.add_node("setting_check", setting_check_node)
builder.add_node("common_authenticate", common_authenticate_node)
builder.add_node("setting_propose", setting_propose_node)
builder.add_node("common_approve", common_approve_node)
builder.add_node("common_interpret", common_interpret_node)
builder.add_node("setting_execute", setting_execute_node)
builder.add_node("common_reject", common_reject_node)
builder.add_node("common_log_request", common_log_request_node)
builder.add_node("common_save", common_save_node)
builder.add_node("common_report", common_report_node)
builder.add_node("setting_fail", setting_fail_node)

builder.add_edge(START, "setting_extract")
builder.add_conditional_edges("setting_extract", route_after_extract, ["setting_list", "setting_check"])
builder.add_edge("setting_list", END)
builder.add_conditional_edges("setting_check", route_after_check, ["setting_fail", "common_authenticate"])
builder.add_conditional_edges("common_authenticate", route_after_authenticate,
                              ["setting_fail", "setting_propose", "common_authenticate"])
builder.add_edge("setting_propose", "common_approve")
builder.add_edge("common_approve", "common_interpret")
builder.add_conditional_edges("common_interpret", route_after_interpret,
                              ["setting_execute", "common_reject", "setting_extract", "common_approve"])
builder.add_edge("setting_execute", "common_log_request")
builder.add_edge("common_reject", "common_log_request")
builder.add_edge("common_log_request", "common_save")
builder.add_edge("common_save", "common_report")
builder.add_edge("common_report", END)
builder.add_edge("setting_fail", END)

setting_graph = builder.compile()
