# 카드 에이전트(2단)의 노드 함수입니다.
#
#   card_router : 카드 요청이 조회 / 결제 / 설정 / 재발급 중 무엇인지 고릅니다
#   card_extract: 무엇을 볼지(목록 / 결제 계좌 / 카드 번호 / 멤버십 / 이용 내역)와 조건을 뽑습니다
#   card_query  : 조건으로 카드를 걸러 볼 것을 보여줍니다. 카드 번호는 본인 확인 뒤에만 옵니다
#   card_todo   : 결제 / 재발급 은 아직 준비 중이라고 안내합니다 (설정은 카드 설정 에이전트 그래프로 넘깁니다)

from datetime import date
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
    info: Literal["목록", "결제 계좌", "카드 번호", "멤버십", "이용 내역"] = Field(
        default="목록", description="카드의 무엇을 볼지")
    bank_name: Optional[str] = Field(default=None, description="은행 이름")
    card_name: Optional[str] = Field(default=None, description="카드 이름")
    card_type: Optional[Literal["체크", "신용"]] = Field(default=None, description="카드 종류")
    status: Optional[Literal["사용 가능", "일시 잠금", "분실 정지", "해지"]] = Field(default=None, description="카드 상태")
    # 이용 내역의 기간입니다. 계좌 거래내역과 같은 방식입니다.
    period: Literal["오늘", "어제", "이번 주", "지난 주", "이번 달", "지난 달", "전체"] = Field(
        default="전체", description="기간")
    start_date: Optional[date] = Field(default=None, description="직접 말한 시작일 YYYY-MM-DD")
    end_date: Optional[date] = Field(default=None, description="직접 말한 종료일 YYYY-MM-DD")


llm_with_filter_output = llm.with_structured_output(CardFilter)


def card_extract_node(state: BankState):
    # 무엇을 볼지와 조건을 LLM 이 뽑습니다. 카드 번호면 다음에 본인 확인을 거치므로 State 에 남겨 둡니다.
    log = logger.get_logger()
    with log.node("card_extract"):
        # LLM 이 형식을 어기면 검증 오류가 나므로, 오류 대신 안내로 끝냅니다.
        try:
            f = llm_with_filter_output.invoke([
                SystemMessage(content=card_query_prompt.format(year=functions.base_date().year, today=functions.base_date())),
                HumanMessage(content=state["query"]),
            ])
        except (ValidationError, OutputParserException) as e:
            log.detail("조건 형식 오류  %s" % type(e).__name__)
            return {"error": "조건을 알아듣지 못했습니다. (예: 가상은행 카드 / 신용카드 결제 계좌 / 이번 달 카드 이용 내역)"}
        log.detail("조건  볼것=%s 은행=%s 이름=%s 종류=%s 상태=%s 기간=%s %s~%s" % (
            f.info, f.bank_name, f.card_name, f.card_type, f.status, f.period, f.start_date, f.end_date))

    return {"card_filter": f.model_dump()}


def card_query_node(state: BankState):
    # 뽑아 둔 조건으로 카드를 거르고, 볼 것(info)에 맞춰 답을 만듭니다. 거르기와 계산은 functions 가 합니다.
    if state.get("error"):
        return {"answer": state["error"]}

    f = state["card_filter"]
    with logger.get_logger().node("card_query"):
        cards = functions.find_cards(functions.CURRENT_USER, f["bank_name"], f["card_name"], f["card_type"], f["status"])
        if not cards:
            return {"answer": "조건에 맞는 카드가 없습니다."}

        accounts = {a["account_id"]: a for a in functions.get_accounts(functions.CURRENT_USER)}
        names = {c["card_id"]: c["name"] for c in cards}
        info = f["info"]

        if info == "결제 계좌":
            lines = ["카드 %d장의 결제 계좌입니다." % len(cards)]
            for card in cards:
                account = accounts[card["account_id"]]
                lines.append("- %s : %s (%s %s)" % (
                    card["name"], account["nickname"], account["bank_name"], account["account_number"]))

        elif info == "카드 번호":
            # 본인 확인을 마친 뒤에만 여기 옵니다. 그래서 가리지 않고 전체를 보여줍니다. (기획서 5.1)
            lines = ["카드 %d장의 카드 번호입니다." % len(cards)]
            for card in cards:
                lines.append("- %s : %s  [%s]" % (card["name"], card["card_number"], functions.CARD_STATUS[card["status"]]))

        elif info == "멤버십":
            memberships = functions.get_memberships(functions.CURRENT_USER, list(names))
            if not memberships:
                return {"answer": "멤버십이 연결된 카드가 없습니다."}
            lines = ["멤버십 %d개입니다." % len(memberships)]
            for m in memberships:
                lines.append("- %s : %s %s등급  %sP" % (names[m["card_id"]], m["name"], m["grade"], format(m["points"], ",")))

        elif info == "이용 내역":
            start, end = functions.period_range(f["period"])
            start = f["start_date"] or start
            end = f["end_date"] or end
            found = functions.get_card_history(functions.CURRENT_USER, list(names), start, end)
            if not found:
                return {"answer": "조건에 맞는 카드 이용 내역이 없습니다."}
            lines = ["카드 이용 내역 %d건 (최근순)" % len(found)]
            for item in found:
                lines.append("- %s  %s  %s원  %s" % (
                    item["occurred_at"][:16].replace("T", " "), names[item["card_id"]],
                    format(item["amount"], ","), item["merchant"] or ""))
            # 합계는 Python 이 더합니다. LLM 이 계산하지 않습니다 (원칙 6).
            lines.append("합계 : %s원" % format(sum(item["amount"] for item in found), ","))

        else:   # 목록
            lines = ["카드 %d장입니다." % len(cards)]
            for card in cards:
                if card["card_type"] == "credit":
                    extra = "한도 %s원" % format(card["credit_limit"], ",")
                else:
                    extra = "연결 계좌 %s" % accounts[card["account_id"]]["nickname"]
                lines.append("- %s (%s %s) : %s  [%s]" % (
                    card["name"], card["bank_name"], functions.CARD_TYPES[card["card_type"]],
                    extra, functions.CARD_STATUS[card["status"]]))

    return {"answer": "\n".join(lines)}


def card_todo_node(state: BankState):
    with logger.get_logger().node("card_todo"):
        answer = "카드 %s 업무는 아직 준비 중입니다." % state["task"]
    return {"answer": answer}


def route_by_task(state: BankState):
    # 고른 업무에 따라 다음 노드를 정합니다. 결제·재발급은 아직 준비 중입니다.
    if state["task"] == "조회":
        return "card_extract"
    if state["task"] == "설정":
        return "card_setting"
    return "card_todo"


def route_after_extract(state: BankState):
    # 카드 번호는 본인 확인을 먼저 받습니다. 나머지는 바로 보여줍니다.
    if not state.get("error") and state["card_filter"]["info"] == "카드 번호":
        return "common_authenticate"
    return "card_query"


def route_after_authenticate(state: BankState):
    # 맞혔거나 취소·3번 실패(error)면 card_query 로 갑니다. card_query 가 error 를 보고 안내로 끝냅니다.
    if state.get("error") or state.get("authenticated"):
        return "card_query"
    return "common_authenticate"        # 틀렸으면 다시 묻습니다
