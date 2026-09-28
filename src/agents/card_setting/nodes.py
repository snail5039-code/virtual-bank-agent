# 카드 설정 에이전트(3단)의 노드 함수입니다.
# 지금은 분실 신고 / 일시 잠금 / 잠금 해제 (카드 상태 바꾸기) 를 맡습니다. 나머지 설정은 준비 중입니다.
#
#   card_setting_extract : 사용자 말에서 할 일과 카드 이름, 분실 사유를 뽑습니다 (LLM)
#   card_setting_check   : 카드를 한 장으로 정하고, 지금 상태에서 할 수 있는지 봅니다 (Python)
#   card_setting_propose : 처리안을 만듭니다. 계산만 하고 저장하지 않습니다
#   card_setting_execute : 승인되면 카드 상태를 바꿉니다 (저장은 common_save)
#   card_setting_fail    : 진행할 수 없는 사유를 알려줍니다
#   (인증·승인·응답 해석·거절·기록·저장·안내는 공통 노드를 씁니다)
#
# State 는 계좌 설정 칸을 같이 씁니다.
#   setting_action = 할 일, target_name = 말한 카드 이름, target_account = 찾아낸 card_id, new_value = 분실 사유

from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import data_store
import functions
import logger
from agents.card_setting.prompts import extract_prompt
from model import llm
from state import BankState


class CardSettingInfo(BaseModel):
    action: Optional[Literal["분실 신고", "일시 잠금", "잠금 해제", "그 밖"]] = Field(default=None, description="할 일")
    card_name: Optional[str] = Field(default=None, description="대상 카드 이름")
    reason: Optional[Literal["분실", "도난", "부정사용"]] = Field(default=None, description="분실 신고 사유")


llm_with_card_setting_output = llm.with_structured_output(CardSettingInfo)


def card_setting_extract_node(state: BankState):
    # 승인 전 수정("아니 여행 카드")도 여기로 돌아와 말한 값만 덮어씁니다.
    log = logger.get_logger()
    with log.node("card_setting_extract"):
        prompt = extract_prompt.format(
            action=state.get("setting_action") or "모름",
            card_name=state.get("target_name") or "모름",
        )
        r = llm_with_card_setting_output.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=state["query"]),
        ])
        log.detail("추출  할 일=%s  카드=%s  사유=%s" % (r.action, r.card_name, r.reason))

        update = {}
        if r.action and not state.get("setting_action"):
            update["setting_action"] = r.action
        if r.card_name:
            # 카드를 다시 말하면 새로 찾아야 하므로 찾아 둔 card_id 를 비웁니다.
            update["target_name"] = r.card_name
            update["target_account"] = None
        if r.reason:
            update["new_value"] = r.reason

    return update


def card_setting_check_node(state: BankState):
    log = logger.get_logger()
    with log.node("card_setting_check"):
        action = state.get("setting_action")
        if action not in functions.CARD_ACTIONS:
            return {"error": "카드 등록·해지, 비밀번호 변경, 별칭 변경은 아직 준비 중입니다."}
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
        if error:
            return {"error": error}

    return {"target_account": card["card_id"]}


def card_setting_propose_node(state: BankState):
    with logger.get_logger().node("card_setting_propose"):
        card = next(c for c in functions.get_cards(functions.CURRENT_USER) if c["card_id"] == state["target_account"])
        action = state["setting_action"]
        rows = [
            ["카드", "%s (%s)" % (card["name"], card["card_number"])],
            ["지금 상태", functions.CARD_STATUS[card["status"]]],
            ["바뀔 상태", functions.CARD_STATUS[functions.CARD_ACTIONS[action]]],
        ]
        if action == "분실 신고":
            rows.append(["사유", state.get("new_value") or "분실"])
            rows.append(["주의", "분실 정지는 해제할 수 없고 재발급만 가능합니다"])
    return {"proposal": {"task": "카드 " + action, "rows": rows}, "approval": "대기"}


def card_setting_execute_node(state: BankState):
    # 승인된 뒤에만 옵니다. 바꾼 데이터를 new_data 로 넘기고, 저장은 common_save 가 합니다.
    with logger.get_logger().node("card_setting_execute"):
        data = data_store.load()
        action = state["setting_action"]
        card = next(c for c in data["cards"] if c["card_id"] == state["target_account"])
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
    if state.get("authenticated"):
        return "card_setting_propose"
    return "common_authenticate"        # 틀렸으면 다시 묻습니다


def route_after_interpret(state: BankState):
    decision = state["approval"]
    if decision == "승인":
        return "card_setting_execute"
    if decision in ("거절", "취소", "다른요청"):
        return "common_reject"
    if decision == "수정":
        return "card_setting_extract"   # 바꾼 말로 다시 뽑고 처리안을 새로 만듭니다
    return "common_approve"             # 모름 : 다시 묻습니다
