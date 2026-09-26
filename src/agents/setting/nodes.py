# 계좌 설정 에이전트(3단)의 노드 함수입니다.
# 계좌 별명·용도 변경, 등록 계좌(상대 계좌 주소록) 등록·조회·삭제를 맡습니다.
#
#   setting_extract : 사용자 말에서 할 일(변경/등록/삭제/조회)과 필요한 값을 뽑습니다 (LLM)
#   setting_list    : 등록 계좌를 보여줍니다. 읽기만 하므로 승인 없이 끝납니다
#   setting_check   : 대상을 ID 로 바꾸고, 할 수 있는지 봅니다 (Python)
#   setting_propose : 처리안을 만듭니다. 계산만 하고 저장하지 않습니다
#   setting_execute : 승인되면 데이터를 바꿉니다 (저장은 common_save)
#   setting_fail    : 진행할 수 없는 사유를 알려줍니다
#   (인증·승인·응답 해석·거절·기록·저장·안내는 공통 노드를 씁니다)

from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import data_store
import functions
import logger
from agents.setting.prompts import extract_prompt
from model import llm
from state import BankState


class SettingInfo(BaseModel):
    action: Optional[Literal["변경", "등록", "삭제", "조회"]] = Field(default=None, description="할 일")
    account_name: Optional[str] = Field(default=None, description="변경·삭제할 계좌의 지금 이름")
    field: Optional[Literal["별명", "용도"]] = Field(default=None, description="변경할 항목")
    new_value: Optional[str] = Field(default=None, description="변경할 새 값")
    bank_name: Optional[str] = Field(default=None, description="등록할 계좌의 은행 이름")
    account_number: Optional[str] = Field(default=None, description="등록할 계좌번호")
    holder_name: Optional[str] = Field(default=None, description="등록할 계좌의 예금주 이름")
    nickname: Optional[str] = Field(default=None, description="등록할 계좌에 붙일 별명")


llm_with_setting_output = llm.with_structured_output(SettingInfo)


def setting_extract_node(state: BankState):
    # 승인 전 수정("아니 휴식비로")도 여기로 돌아와 말한 값만 덮어씁니다.
    log = logger.get_logger()
    with log.node("setting_extract"):
        prompt = extract_prompt.format(
            action=state.get("setting_action") or "모름",
            account_name=state.get("target_name") or "모름",
            field=state.get("setting_field") or "모름",
            new_value=state.get("new_value") or "모름",
            reg_info=state.get("reg_info") or "없음",
        )
        r = llm_with_setting_output.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=state["query"]),
        ])
        log.detail("추출  할 일=%s  계좌=%s  항목=%s  새 값=%s  등록=%s %s %s %s" % (
            r.action, r.account_name, r.field, r.new_value, r.bank_name, r.account_number, r.holder_name, r.nickname))

        update = {}
        if r.action and not state.get("setting_action"):
            update["setting_action"] = r.action
        if r.account_name and not state.get("target_account"):
            update["target_name"] = r.account_name
        if r.field:
            update["setting_field"] = r.field
        if r.new_value:
            update["new_value"] = r.new_value

        # 등록할 계좌 정보는 한 묶음(reg_info)으로 둡니다. 말한 칸만 덮어씁니다.
        reg = dict(state.get("reg_info") or {})
        for key in ["bank_name", "account_number", "holder_name", "nickname"]:
            if getattr(r, key):
                reg[key] = getattr(r, key)
        if reg:
            reg.setdefault("nickname", reg.get("holder_name", ""))     # 별명을 안 말하면 예금주 이름
            update["reg_info"] = reg

    return update


def setting_list_node(state: BankState):
    with logger.get_logger().node("setting_list"):
        registered = functions.get_registered(functions.CURRENT_USER)
        if not registered:
            return {"answer": "등록한 계좌가 없습니다."}
        lines = ["등록 계좌 %d개입니다." % len(registered)]
        for r in registered:
            lines.append("- %s : %s %s (예금주 %s)" % (r["nickname"], r["bank_name"], r["account_number"], r["holder_name"]))
    return {"answer": "\n".join(lines)}


def setting_check_node(state: BankState):
    log = logger.get_logger()
    with log.node("setting_check"):
        action = state.get("setting_action")

        if action == "등록":
            error = functions.check_register(functions.CURRENT_USER, state.get("reg_info") or {})
            return {"error": error} if error else {}

        if not state.get("target_name"):
            return {"error": "어느 계좌인지 말해 주세요. (예: 여행 자금 계좌 이름을 휴가비로 바꿔줘 / 친구 민수 계좌 삭제해줘)"}

        if action == "삭제":
            found = functions.find_registered(functions.CURRENT_USER, state["target_name"])
            log.resolve(state["target_name"], len(found), found[0]["registered_id"] if found else None)
            if len(found) != 1:
                return {"error": "'%s' 에 맞는 등록 계좌를 하나로 정할 수 없습니다. 정확한 이름으로 다시 요청해 주세요." % state["target_name"]}
            return {"target_account": found[0]["registered_id"]}

        # 변경 : 내 계좌의 별명·용도
        if not state.get("setting_field") or not state.get("new_value"):
            return {"error": "무엇을 무엇으로 바꿀지 말해 주세요. (예: 여행 자금 계좌 이름을 휴가비로 바꿔줘)"}
        update = {}
        account_id = state.get("target_account")
        if not account_id:
            found = functions.find_accounts(functions.CURRENT_USER, state["target_name"])
            log.resolve(state["target_name"], len(found), found[0]["account_id"] if found else None)
            if len(found) != 1:
                return {"error": "'%s' 계좌를 하나로 정할 수 없습니다. 정확한 이름으로 다시 요청해 주세요." % state["target_name"]}
            account_id = found[0]["account_id"]
            update["target_account"] = account_id
        error = functions.check_setting(functions.CURRENT_USER, account_id, state["setting_field"], state["new_value"])
        if error:
            update["error"] = error

    return update


def setting_propose_node(state: BankState):
    with logger.get_logger().node("setting_propose"):
        action = state["setting_action"]

        if action == "등록":
            reg = state["reg_info"]
            proposal = {"task": "계좌 등록", "rows": [
                ["은행", reg["bank_name"]],
                ["계좌번호", reg["account_number"]],
                ["예금주", reg["holder_name"]],
                ["별명", reg["nickname"]],
            ]}
        elif action == "삭제":
            r = next(r for r in functions.get_registered(functions.CURRENT_USER)
                     if r["registered_id"] == state["target_account"])
            proposal = {"task": "등록 계좌 삭제", "rows": [
                ["별명", r["nickname"]],
                ["계좌", "%s %s (예금주 %s)" % (r["bank_name"], r["account_number"], r["holder_name"])],
            ]}
        else:
            account = functions.get_account(functions.CURRENT_USER, state["target_account"])
            field = state["setting_field"]
            proposal = {"task": "계좌 %s 변경" % field, "rows": [
                ["계좌", "%s (%s)" % (account["nickname"], account["account_number"])],
                ["지금 " + field, account[functions.SETTING_FIELDS[field]]],
                ["새 " + field, state["new_value"].strip()],
            ]}
    return {"proposal": proposal, "approval": "대기"}


def setting_execute_node(state: BankState):
    # 승인된 뒤에만 옵니다. 바꾼 데이터를 new_data 로 넘기고, 저장은 common_save 가 합니다.
    with logger.get_logger().node("setting_execute"):
        data = data_store.load()
        action = state["setting_action"]

        if action == "등록":
            functions.register_account(data, functions.CURRENT_USER, state["reg_info"])
            answer = "계좌를 등록했습니다. (%s)" % state["reg_info"]["nickname"]
        elif action == "삭제":
            functions.delete_registered(data, state["target_account"])
            answer = "등록 계좌를 삭제했습니다. (%s)" % state["proposal"]["rows"][0][1]
        else:
            old = functions.get_account(functions.CURRENT_USER, state["target_account"])
            field = state["setting_field"]
            functions.change_setting(data, state["target_account"], field, state["new_value"])
            answer = "계좌 %s 변경 완료 : %s → %s" % (
                field, old[functions.SETTING_FIELDS[field]], state["new_value"].strip())

    return {"new_data": data, "answer": answer, "result": "완료"}


def setting_fail_node(state: BankState):
    with logger.get_logger().node("setting_fail"):
        answer = state["error"]
    return {"answer": answer}


# ---------------------------------------------------------------- 분기
def route_after_extract(state: BankState):
    # 조회는 읽기만 하므로 인증·승인 없이 바로 보여줍니다.
    if state.get("setting_action") == "조회":
        return "setting_list"
    return "setting_check"


def route_after_check(state: BankState):
    if state.get("error"):
        return "setting_fail"
    return "common_authenticate"


def route_after_authenticate(state: BankState):
    if state.get("error"):
        return "setting_fail"
    if state.get("authenticated"):
        return "setting_propose"
    return "common_authenticate"        # 틀렸으면 다시 묻습니다


def route_after_interpret(state: BankState):
    decision = state["approval"]
    if decision == "승인":
        return "setting_execute"
    if decision in ("거절", "취소"):
        return "common_reject"
    if decision == "수정":
        return "setting_extract"        # 바꾼 말로 다시 뽑고 처리안을 새로 만듭니다
    return "common_approve"             # 모름 : 다시 묻습니다
