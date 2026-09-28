# 카드 재발급 에이전트(3단)의 노드 함수입니다.
# 재발급 신청 / 신청 조회 (4-5), 배송지 수정 / 신청 취소 (4-6) 를 맡습니다.
# 수정·취소는 신청이 접수 상태일 때만 됩니다. 제작중·배송중이면 불가 안내로 끝납니다.
#
#   reissue_extract : 사용자 말에서 할 일과 카드 이름, 배송지를 뽑습니다 (LLM)
#   reissue_list    : 신청 목록을 보여줍니다. 읽기만 하므로 승인 없이 끝납니다
#   reissue_check   : 카드와 배송지를 하나로 정하고, 할 수 있는지 봅니다 (Python)
#   reissue_propose : 처리안을 만듭니다. 계산만 하고 저장하지 않습니다
#   reissue_execute : 승인되면 신청을 넣거나, 배송지를 바꾸거나, 취소합니다 (저장은 common_save)
#   reissue_fail    : 진행할 수 없는 사유를 알려줍니다
#   (인증·승인·응답 해석·거절·기록·저장·안내는 공통 노드를 씁니다)
#
# State 는 설정 칸을 같이 씁니다.
#   setting_action = 할 일, target_name = 말한 카드 이름, target_account = 찾아낸 card_id,
#   new_value = 말한 배송지, address_id = 찾아낸 배송지 ID

from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import data_store
import functions
import logger
from agents.card.reissue.prompts import extract_prompt
from model import llm
from state import BankState


class ReissueInfo(BaseModel):
    action: Optional[Literal["신청", "조회", "배송지 수정", "신청 취소"]] = Field(default=None, description="할 일")
    card_name: Optional[str] = Field(default=None, description="대상 카드 이름")
    address: Optional[str] = Field(default=None, description="받을 곳 (집 / 회사)")


llm_with_reissue_output = llm.with_structured_output(ReissueInfo)


def reissue_extract_node(state: BankState):
    # 승인 전 수정("아니 회사로")도 여기로 돌아와 말한 값만 덮어씁니다.
    log = logger.get_logger()
    with log.node("reissue_extract"):
        prompt = extract_prompt.format(
            action=state.get("setting_action") or "모름",
            card_name=state.get("target_name") or "모름",
            address=state.get("new_value") or "모름",
        )
        r = llm_with_reissue_output.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=state["query"]),
        ])
        log.detail("추출  할 일=%s  카드=%s  배송지=%s" % (r.action, r.card_name, r.address))

        update = {}
        if r.action and not state.get("setting_action"):
            update["setting_action"] = r.action
        if r.card_name:
            update["target_name"] = r.card_name
            update["target_account"] = None
        if r.address:
            update["new_value"] = r.address
            update["address_id"] = None

    return update


def application_text(app):
    # 신청 한 건을 한 줄로 씁니다. 예) app-001  구 생활비 카드  → 집 (가상시 가상구 집로 10)  [제작중]  09월 15일 신청
    cards = {c["card_id"]: c["name"] for c in functions.get_cards(functions.CURRENT_USER)}
    addresses = {a["address_id"]: a for a in functions.get_addresses(functions.CURRENT_USER)}
    address = addresses.get(app["address_id"])
    return "%s  %s  → %s  [%s]  %s 신청" % (
        app["application_id"], cards.get(app["card_id"], app["card_id"]),
        "%s (%s)" % (address["label"], address["address"]) if address else app["address_id"],
        functions.REISSUE_STATUS[app["status"]],
        functions.parse_time(app["created_at"]).strftime("%m월 %d일"))


def reissue_list_node(state: BankState):
    with logger.get_logger().node("reissue_list"):
        apps = functions.get_applications(functions.CURRENT_USER)
        # 카드를 말했으면 그 카드 신청만 봅니다.
        if state.get("target_name"):
            card_ids = [c["card_id"] for c in functions.pick_cards(functions.CURRENT_USER, state["target_name"])]
            apps = [a for a in apps if a["card_id"] in card_ids]
        if not apps:
            return {"answer": "재발급 신청이 없습니다."}
        lines = ["재발급 신청 %d건입니다." % len(apps)]
        lines += ["- " + application_text(a) for a in apps]
    return {"answer": "\n".join(lines)}


def address_guide():
    names = ", ".join("%s(%s)" % (a["label"], a["address"]) for a in functions.get_addresses(functions.CURRENT_USER))
    return "받을 곳을 말해 주세요. 등록된 배송지 : %s\n(예: 생활비 카드 재발급해줘 집으로)" % names


def reissue_check_node(state: BankState):
    log = logger.get_logger()
    with log.node("reissue_check"):
        action = state.get("setting_action")
        if not state.get("target_name"):
            return {"error": "어느 카드인지 말해 주세요. (예: 생활비 카드 재발급해줘 집으로 / 구 생활비 카드 재발급 취소해줘)"}

        # 카드를 한 장으로 정합니다. 여러 장이면 common_pick_card 가 번호로 고르게 합니다. (카드 설정과 같은 방식)
        found = functions.pick_cards(functions.CURRENT_USER, state["target_name"])
        log.resolve(state["target_name"], len(found), found[0]["card_id"] if found else None)
        if not found:
            return {"error": "'%s' 카드를 찾을 수 없습니다." % state["target_name"]}
        if len(found) > 1:
            return {"candidates": found}
        card = found[0]

        if action == "신청 취소":
            # 이 카드의 진행 중인 신청이 접수 상태인지 봅니다.
            app = functions.find_open_application(functions.CURRENT_USER, card["card_id"])
            if not app:
                return {"error": "진행 중인 재발급 신청이 없습니다. (%s)" % card["name"]}
            error = functions.check_application(app, action)
            return {"error": error} if error else {"target_account": card["card_id"]}

        if action == "신청":
            # 분실 정지 카드인지, 진행 중인 신청이 없는지 봅니다.
            error = functions.check_reissue(functions.CURRENT_USER, card)
            if error:
                return {"error": error}

        # 배송지를 하나로 정합니다. (신청, 배송지 수정)
        addresses = functions.find_addresses(functions.CURRENT_USER, state.get("new_value"))
        if len(addresses) != 1:
            return {"error": address_guide()}
        address_id = addresses[0]["address_id"]

        if action == "배송지 수정":
            app = functions.find_open_application(functions.CURRENT_USER, card["card_id"])
            if not app:
                return {"error": "진행 중인 재발급 신청이 없습니다. (%s)" % card["name"]}
            error = functions.check_application(app, action, address_id)
            if error:
                return {"error": error}

    return {"target_account": card["card_id"], "address_id": address_id}


def reissue_propose_node(state: BankState):
    with logger.get_logger().node("reissue_propose"):
        action = state["setting_action"]
        card = functions.get_card(functions.CURRENT_USER, state["target_account"])
        addresses = {a["address_id"]: a for a in functions.get_addresses(functions.CURRENT_USER)}
        card_row = ["카드", "%s (%s)" % (card["name"], card["card_number"])]

        if action == "신청":
            address = addresses[state["address_id"]]
            rows = [
                card_row,
                ["지금 상태", functions.CARD_STATUS[card["status"]]],
                ["배송지", "%s (%s)" % (address["label"], address["address"])],
                ["안내", "신청해도 기존 카드의 분실 정지는 그대로입니다"],
            ]
            if state.get("reissue_next"):
                rows.insert(0, ["앞 단계", "분실 신고 완료 (재발급을 거절해도 분실 정지는 유지)"])
        else:
            app = functions.find_open_application(functions.CURRENT_USER, card["card_id"])
            rows = [["신청", app["application_id"]], card_row, ["신청 상태", functions.REISSUE_STATUS[app["status"]]]]
            if action == "배송지 수정":
                old, new = addresses[app["address_id"]], addresses[state["address_id"]]
                rows.append(["지금 배송지", "%s (%s)" % (old["label"], old["address"])])
                rows.append(["새 배송지", "%s (%s)" % (new["label"], new["address"])])
            else:
                rows.append(["안내", "취소해도 기존 카드의 분실 정지는 그대로입니다"])

    return {"proposal": {"task": "카드 재발급 " + action, "rows": rows}, "approval": "대기"}


def reissue_execute_node(state: BankState):
    # 승인된 뒤에만 옵니다. 바꾼 데이터를 new_data 로 넘기고, 저장은 common_save 가 합니다.
    with logger.get_logger().node("reissue_execute"):
        data = data_store.load()
        action = state["setting_action"]
        if action == "신청":
            app_id = functions.add_reissue(data, functions.CURRENT_USER, state["target_account"], state["address_id"])
            answer = "재발급을 신청했습니다. (%s  [접수])" % app_id
        else:
            app = functions.find_open_application(functions.CURRENT_USER, state["target_account"])
            functions.change_application(data, app["application_id"], action, state.get("address_id"))
            if action == "배송지 수정":
                address = next(a for a in data["addresses"] if a["address_id"] == state["address_id"])
                answer = "재발급 배송지를 바꿨습니다. (%s → %s)" % (app["application_id"], address["label"])
            else:
                answer = "재발급 신청을 취소했습니다. (%s  [취소됨])" % app["application_id"]
    return {"new_data": data, "answer": answer, "result": "완료"}


def reissue_fail_node(state: BankState):
    with logger.get_logger().node("reissue_fail"):
        answer = state["error"]
        if state.get("reissue_next"):
            answer = "분실 신고는 완료했습니다. 재발급은 진행하지 못했습니다.\n" + answer
    return {"answer": answer}


# ---------------------------------------------------------------- 분기
def route_start(state: BankState):
    # 분실 신고에서 이어 온 경우(4-7)는 할 일과 카드가 이미 정해져 있으므로 뽑기를 건너뜁니다.
    if state.get("reissue_next"):
        return "reissue_check"
    return "reissue_extract"


def route_after_extract(state: BankState):
    # 조회는 읽기만 하므로 인증·승인 없이 바로 보여줍니다.
    if state.get("setting_action") == "조회":
        return "reissue_list"
    return "reissue_check"


def route_after_check(state: BankState):
    if state.get("error"):
        return "reissue_fail"
    if state.get("candidates"):
        return "common_pick_card"
    return "common_authenticate"


def route_after_pick(state: BankState):
    if state.get("error"):
        return "reissue_fail"
    return "reissue_check"


def route_after_authenticate(state: BankState):
    if state.get("error"):
        return "reissue_fail"
    if state.get("authenticated"):
        return "reissue_propose"
    return "common_authenticate"        # 틀렸으면 다시 묻습니다


def route_after_interpret(state: BankState):
    decision = state["approval"]
    if decision == "승인":
        return "reissue_execute"
    if decision in ("거절", "취소", "다른요청"):
        return "common_reject"
    if decision == "수정":
        return "reissue_extract"        # 바꾼 말로 다시 뽑고 처리안을 새로 만듭니다
    return "common_approve"             # 모름 : 다시 묻습니다
