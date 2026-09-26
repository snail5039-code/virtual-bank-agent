# 이체 에이전트(3단)의 노드 함수입니다.
#
#   transfer_extract : 사용자 말에서 출금 계좌, 입금 계좌, 금액을 뽑습니다 (LLM)
#   transfer_check   : 계좌 이름을 ID 로 바꾸고, 무엇이 부족한지 봅니다 (Python)
#   transfer_confirm : 후보가 여러 개면 번호를 고르게 합니다 (interrupt)
#   transfer_ask     : 부족한 정보를 묻습니다 (interrupt)
#   transfer_propose : 처리안을 만듭니다. 계산만 하고 저장하지 않습니다 (Python)
#   transfer_revise  : 승인 전에 바꾼 내용을 반영합니다 (LLM)
#   transfer_execute : 승인되면 잔액을 옮기고 거래 내역을 붙입니다 (Python, 저장은 common_save)
#   transfer_fail    : 진행할 수 없는 사유를 알려줍니다
#   (승인·응답 해석·거절은 공통 노드를 씁니다)
#
# interrupt() 로 멈췄다가 답을 받으면 그 노드를 처음부터 다시 실행합니다.
# 그래서 interrupt 가 있는 노드에서는 묻고 답을 받는 일만 합니다.

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

import data_store
import functions
import logger
from agents.common.nodes import question
from agents.transfer.prompts import extract_prompt, revise_prompt
from model import llm
from state import BankState


class TransferInfo(BaseModel):
    from_name: Optional[str] = Field(default=None, description="돈을 보내는 계좌 이름")
    to_name: Optional[str] = Field(default=None, description="돈을 받는 계좌 이름")
    amount: Optional[int] = Field(default=None, description="보낼 금액 (원)")
    keep_amount: Optional[int] = Field(default=None, description="출금 계좌에 남길 금액 (원). 조건부 이체일 때만")


llm_with_transfer_output = llm.with_structured_output(TransferInfo)


def transfer_extract_node(state: BankState):
    log = logger.get_logger()
    with log.node("transfer_extract"):
        prompt = extract_prompt.format(
            from_name=state.get("from_name") or "모름",
            to_name=state.get("to_name") or "모름",
            amount=state.get("amount") or "모름",
            last_transfer=state.get("last_transfer") or "없음",
            question=state.get("question") or "없음",
        )
        result = llm_with_transfer_output.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=state["query"]),
        ])
        log.detail("추출  출금=%s  입금=%s  금액=%s  남길 금액=%s" % (
            result.from_name, result.to_name, result.amount, result.keep_amount))

        # 비어 있는 칸만 채웁니다. 이미 정해진 값은 바꾸지 않습니다.
        update = {}
        if result.from_name and not state.get("from_account"):
            update["from_name"] = result.from_name
        if result.to_name and not state.get("to_account"):
            update["to_name"] = result.to_name
        if result.amount and not state.get("amount"):
            update["amount"] = result.amount
        # 남길 금액은 0 원도 됩니다 ("전부 보내줘" = 0 원 남기기).
        if result.keep_amount is not None and state.get("keep_amount") is None:
            update["keep_amount"] = result.keep_amount

    return update


def transfer_check_node(state: BankState):
    log = logger.get_logger()
    with log.node("transfer_check"):
        update = {"candidates": None, "confirm_for": None}

        for slot in ["from", "to"]:
            name = state.get(slot + "_name")
            if state.get(slot + "_account") or not name:
                continue

            found = functions.find_accounts(functions.CURRENT_USER, name)
            log.resolve(name, len(found), found[0]["account_id"] if found else None)

            if len(found) == 0:
                update["error"] = "'%s' 계좌를 찾을 수 없습니다." % name
                return update
            if len(found) > 1:
                update["candidates"] = found
                update["confirm_for"] = slot
                return update

            update[slot + "_account"] = found[0]["account_id"]
            update[slot + "_name"] = found[0]["nickname"]

        # 출금과 입금이 같은 계좌면 진행할 수 없습니다.
        from_account = update.get("from_account") or state.get("from_account")
        to_account = update.get("to_account") or state.get("to_account")
        if from_account and from_account == to_account:
            update["error"] = "출금 계좌와 입금 계좌가 같습니다."

        # 조건부 이체 : 이체액 = 잔액 - 남길 금액. Python 이 계산합니다 (원칙 6).
        keep = state.get("keep_amount")
        if keep is not None and from_account:
            balance = functions.get_account(functions.CURRENT_USER, from_account)["balance"]
            update["amount"] = balance - keep
            log.detail("조건부  잔액 %s - 남길 %s = 이체 %s" % (
                format(balance, ","), format(keep, ","), format(balance - keep, ",")))

        # [분기 2] 실행할 수 있는 금액인지 봅니다.
        amount = update.get("amount", state.get("amount"))
        if keep is not None and keep < 0:
            update["error"] = "남길 금액은 0원 이상이어야 합니다."
        elif keep is not None and amount is not None and amount <= 0:
            update["error"] = "잔액이 %s원이라 %s원을 남기면 보낼 금액이 없습니다." % (
                format(amount + keep, ","), format(keep, ","))
        elif amount is not None and amount <= 0:
            update["error"] = "이체 금액은 0원보다 커야 합니다."
        elif amount and from_account:
            balance = functions.get_account(functions.CURRENT_USER, from_account)["balance"]
            if balance < amount:
                update["error"] = "잔액이 부족합니다. (잔액 %s원)" % format(balance, ",")

    return update


def transfer_confirm_node(state: BankState):
    slot = state["confirm_for"]
    candidates = state["candidates"]

    lines = ["'%s' 에 맞는 계좌가 여러 개입니다. 번호를 골라 주세요." % state[slot + "_name"]]
    for number, account in enumerate(candidates, start=1):
        lines.append("%d. %s (%s)" % (number, account["nickname"], account["account_number"]))
    text = "\n".join(lines)

    with logger.get_logger().node("transfer_confirm"):
        logger.get_logger().interrupt_pause("사용자 확인 (후보 %d개)" % len(candidates))

    answer = interrupt(question(text)).strip()

    if answer == "취소":
        return {"error": "이체를 취소했습니다."}
    if answer.isdigit() and 1 <= int(answer) <= len(candidates):
        picked = candidates[int(answer) - 1]
        return {slot + "_account": picked["account_id"], slot + "_name": picked["nickname"]}
    return {}       # 번호가 아니면 check 로 돌아가 다시 고르게 합니다


def transfer_ask_node(state: BankState):
    if not state.get("from_account"):
        ask = "[출금] 돈을 보낼 계좌를 알려주세요."
    elif not state.get("to_account"):
        ask = "[입금] 돈을 받을 계좌를 알려주세요."
    else:
        ask = "[금액] 얼마를 보낼까요?"

    # 지금까지 알아낸 것을 같이 보여줍니다. 그래야 무엇을 알아들었는지 알 수 있습니다.
    from_text = state["from_name"] if state.get("from_account") else "?"
    to_text = state["to_name"] if state.get("to_account") else "?"
    amount_text = format(state["amount"], ",") + "원" if state.get("amount") else "?"

    text = "\n".join([
        "=" * 40,
        "  출금 : " + from_text,
        "  입금 : " + to_text,
        "  금액 : " + amount_text,
        "-" * 40,
        "  " + ask,
        "=" * 40,
    ])

    with logger.get_logger().node("transfer_ask"):
        logger.get_logger().interrupt_pause("질문: " + ask)

    answer = interrupt(question(text)).strip()

    if answer == "취소":
        return {"error": "이체를 취소했습니다."}
    # 답을 새 입력으로 삼아 extract 로 돌아갑니다. 무엇을 물었는지도 같이 넘깁니다.
    return {"query": answer, "question": ask}


def transfer_propose_node(state: BankState):
    # 처리안을 만듭니다. 잔액은 읽기만 합니다. 저장은 승인된 뒤에만 합니다.
    log = logger.get_logger()
    with log.node("transfer_propose"):
        from_account = functions.get_account(functions.CURRENT_USER, state["from_account"])
        to_account = functions.get_account(functions.CURRENT_USER, state["to_account"])
        amount = state["amount"]

        proposal = {
            "task": "이체",
            "rows": [
                ["출금", "%s (%s)" % (from_account["nickname"], from_account["account_number"])],
                ["입금", "%s (%s)" % (to_account["nickname"], to_account["account_number"])],
                ["금액", format(amount, ",") + "원"],
                ["출금 후 잔액", format(from_account["balance"] - amount, ",") + "원"],
            ],
        }
        if state.get("keep_amount") is not None:
            proposal["rows"].insert(2, ["남길 금액", format(state["keep_amount"], ",") + "원"])
        log.detail("처리안  %s → %s  %s원  (출금 잔액 %s)" % (
            from_account["account_id"], to_account["account_id"],
            format(amount, ","), format(from_account["balance"], ",")))

    return {"proposal": proposal, "approval": "대기"}


def transfer_revise_node(state: BankState):
    # "아니, 5만원만" 처럼 바꾼 칸만 새 값으로 덮어씁니다.
    # 계좌 이름이 바뀌면 찾아 둔 ID 를 비워서 check 가 다시 찾게 합니다.
    log = logger.get_logger()
    with log.node("transfer_revise"):
        prompt = revise_prompt.format(
            from_name=state["from_name"], to_name=state["to_name"], amount=state["amount"])
        result = llm_with_transfer_output.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=state["query"]),
        ])
        log.detail("수정  출금=%s  입금=%s  금액=%s" % (result.from_name, result.to_name, result.amount))

        update = {}
        if result.from_name and result.from_name != state["from_name"]:
            update["from_name"] = result.from_name
            update["from_account"] = None
        if result.to_name and result.to_name != state["to_name"]:
            update["to_name"] = result.to_name
            update["to_account"] = None
        if result.amount and result.amount != state["amount"]:
            update["amount"] = result.amount
            update["keep_amount"] = None        # 금액을 직접 말했으면 조건부가 아니라 즉시이체입니다

    return update


def transfer_execute_node(state: BankState):
    # 승인된 뒤에만 옵니다. 바꾼 데이터를 new_data 로 넘기고, 저장은 common_save 가 합니다.
    log = logger.get_logger()
    with log.node("transfer_execute"):
        data = data_store.load()

        # 조건부 이체 : 승인한 뒤 잔액이 바뀌면 이체액도 바뀝니다. 그러면 실행하지 않고 다시 요청하게 합니다.
        keep = state.get("keep_amount")
        if keep is not None:
            balance = next(a["balance"] for a in data["accounts"] if a["account_id"] == state["from_account"])
            if balance - keep != state["amount"]:
                log.detail("재검증 실패  이체액 %s → %s" % (format(state["amount"], ","), format(balance - keep, ",")))
                return {"result": "실패", "error": "잔액이 바뀌어 이체할 금액이 달라졌습니다. "
                        "이체하지 않았습니다. 다시 요청해 주세요."}

        error = functions.transfer(data, state["from_account"], state["to_account"], state["amount"])
        if error:
            log.detail("재검증 실패  " + error)
            return {"result": "실패", "error": error + " 이체하지 않았습니다."}

        balance = next(a["balance"] for a in data["accounts"] if a["account_id"] == state["from_account"])
        log.detail("재검증 OK / 거래 내역 +2")
        answer = "%s → %s  %s원 이체했습니다.\n%s 잔액 %s원" % (
            state["from_name"], state["to_name"], format(state["amount"], ","),
            state["from_name"], format(balance, ","))
        last_transfer = "출금=%s, 입금=%s" % (state["from_name"], state["to_name"])

    return {"new_data": data, "answer": answer, "last_transfer": last_transfer, "result": "완료"}


def transfer_fail_node(state: BankState):
    with logger.get_logger().node("transfer_fail"):
        answer = state["error"]
    return {"answer": answer}


# ---------------------------------------------------------------- 분기
def route_after_check(state: BankState):
    if state.get("error"):
        return "transfer_fail"
    if state.get("candidates"):
        return "transfer_confirm"
    if not state.get("from_account") or not state.get("to_account") or not state.get("amount"):
        return "transfer_ask"
    return "transfer_propose"


def route_after_confirm(state: BankState):
    if state.get("error"):
        return "transfer_fail"
    return "transfer_check"


def route_after_ask(state: BankState):
    if state.get("error"):
        return "transfer_fail"
    return "transfer_extract"


def route_after_interpret(state: BankState):
    decision = state["approval"]
    if decision == "승인":
        return "transfer_execute"
    if decision in ("거절", "취소"):
        return "common_reject"
    if decision == "수정":
        return "transfer_revise"
    return "common_approve"         # 모름 : 다시 묻습니다
