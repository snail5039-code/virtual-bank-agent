# 계좌 에이전트(2단)의 노드 함수입니다.
#
#   account_router : 계좌 요청이 조회 / 이체 / 설정 중 무엇인지 고릅니다
#   account_query  : 계좌 목록과 잔액을 보여줍니다
#   account_todo   : 설정은 아직 준비 중이라고 안내합니다
#   (이체는 이체 에이전트 그래프로 넘깁니다)

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import functions
import logger
from agents.account.prompts import account_prompt
from model import llm
from state import BankState


class AccountDecision(BaseModel):
    task: Literal["조회", "이체", "설정"] = Field(description="계좌 요청의 업무 종류")
    reason: str = Field(description="그 업무를 고른 이유")


llm_with_account_output = llm.with_structured_output(AccountDecision)


def account_router_node(state: BankState):
    log = logger.get_logger()
    with log.node("account_router"):
        result = llm_with_account_output.invoke([
            SystemMessage(content=account_prompt),
            HumanMessage(content=state["query"]),
        ])
        log.route(2, result.task, result.reason)

    return {"task": result.task}


def account_query_node(state: BankState):
    with logger.get_logger().node("account_query"):
        accounts = functions.get_accounts(functions.CURRENT_USER)

        lines = ["보유 계좌 %d개입니다." % len(accounts)]
        for account in accounts:
            lines.append("- %s (%s %s) : %s원" % (
                account["nickname"],
                account["bank_name"],
                account["account_number"],
                format(account["balance"], ","),
            ))
        # 합계는 Python 이 더합니다. LLM 이 계산하지 않습니다 (원칙 6).
        lines.append("총 잔액 : %s원" % format(sum(account["balance"] for account in accounts), ","))

    return {"answer": "\n".join(lines)}


def account_todo_node(state: BankState):
    with logger.get_logger().node("account_todo"):
        answer = "계좌 %s 업무는 아직 준비 중입니다." % state["task"]
    return {"answer": answer}


def route_by_task(state: BankState):
    # 고른 업무에 따라 다음 노드를 정합니다.
    if state["task"] == "조회":
        return "account_query"
    if state["task"] == "이체":
        return "transfer"
    return "account_todo"
