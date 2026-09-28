# 카드 결제(요금) 에이전트(3단)의 노드 함수입니다.
# 지금은 요금 조회 / 명세서 조회 (4-8) 를 맡습니다. 결제는 4-9, 4-10 에서 만듭니다.
#
#   billing_extract   : 사용자 말에서 할 일(요금 조회 / 명세서 조회 / 결제)과 카드, 청구 월을 뽑습니다 (LLM)
#   billing_fee       : 아직 낼 돈이 남은 청구서와 남은 금액 합계를 보여줍니다 ("얼마 내야 해?")
#   billing_statement : 청구서를 골라 상세 내역(어디서 얼마 썼는지)까지 보여줍니다 ("뭐로 나온 거야?")
#   billing_todo      : 결제는 아직 준비 중이라고 안내합니다
# 조회는 읽기만 하므로 인증·승인 없이 끝납니다. 거르기와 합계는 functions 가 합니다.

from typing import Literal, Optional

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

import functions
import logger
from agents.billing.prompts import extract_prompt
from model import llm
from state import BankState


class BillingInfo(BaseModel):
    action: Literal["요금 조회", "명세서 조회", "결제"] = Field(description="할 일")
    card_name: Optional[str] = Field(default=None, description="카드 이름")
    # 형식을 YYYY-MM 로 고정합니다. 틀린 값은 pydantic 이 받지 않습니다.
    billing_month: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$", description="청구 월 YYYY-MM")


llm_with_billing_output = llm.with_structured_output(BillingInfo)


def billing_extract_node(state: BankState):
    log = logger.get_logger()
    with log.node("billing_extract"):
        # LLM 이 형식을 어기면 검증 오류가 나므로, 오류 대신 안내로 끝냅니다.
        try:
            r = llm_with_billing_output.invoke([
                SystemMessage(content=extract_prompt.format(year=functions.base_date().year, today=functions.base_date())),
                HumanMessage(content=state["query"]),
            ])
        except (ValidationError, OutputParserException) as e:
            log.detail("형식 오류  %s" % type(e).__name__)
            return {"error": "요청을 알아듣지 못했습니다. (예: 카드값 얼마야? / 8월 생활비 신용카드 명세서 보여줘)"}
        log.detail("추출  할 일=%s  카드=%s  청구 월=%s" % (r.action, r.card_name, r.billing_month))

    return {"billing_info": r.model_dump()}


def credit_cards(card_name):
    # 청구서가 있는 신용카드만 봅니다. 카드를 말했으면 그 카드만 봅니다.
    # (카드 목록, 안내) 를 돌려줍니다. 볼 카드가 없으면 목록은 비고 안내에 사유가 들어갑니다.
    cards = functions.pick_cards(functions.CURRENT_USER, card_name) if card_name else functions.get_cards(functions.CURRENT_USER)
    credit = {c["card_id"]: c for c in cards if c["card_type"] == "credit"}
    if credit:
        return credit, None
    if cards:
        return {}, "체크카드는 쓰는 즉시 계좌에서 빠져서 청구서가 없습니다. (%s)" % ", ".join(c["name"] for c in cards)
    return {}, "'%s' 카드를 찾을 수 없습니다." % card_name


def statement_line(statement, cards):
    # 예) 생활비 신용카드 2026-08 : 청구 320,000원 / 낸 금액 0원 / 남은 금액 320,000원  (기한 09-15)  [미납]
    return "%s %s : 청구 %s원 / 낸 금액 %s원 / 남은 금액 %s원  (기한 %s)  [%s]" % (
        cards[statement["card_id"]]["name"], statement["billing_month"],
        format(statement["total_amount"], ","), format(statement["paid_amount"], ","),
        format(statement["remaining_amount"], ","), statement["due_date"][5:],
        functions.STATEMENT_STATUS[statement["status"]])


def billing_fee_node(state: BankState):
    with logger.get_logger().node("billing_fee"):
        info = state["billing_info"]
        cards, error = credit_cards(info["card_name"])
        if error:
            return {"answer": error}

        # 낼 돈이 남은 청구서만 봅니다 (미납, 일부 납부).
        found = [s for s in functions.get_statements(functions.CURRENT_USER, list(cards), info["billing_month"])
                 if s["remaining_amount"] > 0]
        if not found:
            return {"answer": "낼 카드값이 없습니다."}

        lines = ["낼 카드값 %d건입니다." % len(found)]
        lines += ["- " + statement_line(s, cards) for s in found]
        # 합계는 Python 이 더합니다. LLM 이 계산하지 않습니다 (원칙 6).
        lines.append("남은 금액 합계 : %s원" % format(sum(s["remaining_amount"] for s in found), ","))
    return {"answer": "\n".join(lines)}


def billing_statement_node(state: BankState):
    with logger.get_logger().node("billing_statement"):
        info = state["billing_info"]
        cards, error = credit_cards(info["card_name"])
        if error:
            return {"answer": error}

        statements = functions.get_statements(functions.CURRENT_USER, list(cards), info["billing_month"])
        if not statements:
            return {"answer": "조건에 맞는 명세서가 없습니다."}
        # 청구 월을 말하지 않았으면 가장 최근 달 명세서를 보여줍니다.
        if not info["billing_month"]:
            latest = statements[0]["billing_month"]
            statements = [s for s in statements if s["billing_month"] == latest]

        lines = []
        for s in statements:
            lines.append(statement_line(s, cards))
            for u in functions.get_statement_items(functions.CURRENT_USER, s):
                lines.append("  - %s  %-6s %s원" % (u["occurred_at"][5:10], u["merchant"], format(u["amount"], ",")))
            lines.append("")
    return {"answer": "\n".join(lines).strip()}


def billing_todo_node(state: BankState):
    with logger.get_logger().node("billing_todo"):
        answer = "카드값 결제는 아직 준비 중입니다. (요금 조회, 명세서 조회는 할 수 있습니다)"
    return {"answer": answer}


def billing_fail_node(state: BankState):
    with logger.get_logger().node("billing_fail"):
        answer = state["error"]
    return {"answer": answer}


def route_after_extract(state: BankState):
    # 할 일에 따라 나눕니다. 결제는 4-9 에서 이 자리에 결제 흐름을 붙입니다.
    if state.get("error"):
        return "billing_fail"
    action = state["billing_info"]["action"]
    if action == "요금 조회":
        return "billing_fee"
    if action == "명세서 조회":
        return "billing_statement"
    return "billing_todo"
