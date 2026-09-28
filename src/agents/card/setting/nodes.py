# 카드 설정 에이전트(3단)의 노드 함수입니다.
#   상태 바꾸기 : 분실 신고 / 일시 잠금 / 잠금 해제 / 해지   (4-3, 해지는 4-4)
#   값 바꾸기   : 별칭 변경 / 비밀번호 변경                   (4-4)
#   새로 넣기   : 카드 등록                                   (4-4)
#
#   card_setting_extract  : 사용자 말에서 할 일과 필요한 값을 뽑습니다 (LLM). 비밀번호는 뽑지 않습니다
#   card_setting_check    : 카드를 한 장으로 정하고, 할 수 있는지 봅니다 (Python)
#   card_setting_password : 비밀번호 변경일 때 새 비밀번호를 가린 입력으로 받습니다 (LLM 을 거치지 않습니다)
#   card_setting_propose  : 처리안을 만듭니다. 계산만 하고 저장하지 않습니다
#   card_setting_execute  : 승인되면 데이터를 바꿉니다 (저장은 common_save)
#   card_setting_fail     : 진행할 수 없는 사유를 알려줍니다
#   (인증·승인·응답 해석·거절·기록·저장·안내는 공통 노드를 씁니다)
#
# State 는 계좌 설정 칸을 같이 씁니다.
#   setting_action = 할 일, target_name = 말한 카드 이름, target_account = 찾아낸 card_id,
#   new_value = 분실 사유 / 새 별칭 / 새 비밀번호, reg_info = 등록할 카드 정보

from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

import data_store
import functions
import logger
from agents.card.setting.prompts import extract_prompt
from agents.common.nodes import is_cancel, secret
from model import llm
from state import BankState


class CardSettingInfo(BaseModel):
    action: Optional[Literal["분실 신고", "일시 잠금", "잠금 해제", "해지", "별칭 변경", "비밀번호 변경", "등록"]] = Field(
        default=None, description="할 일")
    card_name: Optional[str] = Field(default=None, description="대상 카드 이름")
    reason: Optional[Literal["분실", "도난", "부정사용"]] = Field(default=None, description="분실 신고 사유")
    new_name: Optional[str] = Field(default=None, description="새 별칭, 또는 등록할 카드에 붙일 별칭")
    bank_name: Optional[str] = Field(default=None, description="등록할 카드의 은행 이름")
    card_number: Optional[str] = Field(default=None, description="등록할 카드 번호")
    card_type: Optional[Literal["체크", "신용"]] = Field(default=None, description="등록할 카드 종류")
    account_name: Optional[str] = Field(default=None, description="등록할 카드의 결제 계좌 이름")
    reissue: Optional[bool] = Field(default=None, description="분실 신고와 함께 재발급도 원하는지")
    address: Optional[str] = Field(default=None, description="재발급 카드를 받을 곳 (집 / 회사)")


llm_with_card_setting_output = llm.with_structured_output(CardSettingInfo)


def card_setting_extract_node(state: BankState):
    # 승인 전 수정("아니 여행 카드", "별칭은 휴가로")도 여기로 돌아와 말한 값만 덮어씁니다.
    log = logger.get_logger()
    with log.node("card_setting_extract"):
        prompt = extract_prompt.format(
            action=state.get("setting_action") or "모름",
            card_name=state.get("target_name") or "모름",
            reg_info=state.get("reg_info") or "없음",
        )
        r = llm_with_card_setting_output.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=state["query"]),
        ])
        log.detail("추출  할 일=%s  카드=%s  사유=%s  새 별칭=%s  등록=%s %s %s %s" % (
            r.action, r.card_name, r.reason, r.new_name, r.bank_name, r.card_number, r.card_type, r.account_name))

        update = {}
        if r.action and not state.get("setting_action"):
            update["setting_action"] = r.action
        action = update.get("setting_action") or state.get("setting_action")

        if action == "등록":
            # 등록할 카드 정보는 한 묶음(reg_info)으로 둡니다. 말한 칸만 덮어씁니다.
            reg = dict(state.get("reg_info") or {})
            for key in ["bank_name", "card_type", "account_name"]:
                if getattr(r, key):
                    reg[key] = getattr(r, key)
            if r.card_number:
                reg["card_number"] = functions.normalize_card_number(r.card_number)
            if r.new_name:
                reg["name"] = r.new_name.strip()
            update["reg_info"] = reg
            return update

        if r.card_name:
            # 카드를 다시 말하면 새로 찾아야 하므로 찾아 둔 card_id 를 비웁니다.
            update["target_name"] = r.card_name
            update["target_account"] = None
        if action == "분실 신고" and r.reason:
            update["new_value"] = r.reason
        # 정지 후 재발급 (4-7) : 분실 신고가 끝나면 이어서 재발급으로 넘어가도록 표시만 해 둡니다.
        if action == "분실 신고" and r.reissue:
            update["reissue_next"] = True
        if action == "분실 신고" and r.address:
            update["reissue_address"] = r.address
        if action == "별칭 변경" and r.new_name:
            update["new_value"] = r.new_name

    return update


def card_setting_check_node(state: BankState):
    log = logger.get_logger()
    with log.node("card_setting_check"):
        action = state.get("setting_action")
        if not action:
            return {"error": "카드로 무엇을 할지 말해 주세요. (예: 여행 카드 잠가줘 / 생활비 카드 별칭을 장보기로 바꿔줘)"}

        if action == "등록":
            reg = dict(state.get("reg_info") or {})
            # 결제 계좌는 내 계좌여야 하므로 이름으로 찾아 한 개로 정합니다.
            if reg.get("account_name"):
                found = functions.find_accounts(functions.CURRENT_USER, reg["account_name"])
                if len(found) != 1:
                    return {"error": "결제 계좌 '%s' 를 하나로 정할 수 없습니다. 정확한 계좌 이름으로 다시 요청해 주세요." % reg["account_name"]}
                reg["account_id"] = found[0]["account_id"]
            # 별칭을 안 말하면 "은행 이름 + 체크/신용카드" 로 붙입니다. 예) 미래은행 체크카드
            reg.setdefault("name", "%s %s카드" % (reg.get("bank_name", ""), reg.get("card_type", "")))
            error = functions.check_card_register(functions.CURRENT_USER, reg)
            return {"error": error} if error else {"reg_info": reg}

        if not state.get("target_name"):
            return {"error": "어느 카드인지 말해 주세요. (예: 여행 카드 잠가줘 / 생활비 카드 분실 신고해줘)"}

        # 카드를 한 장으로 정합니다. 여러 장이면 후보를 보여주고 정확한 이름으로 다시 요청하게 합니다.
        found = functions.pick_cards(functions.CURRENT_USER, state["target_name"])
        log.resolve(state["target_name"], len(found), found[0]["card_id"] if found else None)
        if not found:
            return {"error": "'%s' 카드를 찾을 수 없습니다." % state["target_name"]}
        if len(found) > 1:
            lines = ["'%s' 에 맞는 카드가 %d장입니다. 정확한 이름으로 다시 요청해 주세요." % (state["target_name"], len(found))]
            lines += ["- %s  [%s]" % (c["name"], functions.CARD_STATUS[c["status"]]) for c in found]
            return {"error": "\n".join(lines)}

        card = found[0]
        # 상태 전이 검사. 할 수 없는 변경이면 여기서 끝냅니다 (인증·승인까지 가지 않습니다).
        error = functions.check_card_status(card, action)
        if not error and action == "별칭 변경":
            error = functions.check_card_alias(functions.CURRENT_USER, card, state.get("new_value"))
        if error:
            return {"error": error}

    return {"target_account": card["card_id"]}


def card_setting_password_node(state: BankState):
    # 새 비밀번호는 LLM 이 뽑지 않고 여기서 따로 받습니다. 가린 입력(secret)이라 화면·로그에 남지 않습니다.
    log = logger.get_logger()
    with log.node("card_setting_password"):
        log.interrupt_pause("새 카드 비밀번호")

    answer = interrupt(secret("새 카드 비밀번호 숫자 4자리를 입력해 주세요.")).strip()

    if is_cancel(answer):
        return {"error": "비밀번호 변경을 취소했습니다."}
    card = next(c for c in functions.get_cards(functions.CURRENT_USER) if c["card_id"] == state["target_account"])
    error = functions.check_card_password(card, answer)
    if error:
        return {"error": error}
    return {"new_value": answer}


def card_row(card_id):
    card = next(c for c in functions.get_cards(functions.CURRENT_USER) if c["card_id"] == card_id)
    return card, ["카드", "%s (%s)" % (card["name"], card["card_number"])]


def card_setting_propose_node(state: BankState):
    with logger.get_logger().node("card_setting_propose"):
        action = state["setting_action"]

        if action == "등록":
            reg = state["reg_info"]
            account = functions.get_account(functions.CURRENT_USER, reg["account_id"])
            rows = [
                ["은행", reg["bank_name"]],
                ["카드 번호", reg["card_number"]],
                ["종류", reg["card_type"]],
                ["결제 계좌", "%s (%s)" % (account["nickname"], account["account_number"])],
                ["별칭", reg["name"]],
            ]
        elif action == "별칭 변경":
            card, row = card_row(state["target_account"])
            rows = [row, ["지금 별칭", card["name"]], ["새 별칭", state["new_value"].strip()]]
        elif action == "비밀번호 변경":
            _, row = card_row(state["target_account"])
            rows = [row, ["새 비밀번호", "****"]]     # 처리안과 처리 기록에 비밀번호를 남기지 않습니다
        else:
            card, row = card_row(state["target_account"])
            rows = [
                row,
                ["지금 상태", functions.CARD_STATUS[card["status"]]],
                ["바뀔 상태", functions.CARD_STATUS[functions.CARD_ACTIONS[action]]],
            ]
            if action == "분실 신고":
                rows.append(["사유", state.get("new_value") or "분실"])
                rows.append(["주의", "분실 정지는 해제할 수 없고 재발급만 가능합니다"])
            if action == "해지":
                rows.append(["주의", "해지하면 되돌릴 수 없습니다"])

    return {"proposal": {"task": "카드 " + action, "rows": rows}, "approval": "대기"}


def card_setting_execute_node(state: BankState):
    # 승인된 뒤에만 옵니다. 바꾼 데이터를 new_data 로 넘기고, 저장은 common_save 가 합니다.
    with logger.get_logger().node("card_setting_execute"):
        data = data_store.load()
        action = state["setting_action"]

        if action == "등록":
            functions.register_card(data, functions.CURRENT_USER, state["reg_info"])
            answer = "카드를 등록했습니다. (%s)\n카드 비밀번호는 '비밀번호 변경' 으로 정해 주세요." % state["reg_info"]["name"]
            return {"new_data": data, "answer": answer, "result": "완료"}

        card = next(c for c in data["cards"] if c["card_id"] == state["target_account"])
        if action == "별칭 변경":
            old = card["name"]
            functions.set_card_value(data, card["card_id"], "name", state["new_value"])
            answer = "카드 별칭 변경 완료 : %s → %s" % (old, card["name"])
        elif action == "비밀번호 변경":
            functions.set_card_value(data, card["card_id"], "card_password", state["new_value"])
            answer = "카드 비밀번호를 바꿨습니다. (%s)" % card["name"]
        else:
            old = functions.CARD_STATUS[card["status"]]
            functions.change_card_status(data, card["card_id"], action, state.get("new_value"))
            answer = "카드 %s 완료 : %s  %s → %s" % (action, card["name"], old, functions.CARD_STATUS[card["status"]])

    return {"new_data": data, "answer": answer, "result": "완료"}


def card_setting_fail_node(state: BankState):
    with logger.get_logger().node("card_setting_fail"):
        answer = state["error"]
    return {"answer": answer}


# ---------------------------------------------------------------- 분기
def route_after_check(state: BankState):
    if state.get("error"):
        return "card_setting_fail"
    return "common_authenticate"


def route_after_authenticate(state: BankState):
    if state.get("error"):
        return "card_setting_fail"
    if not state.get("authenticated"):
        return "common_authenticate"    # 틀렸으면 다시 묻습니다
    # 비밀번호 변경은 본인 확인 뒤에 새 비밀번호를 받습니다. (수정으로 돌아왔을 때 이미 받았으면 건너뜁니다)
    if state["setting_action"] == "비밀번호 변경" and not state.get("new_value"):
        return "card_setting_password"
    return "card_setting_propose"


def route_after_password(state: BankState):
    if state.get("error"):
        return "card_setting_fail"
    return "card_setting_propose"


def route_after_interpret(state: BankState):
    decision = state["approval"]
    if decision == "승인":
        return "card_setting_execute"
    if decision in ("거절", "취소", "다른요청"):
        return "common_reject"
    if decision == "수정":
        return "card_setting_extract"   # 바꾼 말로 다시 뽑고 처리안을 새로 만듭니다
    return "common_approve"             # 모름 : 다시 묻습니다
