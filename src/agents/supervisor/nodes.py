# 1단 Supervisor 의 노드 함수입니다.
#
#   supervisor  : 요청을 보고 계좌 / 카드 / 결과 / 없음 중 하나를 고릅니다
#                 결과 = 앞서 한 업무의 결과를 묻는 질문 → agents/result (5-1)
#   guide       : 은행 업무가 아닌 요청에 사용법을 안내합니다

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import logger
from model import llm
from agents.supervisor.prompts import guide_message, supervisor_prompt
from state import BankState


class SupervisorDecision(BaseModel):
    domain: Literal["계좌", "카드", "결과", "없음"] = Field(description="요청이 속한 업무 분야")
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
    if state["domain"] == "결과":
        return "result"
    return "guide"
