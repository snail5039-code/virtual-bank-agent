# 그래프의 State 와 노드 함수를 정의합니다.
#
# 지금(1-2)은 1단 Supervisor 만 있습니다.
#   supervisor  : 요청을 보고 계좌 / 카드 / 없음 중 하나를 고릅니다
#   account     : 계좌 쪽으로 왔다는 임시 응답 (1-3 에서 조회를 붙입니다)
#   card        : 아직 준비 중이라고 안내합니다
#   guide       : 은행 업무가 아닌 요청에 사용법을 안내합니다

from typing import Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import logger
from model import llm
from agents.supervisor.prompts import guide_message, supervisor_prompt


class BankState(TypedDict):
    query: str          # 사용자 입력
    domain: str         # supervisor 가 고른 분야
    reason: str         # 그렇게 고른 이유
    answer: str         # 사용자에게 보여줄 응답


class SupervisorDecision(BaseModel):
    domain: Literal["계좌", "카드", "없음"] = Field(description="요청이 속한 업무 분야")
    reason: str = Field(description="그 분야를 고른 이유")


llm_with_supervisor_output = llm.with_structured_output(SupervisorDecision)


def supervisor_node(state: BankState):
    log = logger.get_logger()
    with log.node("supervisor"):
        result = llm_with_supervisor_output.invoke([
            SystemMessage(content=supervisor_prompt),
            HumanMessage(content=state["query"]),
        ])
        log.route(1, result.domain, result.reason)

    return {"domain": result.domain, "reason": result.reason}


def account_node(state: BankState):
    with logger.get_logger().node("account"):
        answer = "계좌 업무로 분류됐습니다. (1-3 단계에서 조회를 연결합니다)"
    return {"answer": answer}


def card_node(state: BankState):
    with logger.get_logger().node("card"):
        answer = "카드 업무는 아직 준비 중입니다."
    return {"answer": answer}


def guide_node(state: BankState):
    with logger.get_logger().node("guide"):
        answer = guide_message
    return {"answer": answer}


def route_by_domain(state: BankState):
    # supervisor 가 고른 분야에 따라 다음 노드를 정합니다.
    if state["domain"] == "계좌":
        return "account"
    if state["domain"] == "카드":
        return "card"
    return "guide"
