# 카드 결제(요금) 에이전트 그래프입니다. 카드 에이전트 그래프 안에 노드로 들어갑니다.
#
#   START → billing_extract ─┬─ 요금 조회   → billing_fee       ─┐   (읽기만. 승인 없음)
#                            ├─ 명세서 조회 → billing_statement ─┤
#                            ├─ 결제        → billing_todo      ─┼→ END   (4-9 에서 결제 흐름으로 바뀝니다)
#                            └─ 알아듣지 못함 → billing_fail     ─┘

from langgraph.graph import END, START, StateGraph

from agents.billing.nodes import (billing_extract_node, billing_fail_node, billing_fee_node, billing_statement_node,
                                  billing_todo_node, route_after_extract)
from state import BankState

builder = StateGraph(BankState)

builder.add_node("billing_extract", billing_extract_node)
builder.add_node("billing_fee", billing_fee_node)
builder.add_node("billing_statement", billing_statement_node)
builder.add_node("billing_todo", billing_todo_node)
builder.add_node("billing_fail", billing_fail_node)

builder.add_edge(START, "billing_extract")
builder.add_conditional_edges("billing_extract", route_after_extract,
                              ["billing_fee", "billing_statement", "billing_todo", "billing_fail"])
builder.add_edge("billing_fee", END)
builder.add_edge("billing_statement", END)
builder.add_edge("billing_todo", END)
builder.add_edge("billing_fail", END)

billing_graph = builder.compile()
