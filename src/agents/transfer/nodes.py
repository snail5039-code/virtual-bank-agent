# 이체 에이전트(3단)의 노드 함수입니다.
#
#   transfer_extract : 사용자 말에서 출금 계좌, 입금 계좌, 금액을 뽑습니다 (LLM)
#   transfer_check   : 계좌 이름을 ID 로 바꾸고, 무엇이 부족한지 봅니다 (Python)
#   transfer_confirm : 후보가 여러 개면 번호를 고르게 합니다 (interrupt)
#   transfer_ask     : 부족한 정보를 묻습니다 (interrupt)
#   transfer_ready   : 정보가 다 모였다고 알려줍니다 (실제 이체는 2-4 단계)
#   transfer_fail    : 진행할 수 없는 사유를 알려줍니다
#
# interrupt() 로 멈췄다가 답을 받으면 그 노드를 처음부터 다시 실행합니다.
# 그래서 interrupt 가 있는 노드에서는 묻고 답을 받는 일만 합니다.

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

import functions
import logger
from agents.transfer.prompts import extract_prompt
from model import llm
from state import BankState


class TransferInfo(BaseModel):
    from_name: Optional[str] = Field(default=None, description="돈을 보내는 계좌 이름")
    to_name: Optional[str] = Field(default=None, description="돈을 받는 계좌 이름")
    amount: Optional[int] = Field(default=None, description="보낼 금액 (원)")


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
        log.detail("추출  출금=%s  입금=%s  금액=%s" % (result.from_name, result.to_name, result.amount))

        # 비어 있는 칸만 채웁니다. 이미 정해진 값은 바꾸지 않습니다.
        update = {}
        if result.from_name and not state.get("from_account"):
            update["from_name"] = result.from_name
        if result.to_name and not state.get("to_account"):
            update["to_name"] = result.to_name
        if result.amount and not state.get("amount"):
            update["amount"] = result.amount

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

    return update


def transfer_confirm_node(state: BankState):
    slot = state["confirm_for"]
    candidates = state["candidates"]

    lines = ["'%s' 에 맞는 계좌가 여러 개입니다. 번호를 골라 주세요." % state[slot + "_name"]]
    for number, account in enumerate(candidates, start=1):
        lines.append("%d. %s (%s)" % (number, account["nickname"], account["account_number"]))
    question = "\n".join(lines)

    with logger.get_logger().node("transfer_confirm"):
        logger.get_logger().interrupt_pause("사용자 확인 (후보 %d개)" % len(candidates))

    answer = interrupt(question).strip()

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

    question = "\n".join([
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

    answer = interrupt(question).strip()

    if answer == "취소":
        return {"error": "이체를 취소했습니다."}
    # 답을 새 입력으로 삼아 extract 로 돌아갑니다. 무엇을 물었는지도 같이 넘깁니다.
    return {"query": answer, "question": ask}


def transfer_ready_node(state: BankState):
    with logger.get_logger().node("transfer_ready"):
        answer = "%s → %s  %s원\n이체 정보가 모두 모였습니다. (실제 이체는 2-4 단계에서 연결합니다)" % (
            state["from_name"], state["to_name"], format(state["amount"], ","))
        last_transfer = "출금=%s, 입금=%s" % (state["from_name"], state["to_name"])
    return {"answer": answer, "last_transfer": last_transfer}


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
    return "transfer_ready"


def route_after_confirm(state: BankState):
    if state.get("error"):
        return "transfer_fail"
    return "transfer_check"


def route_after_ask(state: BankState):
    if state.get("error"):
        return "transfer_fail"
    return "transfer_extract"
