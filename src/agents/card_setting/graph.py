# 카드 설정 에이전트 그래프입니다. 카드 에이전트 그래프 안에 노드로 들어갑니다.
# 계좌 설정 그래프와 같은 모양입니다.
#
#   START → extract → check ─┬─ 할 수 없음 → fail → END           (카드를 못 정함 / 전이 불가 / 준비 중)
#              ↑             └─ 할 수 있음 → authenticate → propose → approve → interpret
#              │                                                      ↑         │
#              │                                                      └─ 모름 ──┤
#              └─────────────────────────────────────────────────────── 수정 ──┤
#                                          승인 → execute ─┐                    │
#                                     거절·취소 → reject  ─┴→ log_request → save → report → END

from langgraph.graph import END, START, StateGraph

from agents.card_setting.nodes import (card_setting_check_node, card_setting_execute_node, card_setting_extract_node,
                                       card_setting_fail_node, card_setting_propose_node,
                                       route_after_authenticate, route_after_check, route_after_interpret)
from agents.common.nodes import (common_approve_node, common_authenticate_node, common_interpret_node,
                                 common_log_request_node, common_reject_node,
                                 common_report_node, common_save_node)
from state import BankState

builder = StateGraph(BankState)

builder.add_node("card_setting_extract", card_setting_extract_node)
builder.add_node("card_setting_check", card_setting_check_node)
builder.add_node("common_authenticate", common_authenticate_node)
builder.add_node("card_setting_propose", card_setting_propose_node)
builder.add_node("common_approve", common_approve_node)
builder.add_node("common_interpret", common_interpret_node)
builder.add_node("card_setting_execute", card_setting_execute_node)
builder.add_node("common_reject", common_reject_node)
builder.add_node("common_log_request", common_log_request_node)
builder.add_node("common_save", common_save_node)
builder.add_node("common_report", common_report_node)
builder.add_node("card_setting_fail", card_setting_fail_node)

builder.add_edge(START, "card_setting_extract")
builder.add_edge("card_setting_extract", "card_setting_check")
builder.add_conditional_edges("card_setting_check", route_after_check, ["card_setting_fail", "common_authenticate"])
builder.add_conditional_edges("common_authenticate", route_after_authenticate,
                              ["card_setting_fail", "card_setting_propose", "common_authenticate"])
builder.add_edge("card_setting_propose", "common_approve")
builder.add_edge("common_approve", "common_interpret")
builder.add_conditional_edges("common_interpret", route_after_interpret,
                              ["card_setting_execute", "common_reject", "card_setting_extract", "common_approve"])
builder.add_edge("card_setting_execute", "common_log_request")
builder.add_edge("common_reject", "common_log_request")
builder.add_edge("common_log_request", "common_save")
builder.add_edge("common_save", "common_report")
builder.add_edge("common_report", END)
builder.add_edge("card_setting_fail", END)

card_setting_graph = builder.compile()
