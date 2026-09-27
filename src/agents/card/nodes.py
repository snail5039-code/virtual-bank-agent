# 카드 에이전트(2단)의 노드 함수입니다.
#
#   card_router : 카드 요청이 조회 / 결제 / 설정 / 재발급 중 무엇인지 고릅니다
#   card_query  : 카드 목록을 상태와 함께 보여줍니다. 조건(은행·이름·종류·상태)이 있으면 걸러서 보여줍니다
#   card_todo   : 결제 / 설정 / 재발급 은 아직 준비 중이라고 안내합니다

from typing import Literal, Optional

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

import functions
import logger
from agents.card.prompts import card_prompt, card_query_prompt
from model import llm
from state import BankState


class CardDecision(BaseModel):
    task: Literal["조회", "결제", "설정", "재발급"] = Field(description="카드 요청의 업무 종류")
    reason: str = Field(description="그 업무를 고른 이유")


llm_with_card_output = llm.with_structured_output(CardDecision)


def card_router_node(state: BankState):
    log = logger.get_logger()
    with log.node("card_router"):
        result = llm_with_card_output.invoke([
            SystemMessage(content=card_prompt),
            HumanMessage(content=state["query"]),
        ])
        log.route(2, result.task, result.reason)

    return {"task": result.task}


class CardFilter(BaseModel):
    bank_name: Optional[str] = Field(default=None, description="은행 이름")
    card_name: Optional[str] = Field(default=None, description="카드 이름")
    card_type: Optional[Literal["체크", "신용"]] = Field(default=None, description="카드 종류")
    status: Optional[Literal["사용 가능", "일시 잠금", "분실 정지", "해지"]] = Field(default=None, description="카드 상태")


llm_with_filter_output = llm.with_structured_output(CardFilter)


def card_query_node(state: BankState):
    # 조건은 LLM 이 뽑고, 거르기는 Python 이 합니다. (계좌 거래내역과 같은 방식)
    log = logger.get_logger()
    with log.node("card_query"):
        # LLM 이 형식을 어기면 검증 오류가 나므로, 오류 대신 안내로 끝냅니다.
        try:
            f = llm_with_filter_output.invoke([
                SystemMessage(content=card_query_prompt),
                HumanMessage(content=state["query"]),
            ])
        except (ValidationError, OutputParserException) as e:
            log.detail("조건 형식 오류  %s" % type(e).__name__)
            return {"answer": "조건을 알아듣지 못했습니다. (예: 가상은행 카드 / 신용카드만 / 분실 정지된 카드)"}
        log.detail("조건  은행=%s 이름=%s 종류=%s 상태=%s" % (f.bank_name, f.card_name, f.card_type, f.status))

        cards = functions.find_cards(functions.CURRENT_USER, f.bank_name, f.card_name, f.card_type, f.status)
        if not cards:
            return {"answer": "조건에 맞는 카드가 없습니다."}

        nicknames = {a["account_id"]: a["nickname"] for a in functions.get_accounts(functions.CURRENT_USER)}
        lines = ["카드 %d장입니다." % len(cards)]
        for card in cards:
            if card["card_type"] == "credit":
                extra = "한도 %s원" % format(card["credit_limit"], ",")
            else:
                extra = "연결 계좌 %s" % nicknames.get(card["account_id"], card["account_id"])
            lines.append("- %s (%s %s) : %s  [%s]" % (
                card["name"], card["bank_name"], functions.CARD_TYPES[card["card_type"]],
                extra, functions.CARD_STATUS[card["status"]]))

    return {"answer": "\n".join(lines)}


def card_todo_node(state: BankState):
    with logger.get_logger().node("card_todo"):
        answer = "카드 %s 업무는 아직 준비 중입니다." % state["task"]
    return {"answer": answer}


def route_by_task(state: BankState):
    # 고른 업무에 따라 다음 노드를 정합니다. 조회만 만들었고 나머지는 준비 중입니다.
    if state["task"] == "조회":
        return "card_query"
    return "card_todo"
