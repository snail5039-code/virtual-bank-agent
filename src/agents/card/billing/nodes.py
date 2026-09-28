# 카드 결제(요금) 에이전트(3단)의 노드 함수입니다.
# 요금 조회 / 명세서 조회 (4-8), 전체·부분 결제 (4-9), 분할·일괄 결제 (4-10) 를 맡습니다.
#
#   billing_extract   : 사용자 말에서 할 일과 카드, 청구 월, 금액, 계좌를 뽑습니다 (LLM)
#   billing_fee       : 아직 낼 돈이 남은 청구서와 남은 금액 합계를 보여줍니다 ("얼마 내야 해?")
#   billing_statement : 청구서를 골라 상세 내역(어디서 얼마 썼는지)까지 보여줍니다 ("뭐로 나온 거야?")
#   billing_check     : 결제 방식과 대상(청구서·계좌·금액)을 정하고, 낼 수 있는지 봅니다 (Python)
#   billing_propose   : 결제 처리안을 만듭니다. 계산만 하고 저장하지 않습니다
#   billing_execute   : 승인되면 카드값을 냅니다 (일괄은 건마다 바로 저장, 나머지는 common_save)
#   billing_fail      : 진행할 수 없는 사유를 알려줍니다
# 조회는 읽기만 하므로 인증·승인 없이 끝납니다. 결제는 인증 → 처리안 → 승인 → 저장을 거칩니다.
# 네 방식 모두 결제 한 건은 functions.pay_statement 로 냅니다.
#   전체 : 남은 금액 전부 / 부분 : 말한 금액 / 분할 : 할부 계획을 만들고 첫 회차만 / 일괄 : 여러 건을 전체로, 건별 저장

from typing import Literal, Optional

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, ValidationError

import data_store
import functions
import logger
from agents.card.billing.prompts import extract_prompt
from model import llm
from state import BankState


class BillingInfo(BaseModel):
    action: Optional[Literal["요금 조회", "명세서 조회", "결제"]] = Field(default=None, description="할 일")
    card_name: Optional[str] = Field(default=None, description="카드 이름")
    # 형식을 YYYY-MM 로 고정합니다. 틀린 값은 pydantic 이 받지 않습니다.
    billing_month: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}$", description="청구 월 YYYY-MM")
    amount: Optional[int] = Field(default=None, description="부분 결제 금액. 전부 낼 때는 비움")
    account_name: Optional[str] = Field(default=None, description="돈을 낼 계좌 이름")
    method: Optional[Literal["전체", "부분", "분할", "일괄"]] = Field(default=None, description="결제 방식")
    months: Optional[int] = Field(default=None, description="분할 개월 수")


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
                    known={k: info.get(k) for k in ["action", "card_name", "billing_month", "amount", "account_name",
                                                   "method", "months"]})),
                HumanMessage(content=state["query"]),
            ])
        except (ValidationError, OutputParserException) as e:
            log.detail("형식 오류  %s" % type(e).__name__)
            return {"error": "요청을 알아듣지 못했습니다. (예: 카드값 얼마야? / 8월 생활비 신용카드 명세서 보여줘)"}
        log.detail("추출  할 일=%s  카드=%s  청구 월=%s  금액=%s  계좌=%s  방식=%s  개월=%s" % (
            r.action, r.card_name, r.billing_month, r.amount, r.account_name, r.method, r.months))

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
    # 결제 대상(targets)을 정합니다. 일괄은 여러 건, 나머지(전체·부분·분할)는 1건입니다.
    #   targets = [{statement_id, account_id, amount}, ...]   amount = 지금 낼 금액
    log = logger.get_logger()
    with log.node("billing_check"):
        info = dict(state["billing_info"])
        cards, error = credit_cards(info.get("card_name"))
        if error:
            return {"error": error}

        # 방식 : 말했으면 그 방식, 안 말했으면 개월 수가 있으면 분할, 금액이 있으면 부분, 둘 다 없으면 전체
        method = info.get("method") or ("분할" if info.get("months") else "부분" if info.get("amount") else "전체")
        info["method"] = method

        # 낼 돈이 남은 청구서만 후보입니다. 일괄이 아니면 하나로 정해야 합니다.
        statements = functions.get_statements(functions.CURRENT_USER, list(cards), info.get("billing_month"))
        unpaid = [s for s in statements if s["remaining_amount"] > 0]
        if not unpaid:
            return {"error": "이미 납부 완료된 청구서입니다." if statements else "조건에 맞는 청구서가 없습니다."}
        if method != "일괄" and len(unpaid) > 1:
            lines = ["낼 청구서가 %d건입니다. 카드와 청구 월을 정해 다시 요청해 주세요. "
                     "(예: 8월 생활비 신용카드 값 내줘 / 한 번에 다 내려면: 카드값 전부 일괄로 내줘)" % len(unpaid)]
            lines += ["- " + statement_line(s, cards) for s in unpaid]
            return {"error": "\n".join(lines)}
        log.resolve(info.get("card_name") or "(말 안 함)", len(unpaid), unpaid[0]["statement_id"])

        # 계좌 : 말했으면 그 계좌, 안 말했으면 카드마다 그 카드의 결제 계좌입니다.
        said_account = None
        if info.get("account_name"):
            found = functions.find_accounts(functions.CURRENT_USER, info["account_name"])
            if len(found) != 1:
                return {"error": "'%s' 계좌를 하나로 정할 수 없습니다. 정확한 계좌 이름으로 다시 요청해 주세요." % info["account_name"]}
            said_account = found[0]["account_id"]

        targets = []
        for s in unpaid:
            account_id = said_account or cards[s["card_id"]]["account_id"]
            if method == "분할":
                # 분할은 첫 회차를 지금 냅니다. 나머지 회차는 계획으로만 남깁니다.
                error = functions.check_installment(functions.CURRENT_USER, s, info.get("months"))
                if error:
                    return {"error": error}
                amount = functions.installment_amounts(s["remaining_amount"], info["months"])[0]
            elif method == "부분":
                amount = info.get("amount") or 0
            else:   # 전체, 일괄 : 남은 금액 전부
                amount = s["remaining_amount"]
            # 일괄도 승인 전에 건마다 한 번 봅니다. 실제로 낼 때 잔액을 다시 봅니다 (앞 건을 내면 잔액이 줄기 때문).
            error = functions.check_payment(functions.CURRENT_USER, s, account_id, amount)
            if error:
                return {"error": error if method != "일괄" else "%s %s분 : %s" % (
                    cards[s["card_id"]]["name"], s["billing_month"], error)}
            targets.append({"statement_id": s["statement_id"], "account_id": account_id, "amount": amount})

        info["targets"] = targets
    return {"billing_info": info}


def target_text(data, target):
    # 결제 대상 한 건의 청구서, 이름, 계좌. 예) (청구서, "생활비 신용카드 2026-08분", 생활비 계좌)
    # 부르는 쪽이 한 번 읽어 둔 data 에서 찾습니다. (건마다 파일을 다시 읽지 않게)
    statement = next(s for s in data["card_statements"] if s["statement_id"] == target["statement_id"])
    card = next(c for c in data["cards"] if c["card_id"] == statement["card_id"])
    account = next(a for a in data["accounts"] if a["account_id"] == target["account_id"])
    return statement, "%s %s분" % (card["name"], statement["billing_month"]), account


def billing_propose_node(state: BankState):
    with logger.get_logger().node("billing_propose"):
        info = state["billing_info"]
        method = info["method"]
        targets = info["targets"]
        data = data_store.load()

        if method == "일괄":
            rows = [["방식", "일괄 결제 (%d건)" % len(targets)]]
            for i, t in enumerate(targets, 1):
                _, name, account = target_text(data, t)
                rows.append(["청구서 %d" % i, "%s  %s원  (%s 계좌)" % (name, format(t["amount"], ","), account["nickname"])])
            rows.append(["합계", "%s원" % format(sum(t["amount"] for t in targets), ",")])
            rows.append(["안내", "건마다 따로 냅니다. 중간에 실패해도 앞에서 낸 건은 그대로입니다"])
        else:
            t = targets[0]
            statement, name, account = target_text(data, t)
            left = statement["remaining_amount"] - t["amount"]
            rows = [
                ["청구서", "%s (기한 %s)" % (name, statement["due_date"])],
                ["방식", "%s 결제" % method],
                ["낼 금액", "%s원" % format(t["amount"], ",")],
                ["남은 금액", "%s원 → %s원" % (format(statement["remaining_amount"], ","), format(left, ","))],
                ["결제 계좌", "%s (%s)  잔액 %s원 → %s원" % (
                    account["nickname"], account["account_number"],
                    format(account["balance"], ","), format(account["balance"] - t["amount"], ","))],
            ]
            if method == "분할":
                amounts = functions.installment_amounts(statement["remaining_amount"], info["months"])
                rows.insert(2, ["분할", "%d개월 : %s (첫 회차는 지금 냅니다)" % (
                    info["months"], " / ".join(format(a, ",") + "원" for a in amounts))])
    return {"proposal": {"task": "카드값 %s 결제" % method, "rows": rows}, "approval": "대기"}


def pay_one(data, target, method, months=None):
    # 한 건을 data 안에서 냅니다. 저장은 하지 않습니다. 낸 뒤의 안내 한 줄을 돌려줍니다.
    statement = next(s for s in data["card_statements"] if s["statement_id"] == target["statement_id"])
    card = next(c for c in data["cards"] if c["card_id"] == statement["card_id"])
    memo = "카드값 %s %s분" % (card["name"], statement["billing_month"])
    if method == "분할":
        installment_id = functions.add_installment(data, statement["statement_id"], months)
        memo += " 분할 1/%d회" % months
    functions.pay_statement(data, statement["statement_id"], target["account_id"], target["amount"], memo)
    line = "%s  %s원  → 남은 금액 %s원 [%s]" % (memo, format(target["amount"], ","),
                                         format(statement["remaining_amount"], ","),
                                         functions.STATEMENT_STATUS[statement["status"]])
    if method == "분할":
        line += "  (분할 %s)" % installment_id
    return line


def billing_execute_node(state: BankState):
    # 승인된 뒤에만 옵니다.
    #   전체·부분·분할 : 한 건을 바꾼 데이터를 new_data 로 넘기고, 저장은 common_save 가 합니다 (실패하면 전부 롤백)
    #   일괄           : 건마다 내고 바로 저장합니다 (건별 저장). 2건째가 실패해도 1건째는 남습니다.
    #                   나눠 이체(전부 아니면 전무)와 반대입니다. (기획서 5.2)
    log = logger.get_logger()
    with log.node("billing_execute"):
        info = state["billing_info"]
        method = info["method"]

        if method != "일괄":
            data = data_store.load()
            line = pay_one(data, info["targets"][0], method, info.get("months"))
            return {"new_data": data, "answer": "카드값을 냈습니다.\n" + line, "result": "완료"}

        results = []    # (완료 / 실패 / 미처리, 안내)
        stopped = False
        data = data_store.load()
        for t in info["targets"]:
            _, name, _ = target_text(data, t)       # 이름(카드·청구 월)은 내도 바뀌지 않으므로 직전 data 로 충분합니다
            if stopped:
                results.append(("미처리", name))
                continue
            data = data_store.load()        # 앞 건을 저장한 뒤의 최신 데이터로 봅니다
            statement = next(s for s in data["card_statements"] if s["statement_id"] == t["statement_id"])
            error = functions.check_payment(functions.CURRENT_USER, statement, t["account_id"], t["amount"])
            if error:
                results.append(("실패", "%s : %s" % (name, error)))
                continue
            line = pay_one(data, t, method)
            try:
                data_store.save(data)
                results.append(("완료", line))
            except data_store.DataStoreError:
                # 저장이 안 되면 뒤 건은 내지 않습니다. 이미 저장한 앞 건은 그대로입니다.
                results.append(("실패", "%s : 저장에 실패했습니다" % name))
                stopped = True
            log.detail("일괄 %s  %s" % (results[-1][0], name))

        done = sum(1 for r in results if r[0] == "완료")
        lines = ["일괄 결제 결과 : 완료 %d건 / 실패 %d건 / 미처리 %d건" % (
            done, sum(1 for r in results if r[0] == "실패"), sum(1 for r in results if r[0] == "미처리"))]
        lines += ["- [%s] %s" % r for r in results]
        answer = "\n".join(lines)
    # 이미 건마다 저장했으므로 new_data 는 비웁니다. 처리 기록은 common_log_request 가 파일을 새로 읽어 덧붙입니다.
    if done == 0:
        return {"new_data": None, "answer": answer, "error": answer, "result": "실패"}
    return {"new_data": None, "answer": answer, "result": "완료"}


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
