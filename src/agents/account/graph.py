# 계좌 에이전트 그래프입니다. supervisor 그래프 안에 노드로 들어갑니다.
#
#   START → account_router ─┬─ 조회     → account_query              ─┐
#                           ├─ 거래내역 → account_history            ─┤
#                           ├─ 이체     → transfer (이체 에이전트 그래프) ─┼→ END
#                           └─ 설정     → account_setting (설정 에이전트 그래프) ─┘

from langgraph.graph import END, START, StateGraph

from agents.setting.graph import setting_graph
from agents.transfer.graph import transfer_graph
from agents.account.nodes import (account_history_node, account_query_node,
                                  account_router_node, route_by_task)
from state import BankState

builder = StateGraph(BankState)

builder.add_node("account_router", account_router_node)
builder.add_node("account_query", account_query_node)
builder.add_node("account_history", account_history_node)
builder.add_node("transfer", transfer_graph)      # 이체 에이전트 그래프를 노드로 넣습니다
builder.add_node("account_setting", setting_graph)  # 설정 에이전트 그래프를 노드로 넣습니다

builder.add_edge(START, "account_router")
builder.add_conditional_edges("account_router", route_by_task, ["account_query", "account_history", "transfer", "account_setting"])
builder.add_edge("account_query", END)
builder.add_edge("account_history", END)
builder.add_edge("transfer", END)
builder.add_edge("account_setting", END)

account_graph = builder.compile()
