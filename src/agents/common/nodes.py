# 여러 업무가 같이 쓰는 공통 노드입니다. 기획서 6장을 따릅니다.
#
#   common_pending_check : [분기 0] 멈춰 있는 업무가 있는지 봅니다 (main.py 에서 부릅니다)
#   common_authenticate  : 본인 확인을 받습니다. 세션 동안 한 번만 (interrupt)
#   common_approve       : 처리안을 보여주고 승인을 기다립니다 (interrupt)
#   common_interpret     : 승인 질문에 대한 답을 승인 / 거절 / 취소 / 수정 / 모름 으로 가릅니다 (LLM)
#   common_reject        : 거절·취소를 안내합니다
#   common_log_request   : 처리 기록을 남깁니다
#   common_save          : 파일에 저장합니다 (실패하면 세 번까지)
#   common_report        : 저장이 성공했을 때만 결과를 안내합니다
#
# 처리안(proposal)은 각 업무의 propose 노드가 만듭니다. 모양은 다음과 같습니다.
#   {"task": "이체", "rows": [["출금", "생활비"], ["금액", "100,000원"], ...], ...}
# 공통 노드는 task 와 rows 만 읽습니다. 나머지 칸은 업무마다 자유롭게 둡니다.

from datetime import datetime
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

import data_store
import functions
import logger
from agents.common.prompts import interpret_prompt
from model import llm
from state import BankState

# 그래프가 멈출 때 interrupt 에 넘기는 값입니다.
# kind 를 보고 main.py 가 승인 대기인지, 부족 정보 질문인지 구분합니다.
APPROVAL = "approval"
QUESTION = "question"
SECRET = "secret"           # 비밀번호처럼 로그에 남기면 안 되는 답을 묻는 질문


def question(text):
    return {"kind": QUESTION, "text": text}


def secret(text):
    return {"kind": SECRET, "text": text}


def approval(text):
    return {"kind": APPROVAL, "text": text}


# ---------------------------------------------------------------- 분기 0
def common_pending_check(graph, config):
    # 멈춰 있는 업무가 있으면 그 종류(approval / question)를, 없으면 None 을 돌려줍니다.
    # 이 판정이 없으면 승인 대기 중에 친 "응, 진행해" 가 새 요청으로 분류됩니다.
    snapshot = graph.get_state(config)
    if not snapshot.next:
        return None
    for item in snapshot.interrupts:
        return item.value["kind"]
    return QUESTION


# ---------------------------------------------------------------- 인증
AUTH_TRIES = 3


def common_authenticate_node(state: BankState):
    # 처리안을 보여주기 전에 본인 확인을 받습니다. 승인 뒤에 두면 틀렸을 때 처리안을 다시 만들어야 합니다.
    # 한 번 맞히면 세션(프로그램을 끌 때까지) 동안 다시 묻지 않습니다.
    log = logger.get_logger()
    if state.get("authenticated"):
        with log.node("common_authenticate"):
            log.detail("세션 인증 있음 → 건너뜀")
        return {}

    tries = state.get("auth_tries") or 0
    lines = ["[본인 확인] 계좌 비밀번호, PIN, 휴대전화번호, 주민번호 뒷자리 중 하나를 입력해 주세요."]
    if tries:
        lines.insert(0, "일치하지 않습니다. (%d/%d)" % (tries, AUTH_TRIES))

    with log.node("common_authenticate"):
        log.interrupt_pause("본인 확인")

    answer = interrupt(secret("\n".join(lines))).strip()

    if answer == "취소":
        return {"error": "본인 확인을 취소했습니다."}
    if functions.authenticate(functions.CURRENT_USER, answer):
        log.note("본인 확인 성공")
        return {"authenticated": True, "auth_tries": 0}
    tries += 1
    log.note("본인 확인 실패 %d/%d" % (tries, AUTH_TRIES))
    if tries >= AUTH_TRIES:
        return {"error": "본인 확인에 %d번 실패했습니다. 처음부터 다시 요청해 주세요." % AUTH_TRIES, "auth_tries": 0}
    return {"auth_tries": tries}


# ---------------------------------------------------------------- 승인
def format_proposal(proposal):
    # 한글은 두 칸을 차지하므로 글자 수가 아니라 화면 폭으로 맞춥니다.
    width = max(logger._width(label) for label, _ in proposal["rows"])
    lines = ["  [%s 처리안]" % proposal["task"]]
    for label, value in proposal["rows"]:
        lines.append("  %s : %s" % (logger._pad(label, width), value))
    return "\n".join(lines)


def common_approve_node(state: BankState):
    # interrupt 한 줄만 둡니다. 재개하면 이 노드가 처음부터 다시 돌기 때문에
    # 여기서 저장하거나 값을 바꾸면 그 일이 두 번 일어납니다.
    proposal = state["proposal"]

    lines = ["=" * 40, format_proposal(proposal), "-" * 40]
    if state.get("approval") == "모름":
        lines.append("  답을 알아듣지 못했습니다.")
    lines.append("  진행할까요? (승인 / 거절 / 바꿀 내용)")
    lines.append("=" * 40)

    with logger.get_logger().node("common_approve"):
        logger.get_logger().interrupt_pause("승인 대기 (%s)" % proposal["task"])

    reply = interrupt(approval("\n".join(lines))).strip()
    return {"query": reply}


# ---------------------------------------------------------------- 응답 해석
class ApprovalDecision(BaseModel):
    decision: Literal["승인", "거절", "취소", "수정", "모름"] = Field(description="사용자 답의 종류")
    reason: str = Field(description="그렇게 고른 이유")


llm_with_approval_output = llm.with_structured_output(ApprovalDecision)


def common_interpret_node(state: BankState):
    log = logger.get_logger()
    with log.node("common_interpret"):
        result = llm_with_approval_output.invoke([
            SystemMessage(content=interpret_prompt.format(proposal=format_proposal(state["proposal"]))),
            HumanMessage(content=state["query"]),
        ])
        log.detail("응답 해석 = %s   (근거: %s)" % (result.decision, result.reason))

    return {"approval": result.decision}


def common_reject_node(state: BankState):
    with logger.get_logger().node("common_reject"):
        answer = "%s 요청을 진행하지 않았습니다. 바뀐 것은 없습니다." % state["proposal"]["task"]
    return {"answer": answer, "result": "거절"}


# ---------------------------------------------------------------- 마무리
# 업무 노드가 answer 와 result 를 정해 두면, 여기서 기록 → 저장 → 안내 순서로 끝냅니다.
#   log_request : 처리 기록을 저장할 데이터(new_data)에 덧붙입니다
#   save        : new_data 를 파일에 씁니다. 실패하면 세 번까지 다시 해 봅니다
#   report      : 저장이 성공했을 때만 answer 를 그대로 보여줍니다
# 업무 변경과 처리 기록을 한 번에 저장하므로, 저장이 실패하면 둘 다 반영되지 않습니다.

SAVE_TRIES = 3


def common_log_request_node(state: BankState):
    log = logger.get_logger()
    with log.node("common_log_request"):
        # 업무 노드가 바꾼 데이터가 있으면 거기에, 없으면(거절) 지금 파일 내용에 덧붙입니다.
        data = state.get("new_data") or data_store.load()
        record = {
            "request_id": "req-%04d" % (len(data["requests"]) + 1),
            "owner_id": functions.CURRENT_USER,
            "task_type": state["proposal"]["task"],
            "content": dict(state["proposal"]["rows"]),
            "status": state["result"],
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        data["requests"].append(record)
        log.detail("처리 기록 %s  %s / %s" % (record["request_id"], record["task_type"], record["status"]))

    return {"new_data": data}


def common_save_node(state: BankState):
    # retry 는 저장에만 붙입니다. 승인에 붙이면 같은 질문을 반복하게 됩니다.
    # 저장이 실패해도 파일은 그대로 남습니다 (data_store 가 보장합니다).
    log = logger.get_logger()
    with log.node("common_save"):
        for attempt in range(1, SAVE_TRIES + 1):
            try:
                data_store.save(state["new_data"])
                return {"new_data": None}
            except data_store.DataStoreError:
                log.detail("저장 실패 %d/%d" % (attempt, SAVE_TRIES))     # 사유는 data_store 가 로그에 남깁니다

    # new_data 는 비웁니다. 저장 못 한 데이터를 State 에 남겨 두지 않습니다.
    return {"new_data": None, "result": "실패",
            "error": "저장에 실패해 처리하지 못했습니다. 바뀐 것은 없습니다."}


def common_report_node(state: BankState):
    # 저장과 안내를 나눈 이유: 한 곳에 두면 저장이 실패했는데 "완료" 를 말하게 됩니다.
    with logger.get_logger().node("common_report"):
        if state["result"] == "실패":
            return {"answer": state["error"]}
    return {}
