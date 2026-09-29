# 계좌 설정 에이전트(3단)의 노드 함수입니다.
# 계좌 별명·용도 변경, 등록 계좌(상대 계좌 주소록) 등록·조회·삭제, 예약 이체 조회·취소,
# 내 계좌 정지·정지 해제·해지, 은행별 계좌번호 규칙 안내를 맡습니다.
#
#   setting_extract : 사용자 말에서 할 일(변경/등록/삭제/조회/예약조회/예약취소)과 필요한 값을 뽑습니다 (LLM)
#   setting_list    : 등록 계좌나 예약 이체 목록을 보여줍니다. 읽기만 하므로 승인 없이 끝납니다
#   setting_check   : 대상을 ID 로 바꾸고, 할 수 있는지 봅니다 (Python)
#   setting_confirm : 이름에 맞는 것이 여러 개면 번호를 고르게 합니다 (interrupt)
#   setting_ask     : 빠진 값(계좌, 새 값, 등록 정보)을 묻습니다 (interrupt)
#   setting_propose : 처리안을 만듭니다. 계산만 하고 저장하지 않습니다
#   setting_execute : 승인되면 데이터를 바꿉니다 (저장은 common_save)
#   setting_fail    : 진행할 수 없는 사유를 알려줍니다
#   (인증·승인·응답 해석·거절·기록·저장·안내는 공통 노드를 씁니다)

from datetime import date
from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

import data_store
import functions
import logger
from agents.account.setting.prompts import extract_prompt
from agents.common.nodes import is_cancel, pick_text, pick_warning, picked, question
from model import llm
from state import BankState


class SettingInfo(BaseModel):
    action: Optional[Literal["변경", "등록", "삭제", "조회", "예약조회", "예약취소", "정지", "정지 해제", "해지", "규칙", "개설"]] = Field(
        default=None, description="할 일")
    account_name: Optional[str] = Field(default=None, description="변경·삭제할 계좌의 지금 이름, 또는 취소할 예약의 단서")
    field: Optional[Literal["별명", "용도"]] = Field(default=None, description="변경할 항목")
    new_value: Optional[str] = Field(default=None, description="변경할 새 값")
    bank_name: Optional[str] = Field(default=None, description="등록할 계좌의 은행 이름")
    account_number: Optional[str] = Field(default=None, description="등록할 계좌번호")
    holder_name: Optional[str] = Field(default=None, description="등록할 계좌의 예금주 이름")
    nickname: Optional[str] = Field(default=None, description="등록할 계좌에 붙일 별명")
    to_account_name: Optional[str] = Field(default=None, description="해지할 때 남은 돈을 받을 계좌 이름")
    other_request: bool = Field(default=False, description="방금 한 질문의 답이 아니라 계좌 설정과 관계없는 다른 요청이면 true")


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
            question=state.get("question") or "없음",
            today=date.today(),
        )
        r = llm_with_setting_output.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=state["query"]),
        ])
        log.detail("추출  할 일=%s  계좌=%s  항목=%s  새 값=%s  등록=%s %s %s %s" % (
            r.action, r.account_name, r.field, r.new_value, r.bank_name, r.account_number, r.holder_name, r.nickname))

        # 진행 중에 은행별 계좌번호 규칙을 물으면 멈추지 않고, 규칙을 보여준 뒤 같은 질문을 다시 합니다.
        if state.get("setting_action") and r.action == "규칙":
            return {"notice": functions.account_rules_text()}
        # 질문(빠진 값)에 답하는 대신 다른 요청을 쳤으면 멈춥니다. (이체와 같은 방식)
        if state.get("question") and r.other_request:
            return {"error": "진행 중이던 계좌 설정을 멈췄습니다. 새 요청을 다시 입력해 주세요."}

        update = {}
        if r.action and not state.get("setting_action"):
            update["setting_action"] = r.action
        if r.account_name and not state.get("target_account"):
            update["target_name"] = r.account_name
        if r.field:
            update["setting_field"] = r.field
        if r.new_value:
            update["new_value"] = r.new_value
        if r.to_account_name:       # 해지할 때 남은 돈을 받을 계좌. 다시 말하면 새로 찾습니다
            update["to_name"] = r.to_account_name
            update["to_account"] = None

        # 등록할 계좌 정보는 한 묶음(reg_info)으로 둡니다. 말한 칸만 덮어씁니다.
        reg = dict(state.get("reg_info") or {})
        for key in ["bank_name", "account_number", "holder_name", "nickname"]:
            if getattr(r, key):
                reg[key] = getattr(r, key)
        if reg:
            # 별명을 안 말하면 예금주 이름. 예금주를 나중에 답할 수도 있으므로 비어 있으면 매번 다시 채웁니다.
            if not reg.get("nickname"):
                reg["nickname"] = reg.get("holder_name", "")
            update["reg_info"] = reg

    return update


def schedule_text(data, s):
    # 예약 한 건(s)을 한 줄로 씁니다. 예) sch-001  09월 27일 09:00  생활비 → 저축  100,000원  [예약]
    # 계좌 이름은 부르는 쪽이 한 번 읽어 둔 data 에서 찾습니다. (건마다 파일을 다시 읽지 않게)
    return "%s  %s  %s → %s  %s원  [%s]" % (
        s["schedule_id"], functions.when_text(s["scheduled_at"]),
        functions.target_name(data, s["from_account"]), functions.target_name(data, s["to_account"]),
        format(s["amount"], ","), s["status"])


def schedule_list_text(owner_id):
    data = data_store.load()
    schedules = [s for s in data["scheduled_transfers"] if s["owner_id"] == owner_id]
    if not schedules:
        return "예약 이체가 없습니다."
    lines = ["예약 이체 %d건입니다." % len(schedules)]
    lines += ["- " + schedule_text(data, s) for s in schedules]
    return "\n".join(lines)


# 에이전트에서는 상대 계좌만 등록합니다. 내 계좌 만들기는 계좌 페이지(웹 버튼)에서 합니다.
OWN_ACCOUNT_GUIDE = "상대 계좌만 등록할 수 있습니다. 본인 계좌의 경우 계좌 페이지에서 진행하세요."


def setting_list_node(state: BankState):
    with logger.get_logger().node("setting_list"):
        if state.get("setting_action") == "규칙":
            return {"answer": functions.account_rules_text()}
        if state.get("setting_action") == "개설":
            # 내 계좌 새로 만들기는 계좌 비밀번호를 정해야 해서 웹 화면에서만 합니다.
            return {"answer": OWN_ACCOUNT_GUIDE}
        if state.get("setting_action") == "예약조회":
            return {"answer": schedule_list_text(state["owner_id"])}
        registered = functions.get_registered(state["owner_id"])
        if not registered:
            return {"answer": "등록한 계좌가 없습니다."}
        lines = ["등록 계좌 %d개입니다." % len(registered)]
        for r in registered:
            lines.append("- %s : %s %s (예금주 %s)" % (r["nickname"], r["bank_name"], r["account_number"], r["holder_name"]))
    return {"answer": "\n".join(lines)}


def setting_check_node(state: BankState):
    # 대상을 하나로 정하고 빠진 값이 있는지 봅니다. 모자라면 끝내지 않고 다음 중 하나를 State 에 남깁니다.
    #   candidates : 이름에 맞는 것이 여러 개 → setting_confirm 이 번호로 고르게 합니다
    #   question   : 빠진 값이 있음          → setting_ask 가 그 값만 묻습니다
    # 한 번 정한 대상(target_account)은 다시 찾지 않습니다. 되물은 뒤 여기로 돌아오기 때문입니다.
    log = logger.get_logger()
    with log.node("setting_check"):
        action = state.get("setting_action")
        target_id = state.get("target_account")
        update = {"candidates": None, "question": None, "confirm_for": None, "notice": None}
        notice = state.get("notice")        # 진행 중에 물어본 규칙 등 : 이번 질문 위에 한 번 붙입니다

        # "비상금 계좌 삭제해줘" 처럼 내 계좌를 지우려고 하면(등록 계좌가 아니면) 해지로 바꿉니다.
        if (action == "삭제" and not target_id and state.get("target_name")
                and not functions.find_registered(state["owner_id"], state["target_name"])
                and functions.find_accounts(state["owner_id"], state["target_name"])):
            action = update["setting_action"] = "해지"

        if action == "등록":
            reg = dict(state.get("reg_info") or {})
            # 은행 말고 빠진 칸은 글로 묻고, 은행은 목록에서 고르게 합니다 (common_pick_bank).
            # 묻는 말에 말하는 형식과, 은행을 알면 그 은행의 계좌번호 자릿수도 같이 알려줍니다.
            missing = [label for label in functions.register_missing(reg) if label != "은행"]
            if missing:
                bank = functions.match_bank(reg.get("bank_name"))
                lines = [notice] if notice else []
                lines.append("[등록] 알려주세요 : %s" % ", ".join(missing))
                lines.append(OWN_ACCOUNT_GUIDE)
                lines.append("말하는 형식 : [은행] [계좌번호] [예금주 이름]  (예: 신한은행 110-123-456789 이영희)")
                if bank:
                    lines.append("%s 을(를) 골랐어요. %s" % (bank, functions.account_number_rule(bank)))
                else:
                    lines.append("계좌번호는 은행마다 자릿수가 달라요. ('계좌번호 규칙 보여줘' 라고 하면 알려드려요)")
                update["question"] = "\n".join(lines)
                return update
            bank = functions.match_bank(reg.get("bank_name"))
            if not bank:
                update["confirm_for"] = "bank"
                return update
            reg["bank_name"] = bank      # "국민" → KB국민은행 처럼 목록 이름으로 맞춥니다
            # 계좌번호는 그 은행 모양으로 맞춥니다. 모양이 틀리면 규칙을 알려주고 계좌번호만 다시 묻습니다.
            number = functions.normalize_account_number(bank, reg["account_number"])
            if not number:
                update["question"] = ("%s\n" % notice if notice else "") + \
                    "[등록] %s 계좌번호를 다시 알려주세요." % functions.account_number_rule(bank)
                reg["account_number"] = None
                update["reg_info"] = reg
                return update
            reg["account_number"] = number
            update["reg_info"] = reg
            error = functions.check_register(state["owner_id"], reg)
            if error:
                update["error"] = error
            return update

        if action in ("정지", "정지 해제", "해지"):
            return account_state_check(state, action, target_id, update)

        if action == "예약취소":
            if not target_id:
                found = functions.find_schedules(state["owner_id"], state.get("target_name"))
                log.resolve(state.get("target_name") or "(말 안 함)", len(found), found[0]["schedule_id"] if found else None)
                if not found:
                    update["error"] = "취소할 예약을 찾을 수 없습니다.\n" + schedule_list_text(state["owner_id"])
                    return update
                if len(found) > 1:
                    data = data_store.load()
                    update["candidates"] = [{"id": s["schedule_id"], "text": schedule_text(data, s)} for s in found]
                    return update
                update["target_account"] = found[0]["schedule_id"]
            return update

        if not state.get("target_name") and not target_id:
            if action == "삭제":
                update["question"] = "[계좌] 어느 등록 계좌를 지울까요? (별명이나 예금주 이름)"
            else:
                update["question"] = "[계좌] 어느 계좌를 바꿀까요?"
            return update

        if action == "삭제":
            if not target_id:
                found = functions.find_registered(state["owner_id"], state["target_name"])
                log.resolve(state["target_name"], len(found), found[0]["registered_id"] if found else None)
                if not found:
                    update["error"] = "'%s' 등록 계좌를 찾을 수 없습니다." % state["target_name"]
                    return update
                if len(found) > 1:
                    update["candidates"] = [{"id": r["registered_id"], "text": "%s (%s %s, 예금주 %s)" % (
                        r["nickname"], r["bank_name"], r["account_number"], r["holder_name"])} for r in found]
                    return update
                update["target_account"] = found[0]["registered_id"]
            return update

        # 변경 : 내 계좌의 별명·용도. 계좌를 먼저 정하고, 그다음 무엇을 무엇으로 바꿀지 봅니다.
        if not target_id:
            found = functions.find_accounts(state["owner_id"], state["target_name"])
            log.resolve(state["target_name"], len(found), found[0]["account_id"] if found else None)
            if not found:
                update["error"] = "'%s' 계좌를 찾을 수 없습니다." % state["target_name"]
                return update
            if len(found) > 1:
                update["candidates"] = [{"id": a["account_id"], "text": "%s (%s)" % (a["nickname"], a["account_number"])}
                                        for a in found]
                return update
            target_id = found[0]["account_id"]
            update["target_account"] = target_id
        field = state.get("setting_field")
        if not field:
            update["question"] = "[항목] 별명과 용도 중 무엇을 바꿀까요?"
            return update
        if not state.get("new_value"):
            account = functions.get_account(state["owner_id"], target_id)
            update["question"] = "[새 값] 무엇으로 바꿀까요? (지금 %s : %s)" % (field, account[functions.SETTING_FIELDS[field]])
            return update
        error = functions.check_setting(state["owner_id"], target_id, field, state["new_value"])
        if error:
            update["error"] = error

    return update


def account_state_check(state, action, target_id, update):
    # 내 계좌 정지 / 정지 해제 / 해지 : 계좌를 하나로 정하고 할 수 있는지 봅니다.
    # 해지할 때 잔액이 남아 있으면 받을 계좌(to_name → to_account)를 묻고 찾습니다. 여러 개면 번호로 고르게 합니다.
    log = logger.get_logger()
    owner = state["owner_id"]
    if not target_id:
        if not state.get("target_name"):
            update["question"] = "[계좌] 어느 계좌를 %s할까요?" % action
            return update
        found = functions.find_accounts(owner, state["target_name"])
        log.resolve(state["target_name"], len(found), found[0]["account_id"] if found else None)
        if not found:
            update["error"] = "'%s' 계좌를 찾을 수 없습니다." % state["target_name"]
            return update
        if len(found) > 1:
            update["candidates"] = [{"id": a["account_id"], "text": "%s (%s %s)" % (a["nickname"], a["bank_name"], a["account_number"])}
                                    for a in found]
            return update
        target_id = update["target_account"] = found[0]["account_id"]
    account = functions.get_account(owner, target_id)

    if action != "해지":
        error = functions.check_account_status(account, action)
        if error:
            update["error"] = error
        return update

    data = data_store.load()
    to_id = state.get("to_account")
    if account["balance"] > 0 and not to_id:
        if not state.get("to_name"):
            update["question"] = "[받을 계좌] 남은 돈 %s원을 받을 계좌를 알려주세요. (내 다른 계좌나 등록 계좌)" % format(account["balance"], ",")
            return update
        found = [t for t in functions.find_targets(owner, state["to_name"]) if t["account_id"] != target_id]
        log.resolve(state["to_name"], len(found), found[0]["account_id"] if found else None)
        if not found:
            update["error"] = "받을 계좌 '%s' 를 찾을 수 없습니다." % state["to_name"]
            return update
        if len(found) > 1:
            update["candidates"] = [{"id": t["account_id"], "text": "%s (%s)" % (t["nickname"], t["account_number"])} for t in found]
            update["confirm_for"] = "to"       # 고른 번호를 받을 계좌(to_account)에 넣게 합니다
            return update
        to_id = update["to_account"] = found[0]["account_id"]
    error = functions.check_close(data, owner, target_id, to_id)
    if error:
        update["error"] = error
    return update


# 번호 고르기에서 번호가 아닌 답을 받았을 때 보여줄 업무 이름입니다.
SETTING_TASKS = {"변경": "계좌 별명·용도 변경", "삭제": "등록 계좌 삭제", "예약취소": "예약 이체 취소",
                 "정지": "계좌 정지", "정지 해제": "계좌 정지 해제", "해지": "계좌 해지"}


def setting_confirm_node(state: BankState):
    # 이름에 맞는 계좌·예약이 여러 개면 번호로 고르게 합니다. 고른 ID 를 target_account 에 넣고 check 로 돌아갑니다.
    # 후보는 check 가 {id, text} 로 만들어 둡니다 (내 계좌 / 등록 계좌 / 예약 모두 같은 모양).
    candidates = state["candidates"]
    lines = ["맞는 것이 %d개입니다. 번호를 골라 주세요." % len(candidates)]
    lines += ["%d. %s" % (number, c["text"]) for number, c in enumerate(candidates, start=1)]

    with logger.get_logger().node("setting_confirm"):
        logger.get_logger().interrupt_pause("사용자 확인 (후보 %d개)" % len(candidates))

    answer = interrupt(question(pick_text(state, lines))).strip()

    if is_cancel(answer):
        return {"error": "요청을 취소했습니다."}
    choice = picked(answer, candidates)
    if choice and state.get("confirm_for") == "to":      # 해지할 때 받을 계좌를 고른 경우
        return {"to_account": choice["id"], "candidates": None, "confirm_for": None, "pick_warning": None}
    if choice:
        return {"target_account": choice["id"], "candidates": None, "pick_warning": None}
    # 번호가 아니면 지금 하는 업무를 알려주고 check 로 돌아가 다시 고르게 합니다.
    return pick_warning(SETTING_TASKS.get(state.get("setting_action"), "계좌 설정"))


def setting_ask_node(state: BankState):
    # check 가 남긴 질문(빠진 값)을 묻습니다. 답은 새 입력으로 삼아 extract 로 돌아가 빈 칸만 채웁니다.
    with logger.get_logger().node("setting_ask"):
        logger.get_logger().interrupt_pause("질문: " + state["question"])

    answer = interrupt(question(state["question"] + "\n(그만두려면 '취소')")).strip()

    if is_cancel(answer):
        return {"error": "요청을 취소했습니다."}
    return {"query": answer}


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
        elif action == "예약취소":
            data = data_store.load()
            s = next(s for s in data["scheduled_transfers"] if s["schedule_id"] == state["target_account"])
            proposal = {"task": "예약 이체 취소", "rows": [["예약", schedule_text(data, s)]]}
        elif action in ("정지", "정지 해제"):
            account = functions.get_account(state["owner_id"], state["target_account"])
            rows = [
                ["계좌", "%s (%s %s)" % (account["nickname"], account["bank_name"], account["account_number"])],
                ["지금 상태", functions.ACCOUNT_STATUS[functions.account_status(account)]],
                ["바뀔 상태", functions.ACCOUNT_STATUS[functions.ACCOUNT_ACTIONS[action]]],
            ]
            if action == "정지":
                rows.append(["주의", "정지를 풀기 전까지 이 계좌에서 돈이 나가지 않습니다 (입금은 받습니다)"])
            proposal = {"task": "계좌 " + action, "rows": rows}
        elif action == "해지":
            data = data_store.load()
            account = functions.get_account(state["owner_id"], state["target_account"])
            rows = [["계좌", "%s (%s %s)" % (account["nickname"], account["bank_name"], account["account_number"])],
                    ["잔액", format(account["balance"], ",") + "원"]]
            if account["balance"] > 0:
                rows.append(["남은 돈 보낼 곳", functions.get_target(data, state["to_account"])["text"]])
            rows.append(["주의", "해지하면 되돌릴 수 없습니다"])
            proposal = {"task": "계좌 해지", "rows": rows}
        elif action == "삭제":
            r = next(r for r in functions.get_registered(state["owner_id"])
                     if r["registered_id"] == state["target_account"])
            proposal = {"task": "등록 계좌 삭제", "rows": [
                ["별명", r["nickname"]],
                ["계좌", "%s %s (예금주 %s)" % (r["bank_name"], r["account_number"], r["holder_name"])],
            ]}
        else:
            account = functions.get_account(state["owner_id"], state["target_account"])
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
            functions.register_account(data, state["owner_id"], state["reg_info"])
            answer = "계좌를 등록했습니다. (%s)" % state["reg_info"]["nickname"]
        elif action == "예약취소":
            functions.cancel_schedule(data, state["target_account"])
            answer = "예약 이체를 취소했습니다. (%s)" % state["target_account"]
        elif action in ("정지", "정지 해제"):
            account = functions.get_account(state["owner_id"], state["target_account"])
            functions.change_account_status(data, state["target_account"], action)
            answer = "계좌 %s 완료 : %s  %s → %s" % (action, account["nickname"], functions.ACCOUNT_STATUS[functions.account_status(account)],
                                                functions.ACCOUNT_STATUS[functions.ACCOUNT_ACTIONS[action]])
        elif action == "해지":
            account = functions.get_account(state["owner_id"], state["target_account"])
            try:
                moved = functions.close_account(data, state["target_account"], state.get("to_account"))
            except ValueError as e:         # 실행 직전에 이체가 막힌 경우 : 바꾸지 않고 실패로 남깁니다
                return {"answer": str(e), "result": "실패", "new_data": data_store.load()}
            answer = "계좌를 해지했습니다. (%s  %s %s)" % (account["nickname"], account["bank_name"], account["account_number"])
            if moved:
                answer += "\n남은 돈 %s원은 %s(으)로 보냈습니다." % (format(moved, ","), functions.target_name(data, state["to_account"]))
        elif action == "삭제":
            functions.delete_registered(data, state["target_account"])
            answer = "등록 계좌를 삭제했습니다. (%s)" % state["proposal"]["rows"][0][1]
        else:
            old = functions.get_account(state["owner_id"], state["target_account"])
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
    if state.get("setting_action") in ("조회", "예약조회", "규칙", "개설"):
        return "setting_list"
    return "setting_check"


def route_after_check(state: BankState):
    if state.get("error"):
        return "setting_fail"
    if state.get("candidates"):
        return "setting_confirm"
    if state.get("question"):
        return "setting_ask"
    if state.get("confirm_for") == "bank":
        return "common_pick_bank"
    return "common_authenticate"


def route_after_confirm(state: BankState):
    if state.get("error"):
        return "setting_fail"
    return "setting_check"


def route_after_ask(state: BankState):
    if state.get("error"):
        return "setting_fail"
    return "setting_extract"


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
    if decision in ("거절", "취소", "다른요청"):
        return "common_reject"
    if decision == "수정":
        return "setting_extract"        # 바꾼 말로 다시 뽑고 처리안을 새로 만듭니다
    return "common_approve"             # 모름 : 다시 묻습니다
