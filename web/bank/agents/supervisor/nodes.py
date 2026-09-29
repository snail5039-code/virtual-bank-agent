# 1단 Supervisor 의 노드 함수입니다.
#
#   rewrite     : 최근 대화를 보고 "그거", "그 카드" 같은 말을 실제 이름으로 바꿉니다 (대화 기억, 12장 보완)
#   supervisor  : 요청을 보고 계좌 / 카드 / 결과 / 없음 중 하나를 고릅니다
#                 결과 = 앞서 한 업무의 결과를 묻는 질문 → agents/result (5-1)
#   guide       : 은행 업무가 아닌 요청에 사용법을 안내합니다
#   bounce      : 2단이 "내 도메인 아님" 을 고르면 반대쪽 도메인으로 한 번 다시 보냅니다 (5-3)
#   bounce_fail : 반송한 뒤에도 또 아니면 안내로 끝냅니다

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END
from pydantic import BaseModel, Field

import logger
from model import llm
from agents.supervisor.prompts import guide_message, rewrite_prompt, supervisor_prompt
from state import BankState


class RewrittenRequest(BaseModel):
    query: str = Field(description="가리키는 말을 실제 이름으로 바꾼 요청. 바꿀 것이 없으면 새 요청 그대로")


llm_with_rewrite_output = llm.with_structured_output(RewrittenRequest)


def rewrite_node(state: BankState):
    # 새 요청일 때만 옵니다 (그래프 START 바로 다음). "승인", "2", 비밀번호 같은 답은 멈춘 곳에서 이어가므로 여기를 지나지 않습니다.
    # 최근 대화가 없으면 LLM 을 부르지 않고 그대로 둡니다.
    # 바꾼 문장은 query 와 request_text 에 넣습니다. 뒤의 노드들은 대화 기록을 몰라도 평소처럼 처리합니다.
    history = state.get("history") or []
    if not history:
        return {}
    log = logger.get_logger()
    with log.node("rewrite"):
        lines = []
        for number, turn in enumerate(history, start=1):
            lines.append("%d) 사용자: %s" % (number, turn["request"]))
            lines.append("   답: %s" % turn["answer"])
        result = llm_with_rewrite_output.invoke([
            SystemMessage(content=rewrite_prompt.format(history="\n".join(lines))),
            HumanMessage(content=state["query"]),
        ])
        query = result.query.strip()
        if not query or query == state["query"]:
            log.detail("다듬기  바꿀 것 없음")
            return {}
        log.detail("다듬기  %s → %s" % (state["query"], query))
    return {"query": query, "request_text": query}


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


# ---------------------------------------------------------------- 도메인 반송 (5-3)
# 2단이 "내 도메인 아님" (계좌 쪽 "카드 업무" / 카드 쪽 "계좌 업무") 을 고르면 반대쪽으로 한 번만 다시 보냅니다.
# 분야가 계좌·카드 둘이라 LLM 을 다시 부르지 않고 바로 넘깁니다. 두 번째도 아니면 오가지 않고 안내로 끝냅니다.
BOUNCE = {"카드 업무": "카드", "계좌 업무": "계좌"}


def bounce_node(state: BankState):
    log = logger.get_logger()
    with log.node("bounce"):
        domain = BOUNCE[state["task"]]
        log.route(1, domain, "2단(%s)이 '%s' 로 돌려보냄 → 반송 1회" % (state["domain"], state["task"]))
    return {"domain": domain, "task": None, "bounced": True}


def bounce_fail_node(state: BankState):
    with logger.get_logger().node("bounce_fail"):
        answer = "요청을 알아듣지 못했습니다. 계좌 업무인지 카드 업무인지 조금 더 자세히 말해 주세요.\n" + guide_message
    return {"answer": answer}


def route_after_domain(state: BankState):
    # 2단 에이전트가 끝난 뒤. 반송이면 한 번만 반대쪽으로, 이미 반송했으면 안내로 끝냅니다.
    if state.get("task") in BOUNCE:
        return "bounce_fail" if state.get("bounced") else "bounce"
    return END


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
