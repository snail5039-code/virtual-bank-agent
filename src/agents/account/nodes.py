# 계좌 에이전트(2단)의 노드 함수입니다.
#
#   account_router : 계좌 요청이 조회 / 거래내역 / 이체 / 설정 중 무엇인지 고릅니다
#   account_query  : 계좌 목록과 잔액, 총액을 보여줍니다
#   account_history: 거래 내역을 조건(기간·계좌·종류·금액)으로 걸러 보여줍니다
#   (이체는 이체 에이전트 그래프로, 설정은 설정 에이전트 그래프로 넘깁니다)

from datetime import date
from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import functions
import logger
from agents.account.prompts import account_prompt, history_prompt
from model import llm
from state import BankState


class AccountDecision(BaseModel):
    task: Literal["조회", "거래내역", "이체", "설정"] = Field(description="계좌 요청의 업무 종류")
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
            lines.append("- %s (%s %s) : %s원  [%s]" % (
                account["nickname"],
                account["bank_name"],
                account["account_number"],
                format(account["balance"], ","),
                account["purpose"],
            ))
        # 합계는 Python 이 더합니다. LLM 이 계산하지 않습니다 (원칙 6).
        lines.append("총 잔액 : %s원" % format(sum(account["balance"] for account in accounts), ","))

    return {"answer": "\n".join(lines)}


class HistoryFilter(BaseModel):
    account_name: Optional[str] = Field(default=None, description="계좌 이름")
    period: Literal["오늘", "어제", "이번 주", "지난 주", "이번 달", "지난 달", "전체"] = Field(
        default="전체", description="기간")
    start_date: Optional[str] = Field(default=None, description="직접 말한 시작일 YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="직접 말한 종료일 YYYY-MM-DD")
    kind: Optional[Literal["입금", "출금", "결제"]] = Field(default=None, description="거래 종류")
    min_amount: Optional[int] = Field(default=None, description="이 금액 이상")
    max_amount: Optional[int] = Field(default=None, description="이 금액 이하")


llm_with_history_output = llm.with_structured_output(HistoryFilter)


def account_history_node(state: BankState):
    # 조건은 LLM 이 뽑고, 날짜 계산과 거르기는 Python 이 합니다.
    log = logger.get_logger()
    with log.node("account_history"):
        f = llm_with_history_output.invoke([
            SystemMessage(content=history_prompt.format(year=functions.BASE_DATE.year, today=functions.BASE_DATE)),
            HumanMessage(content=state["query"]),
        ])
        log.detail("조건  계좌=%s 기간=%s %s~%s 종류=%s 금액=%s~%s" % (
            f.account_name, f.period, f.start_date, f.end_date, f.kind, f.min_amount, f.max_amount))

        accounts = functions.get_accounts(functions.CURRENT_USER)
        if f.account_name:
            accounts = functions.find_accounts(functions.CURRENT_USER, f.account_name)
            if not accounts:
                return {"answer": "'%s' 계좌를 찾을 수 없습니다." % f.account_name}

        start, end = functions.period_range(f.period)
        if f.start_date:
            start = date.fromisoformat(f.start_date)
        if f.end_date:
            end = date.fromisoformat(f.end_date)

        found = functions.get_transactions(
            functions.CURRENT_USER, [a["account_id"] for a in accounts],
            start, end, f.kind, f.min_amount, f.max_amount)
        log.detail("기간 %s ~ %s / %d건" % (start, end, len(found)))

        if not found:
            return {"answer": "조건에 맞는 거래 내역이 없습니다."}

        nicknames = {a["account_id"]: a["nickname"] for a in accounts}
        cards = {c["card_id"]: c["name"] for c in functions.get_cards(functions.CURRENT_USER)}
        lines = ["거래 내역 %d건 (최근순)" % len(found)]
        for tx in found:
            line = "- %s  %s  %s  %s원" % (
                tx["occurred_at"][:16].replace("T", " "), nicknames[tx["account_id"]],
                "입금" if tx["type"] == "deposit" else "출금", format(tx["amount"], ","))
            if tx["merchant"]:
                line += "  " + tx["merchant"]
            if tx["card_id"]:
                line += "  (%s)" % cards.get(tx["card_id"], tx["card_id"])
            lines.append(line)

    return {"answer": "\n".join(lines)}


def route_by_task(state: BankState):
    # 고른 업무에 따라 다음 노드를 정합니다.
    if state["task"] == "조회":
        return "account_query"
    if state["task"] == "거래내역":
        return "account_history"
    if state["task"] == "이체":
        return "transfer"
    return "account_setting"
