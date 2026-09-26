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

from datetime import datetime
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


class Split(BaseModel):
    to_name: str = Field(description="돈을 받는 계좌 이름")
    amount: Optional[int] = Field(default=None, description="이 계좌로 보낼 금액 (원)")


class TransferInfo(BaseModel):
    from_name: Optional[str] = Field(default=None, description="돈을 보내는 계좌 이름")
    to_name: Optional[str] = Field(default=None, description="돈을 받는 계좌 이름")
    amount: Optional[int] = Field(default=None, description="보낼 금액 (원)")
    keep_amount: Optional[int] = Field(default=None, description="출금 계좌에 남길 금액 (원). 조건부 이체일 때만")
    splits: Optional[list[Split]] = Field(default=None, description="입금 계좌가 두 곳 이상일 때만. 계좌별 금액")
    scheduled_at: Optional[str] = Field(default=None, description="예약 이체 시각 YYYY-MM-DDTHH:MM. 예약일 때만")


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
            now=datetime.now().strftime("%Y-%m-%dT%H:%M (%A)"),
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
        # 나눠 이체 : 입금 계좌가 두 곳 이상이면 계좌별 금액 목록으로 받습니다.
        if result.splits and len(result.splits) >= 2 and not state.get("splits"):
            update["splits"] = [split.model_dump() for split in result.splits]
            log.detail("나눠 이체  %s" % update["splits"])
        # 예약 이체 : 시각을 말하면 지금 보내지 않고 예약만 합니다.
        if result.scheduled_at and not state.get("scheduled_at"):
            update["scheduled_at"] = result.scheduled_at
            log.detail("예약 시각  %s" % result.scheduled_at)

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

        # 입금 목록을 만들고, 실행할 수 있는지 봅니다. 계산은 functions 가 합니다 (원칙 6).
        targets, error = functions.build_targets(
            functions.CURRENT_USER, from_account, to_account,
            update.get("to_name") or state.get("to_name"), state.get("amount"),
            state.get("keep_amount"), state.get("splits"))
        if targets and not error:
            error = functions.check_transfer(functions.CURRENT_USER, from_account, targets, state.get("keep_amount"))
        if targets and not error and state.get("scheduled_at"):
            error = functions.check_schedule(state["scheduled_at"], targets, state.get("keep_amount"))
        if error:
            update["error"] = error
        update["targets"] = targets
        if targets:
            log.detail("입금 목록  %s" % ", ".join("%s %s원" % (t["to_name"], format(t["amount"], ",")) for t in targets))

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
        targets = state["targets"]
        total = sum(target["amount"] for target in targets)

        rows = [["출금", "%s (%s)" % (from_account["nickname"], from_account["account_number"])]]
        if state.get("keep_amount") is not None:
            rows.append(["남길 금액", format(state["keep_amount"], ",") + "원"])
        for number, target in enumerate(targets, start=1):
            to_account = functions.get_account(functions.CURRENT_USER, target["to_account"])
            label = "입금" if len(targets) == 1 else "입금 %d" % number
            rows.append([label, "%s (%s)  %s원" % (
                to_account["nickname"], to_account["account_number"], format(target["amount"], ","))])
        rows.append(["총액", format(total, ",") + "원"])
        rows.append(["출금 후 잔액", format(from_account["balance"] - total, ",") + "원"])

        proposal = {"task": "이체", "rows": rows}
        if state.get("scheduled_at"):
            proposal["task"] = "예약 이체"
            rows.insert(0, ["예약 시각", functions.parse_time(state["scheduled_at"]).strftime("%Y-%m-%d %H:%M")])
        log.detail("처리안  %s → %d곳  총 %s원  (출금 잔액 %s)" % (
            from_account["account_id"], len(targets), format(total, ","), format(from_account["balance"], ",")))

    return {"proposal": proposal, "approval": "대기"}


def transfer_revise_node(state: BankState):
    # "아니, 5만원만" 처럼 바꾼 칸만 새 값으로 덮어씁니다.
    # 계좌 이름이 바뀌면 찾아 둔 ID 를 비워서 check 가 다시 찾게 합니다.
    log = logger.get_logger()
    with log.node("transfer_revise"):
        targets = ", ".join("%s %s원" % (t["to_name"], format(t["amount"], ",")) for t in state["targets"])
        prompt = revise_prompt.format(from_name=state["from_name"], targets=targets)
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
        if result.splits and len(result.splits) >= 2:
            update["splits"] = [split.model_dump() for split in result.splits]

    return update


def transfer_execute_node(state: BankState):
    # 승인된 뒤에만 옵니다. 바꾼 데이터를 new_data 로 넘기고, 저장은 common_save 가 합니다.
    log = logger.get_logger()
    with log.node("transfer_execute"):
        data = data_store.load()

        # 예약 이체 : 돈은 옮기지 않고 예약만 남깁니다. 시각이 되면 main.py 가 실행합니다.
        if state.get("scheduled_at"):
            target = state["targets"][0]
            functions.add_schedule(data, functions.CURRENT_USER, state["from_account"], target, state["scheduled_at"])
            answer = "%s → %s  %s원\n%s 에 이체하도록 예약했습니다." % (
                state["from_name"], target["to_name"], format(target["amount"], ","),
                functions.parse_time(state["scheduled_at"]).strftime("%m월 %d일 %H:%M"))
            return {"new_data": data, "answer": answer, "result": "완료"}

        # 하나라도 안 되면 new_data 를 넘기지 않으므로 아무것도 저장되지 않습니다 (전부 아니면 전무).
        error = functions.transfer_all(data, state["from_account"], state["targets"], state.get("keep_amount"))
        if error:
            log.detail("재검증 실패  " + error)
            return {"result": "실패", "error": "이체하지 않았습니다. " + error}

        lines = ["%s → %s  %s원" % (state["from_name"], target["to_name"], format(target["amount"], ","))
                 for target in state["targets"]]
        balance = next(a["balance"] for a in data["accounts"] if a["account_id"] == state["from_account"])
        log.detail("재검증 OK / 거래 내역 +%d" % (len(state["targets"]) * 2))
        answer = "\n".join(lines) + "\n이체했습니다. %s 잔액 %s원" % (state["from_name"], format(balance, ","))
        last_transfer = "출금=%s, 입금=%s" % (
            state["from_name"], ", ".join(target["to_name"] for target in state["targets"]))

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
    if not state.get("from_account") or not state.get("targets"):
        return "transfer_ask"
    return "common_authenticate"


def route_after_authenticate(state: BankState):
    if state.get("error"):
        return "transfer_fail"
    if state.get("authenticated"):
        return "transfer_propose"
    return "common_authenticate"        # 틀렸으면 다시 묻습니다


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
