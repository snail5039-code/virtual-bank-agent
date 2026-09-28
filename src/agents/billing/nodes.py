# 카드 결제(요금) 에이전트(3단)의 노드 함수입니다.
# 요금 조회 / 명세서 조회 (4-8), 전체 결제 / 부분 결제 (4-9) 를 맡습니다. 분할·일괄은 4-10 에서 만듭니다.
#
#   billing_extract   : 사용자 말에서 할 일과 카드, 청구 월, 금액, 계좌를 뽑습니다 (LLM)
#   billing_fee       : 아직 낼 돈이 남은 청구서와 남은 금액 합계를 보여줍니다 ("얼마 내야 해?")
#   billing_statement : 청구서를 골라 상세 내역(어디서 얼마 썼는지)까지 보여줍니다 ("뭐로 나온 거야?")
#   billing_check     : 결제할 청구서와 계좌를 하나로 정하고, 낼 수 있는지 봅니다 (Python)
#   billing_propose   : 결제 처리안을 만듭니다. 계산만 하고 저장하지 않습니다
#   billing_execute   : 승인되면 카드값을 냅니다 (저장은 common_save)
#   billing_fail      : 진행할 수 없는 사유를 알려줍니다
# 조회는 읽기만 하므로 인증·승인 없이 끝납니다. 결제는 인증 → 처리안 → 승인 → 저장을 거칩니다.
# 전체 결제는 "남은 금액 전부를 내는 부분 결제" 라서 같은 노드와 함수를 씁니다. 금액을 말하면 부분, 안 말하면 전체입니다.

from typing import Literal, Optional

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

import data_store
import functions
import logger
from agents.billing.prompts import extract_prompt
from model import llm
from state import BankState


class BillingInfo(BaseModel):
    action: Optional[Literal["요금 조회", "명세서 조회", "결제"]] = Field(default=None, description="할 일")
    card_name: Optional[str] = Field(default=None, description="카드 이름")
    # 형식을 YYYY-MM 로 고정합니다. 틀린 값은 pydantic 이 받지 않습니다.
    billing_month: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$", description="청구 월 YYYY-MM")
    amount: Optional[int] = Field(default=None, description="부분 결제 금액. 전부 낼 때는 비움")
    account_name: Optional[str] = Field(default=None, description="돈을 낼 계좌 이름")


llm_with_billing_output = llm.with_structured_output(BillingInfo)


def billing_extract_node(state: BankState):
    # 승인 전 수정("아니 저축에서", "10만원만")도 여기로 돌아와 말한 값만 덮어씁니다.
    log = logger.get_logger()
    info = dict(state.get("billing_info") or {})
    with log.node("billing_extract"):
        # LLM 이 형식을 어기면 검증 오류가 나므로, 오류 대신 안내로 끝냅니다.
        try:
            r = llm_with_billing_output.invoke([
                SystemMessage(content=extract_prompt.format(
                    year=functions.base_date().year, today=functions.base_date(),
                    known={k: info.get(k) for k in ["action", "card_name", "billing_month", "amount", "account_name"]})),
                HumanMessage(content=state["query"]),
            ])
        except (ValidationError, OutputParserException) as e:
            log.detail("형식 오류  %s" % type(e).__name__)
            return {"error": "요청을 알아듣지 못했습니다. (예: 카드값 얼마야? / 8월 생활비 신용카드 명세서 보여줘)"}
        log.detail("추출  할 일=%s  카드=%s  청구 월=%s  금액=%s  계좌=%s" % (
            r.action, r.card_name, r.billing_month, r.amount, r.account_name))

        for key, value in r.model_dump().items():
            if value is not None and not (key == "action" and info.get("action")):
                info[key] = value
        if not info.get("action"):
            return {"error": "요청을 알아듣지 못했습니다. (예: 카드값 얼마야? / 8월 생활비 신용카드 값 내줘)"}

    return {"billing_info": info}


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
        cards, error = credit_cards(info.get("card_name"))
        if error:
            return {"answer": error}

        # 낼 돈이 남은 청구서만 봅니다 (미납, 일부 납부).
        found = [s for s in functions.get_statements(functions.CURRENT_USER, list(cards), info.get("billing_month"))
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
        cards, error = credit_cards(info.get("card_name"))
        if error:
            return {"answer": error}

        statements = functions.get_statements(functions.CURRENT_USER, list(cards), info.get("billing_month"))
        if not statements:
            return {"answer": "조건에 맞는 명세서가 없습니다."}
        # 청구 월을 말하지 않았으면 가장 최근 달 명세서를 보여줍니다.
        if not info.get("billing_month"):
            latest = statements[0]["billing_month"]
            statements = [s for s in statements if s["billing_month"] == latest]

        lines = []
        for s in statements:
            lines.append(statement_line(s, cards))
            for u in functions.get_statement_items(functions.CURRENT_USER, s):
                lines.append("  - %s  %-6s %s원" % (u["occurred_at"][5:10], u["merchant"], format(u["amount"], ",")))
            lines.append("")
    return {"answer": "\n".join(lines).strip()}


def billing_check_node(state: BankState):
    log = logger.get_logger()
    with log.node("billing_check"):
        info = dict(state["billing_info"])
        cards, error = credit_cards(info.get("card_name"))
        if error:
            return {"error": error}

        # 청구서를 하나로 정합니다. 낼 돈이 남은 청구서만 후보입니다.
        statements = functions.get_statements(functions.CURRENT_USER, list(cards), info.get("billing_month"))
        unpaid = [s for s in statements if s["remaining_amount"] > 0]
        if not unpaid:
            return {"error": "이미 납부 완료된 청구서입니다." if statements else "조건에 맞는 청구서가 없습니다."}
        if len(unpaid) > 1:
            lines = ["낼 청구서가 %d건입니다. 카드와 청구 월을 정해 다시 요청해 주세요. (예: 8월 생활비 신용카드 값 내줘)" % len(unpaid)]
            lines += ["- " + statement_line(s, cards) for s in unpaid]
            return {"error": "\n".join(lines)}
        statement = unpaid[0]
        log.resolve(info.get("card_name") or "(말 안 함)", 1, statement["statement_id"])

        # 계좌 : 말했으면 그 계좌, 안 말했으면 카드의 결제 계좌입니다.
        if info.get("account_name"):
            found = functions.find_accounts(functions.CURRENT_USER, info["account_name"])
            if len(found) != 1:
                return {"error": "'%s' 계좌를 하나로 정할 수 없습니다. 정확한 계좌 이름으로 다시 요청해 주세요." % info["account_name"]}
            account_id = found[0]["account_id"]
        else:
            account_id = cards[statement["card_id"]]["account_id"]

        # 금액 : 말했으면 부분 결제, 안 말했으면 남은 금액 전부 (전체 결제)
        amount = info.get("amount") or statement["remaining_amount"]
        error = functions.check_payment(functions.CURRENT_USER, statement, account_id, amount)
        if error:
            return {"error": error}

        info.update({"statement_id": statement["statement_id"], "account_id": account_id, "pay_amount": amount})
    return {"billing_info": info}


def billing_propose_node(state: BankState):
    with logger.get_logger().node("billing_propose"):
        info = state["billing_info"]
        statement = functions.get_statements(functions.CURRENT_USER)
        statement = next(s for s in statement if s["statement_id"] == info["statement_id"])
        card = next(c for c in functions.get_cards(functions.CURRENT_USER) if c["card_id"] == statement["card_id"])
        account = functions.get_account(functions.CURRENT_USER, info["account_id"])
        amount = info["pay_amount"]
        left = statement["remaining_amount"] - amount
        rows = [
            ["청구서", "%s %s분 (기한 %s)" % (card["name"], statement["billing_month"], statement["due_date"])],
            ["방식", "전체 결제" if left == 0 else "부분 결제"],
            ["낼 금액", "%s원" % format(amount, ",")],
            ["남은 금액", "%s원 → %s원" % (format(statement["remaining_amount"], ","), format(left, ","))],
            ["결제 계좌", "%s (%s)  잔액 %s원 → %s원" % (
                account["nickname"], account["account_number"],
                format(account["balance"], ","), format(account["balance"] - amount, ","))],
        ]
    return {"proposal": {"task": "카드값 결제", "rows": rows}, "approval": "대기"}


def billing_execute_node(state: BankState):
    # 승인된 뒤에만 옵니다. 바꾼 데이터를 new_data 로 넘기고, 저장은 common_save 가 합니다.
    with logger.get_logger().node("billing_execute"):
        info = state["billing_info"]
        data = data_store.load()
        statement = next(s for s in data["card_statements"] if s["statement_id"] == info["statement_id"])
        card = next(c for c in data["cards"] if c["card_id"] == statement["card_id"])
        memo = "카드값 %s %s분" % (card["name"], statement["billing_month"])
        functions.pay_statement(data, info["statement_id"], info["account_id"], info["pay_amount"], memo)
        answer = "카드값을 냈습니다. (%s  %s원)\n남은 금액 %s원  [%s]" % (
            memo, format(info["pay_amount"], ","), format(statement["remaining_amount"], ","),
            functions.STATEMENT_STATUS[statement["status"]])
    return {"new_data": data, "answer": answer, "result": "완료"}


def billing_fail_node(state: BankState):
    with logger.get_logger().node("billing_fail"):
        answer = state["error"]
    return {"answer": answer}


def route_after_extract(state: BankState):
    # 할 일에 따라 나눕니다. 조회 둘은 바로 보여주고, 결제는 check 부터 쓰기 흐름을 탑니다.
    if state.get("error"):
        return "billing_fail"
    action = state["billing_info"]["action"]
    if action == "요금 조회":
        return "billing_fee"
    if action == "명세서 조회":
        return "billing_statement"
    return "billing_check"


def route_after_check(state: BankState):
    if state.get("error"):
        return "billing_fail"
    return "common_authenticate"


def route_after_authenticate(state: BankState):
    if state.get("error"):
        return "billing_fail"
    if state.get("authenticated"):
        return "billing_propose"
    return "common_authenticate"        # 틀렸으면 다시 묻습니다


def route_after_interpret(state: BankState):
    decision = state["approval"]
    if decision == "승인":
        return "billing_execute"
    if decision in ("거절", "취소", "다른요청"):
        return "common_reject"
    if decision == "수정":
        return "billing_extract"        # 바꾼 말로 다시 뽑고 처리안을 새로 만듭니다
    return "common_approve"             # 모름 : 다시 묻습니다
