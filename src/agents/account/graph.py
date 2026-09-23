# 계좌 에이전트 그래프입니다. supervisor 그래프 안에 노드로 들어갑니다.
#
#   START → account_router ─┬─ 조회      → account_query ─┐
#                           └─ 이체·설정 → account_todo  ─┴→ END

from langgraph.graph import END, START, StateGraph

from agents.account.nodes import (account_query_node, account_router_node,
                                  account_todo_node, route_by_task)
from state import BankState

builder = StateGraph(BankState)

builder.add_node("account_router", account_router_node)
builder.add_node("account_query", account_query_node)
builder.add_node("account_todo", account_todo_node)

builder.add_edge(START, "account_router")
builder.add_conditional_edges("account_router", route_by_task, ["account_query", "account_todo"])
builder.add_edge("account_query", END)
builder.add_edge("account_todo", END)

account_graph = builder.compile()
