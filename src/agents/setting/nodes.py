# 계좌 설정 에이전트(3단)의 노드 함수입니다. 계좌 별명·용도를 바꿉니다.
#
#   setting_extract : 사용자 말에서 계좌, 항목(별명/용도), 새 값을 뽑습니다 (LLM)
#   setting_check   : 계좌를 ID 로 바꾸고, 바꿀 수 있는지 봅니다 (Python)
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
    account_name: Optional[str] = Field(default=None, description="바꿀 계좌의 지금 이름")
    field: Optional[Literal["별명", "용도"]] = Field(default=None, description="바꿀 항목")
    new_value: Optional[str] = Field(default=None, description="새 값")


llm_with_setting_output = llm.with_structured_output(SettingInfo)


def setting_extract_node(state: BankState):
    # 승인 전 수정("아니 휴식비로")도 여기로 돌아와 새 값만 덮어씁니다.
    log = logger.get_logger()
    with log.node("setting_extract"):
        prompt = extract_prompt.format(
            account_name=state.get("target_name") or "모름",
            field=state.get("setting_field") or "모름",
            new_value=state.get("new_value") or "모름",
        )
        result = llm_with_setting_output.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=state["query"]),
        ])
        log.detail("추출  계좌=%s  항목=%s  새 값=%s" % (result.account_name, result.field, result.new_value))

        update = {}
        if result.account_name and not state.get("target_account"):
            update["target_name"] = result.account_name
        if result.field:
            update["setting_field"] = result.field
        if result.new_value:
            update["new_value"] = result.new_value

    return update


def setting_check_node(state: BankState):
    log = logger.get_logger()
    with log.node("setting_check"):
        if not state.get("target_name") or not state.get("setting_field") or not state.get("new_value"):
            return {"error": "어느 계좌의 별명(또는 용도)을 무엇으로 바꿀지 말해 주세요. (예: 여행 자금 계좌 이름을 휴가비로 바꿔줘)"}

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
        account = functions.get_account(functions.CURRENT_USER, state["target_account"])
        field = state["setting_field"]
        proposal = {
            "task": "계좌 %s 변경" % field,
            "rows": [
                ["계좌", "%s (%s)" % (account["nickname"], account["account_number"])],
                ["지금 " + field, account[functions.SETTING_FIELDS[field]]],
                ["새 " + field, state["new_value"].strip()],
            ],
        }
    return {"proposal": proposal, "approval": "대기"}


def setting_execute_node(state: BankState):
    # 승인된 뒤에만 옵니다. 바꾼 데이터를 new_data 로 넘기고, 저장은 common_save 가 합니다.
    with logger.get_logger().node("setting_execute"):
        data = data_store.load()
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
