# 여러 업무가 같이 쓰는 공통 노드입니다. 기획서 6장을 따릅니다.
#
#   common_pending_check : [분기 0] 멈춰 있는 업무가 있는지 봅니다 (main.py 에서 부릅니다)
#   common_approve       : 처리안을 보여주고 승인을 기다립니다 (interrupt)
#   common_interpret     : 승인 질문에 대한 답을 승인 / 거절 / 취소 / 수정 / 모름 으로 가릅니다 (LLM)
#   common_reject        : 거절·취소를 안내하고 끝냅니다
#
# 처리안(proposal)은 각 업무의 propose 노드가 만듭니다. 모양은 다음과 같습니다.
#   {"task": "이체", "rows": [["출금", "생활비"], ["금액", "100,000원"], ...], ...}
# 공통 노드는 task 와 rows 만 읽습니다. 나머지 칸은 업무마다 자유롭게 둡니다.

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel, Field

import logger
from agents.common.prompts import interpret_prompt
from model import llm
from state import BankState

# 그래프가 멈출 때 interrupt 에 넘기는 값입니다.
# kind 를 보고 main.py 가 승인 대기인지, 부족 정보 질문인지 구분합니다.
APPROVAL = "approval"
QUESTION = "question"


def question(text):
    return {"kind": QUESTION, "text": text}


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
    return {"answer": answer}
