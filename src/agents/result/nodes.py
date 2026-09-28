# 후속 결과 조회(5-1) 노드입니다. "아까 이체 됐어?" 처럼 앞서 한 업무의 결과를 묻는 질문에 답합니다.
#
#   result_query : 어느 업무인지 LLM 이 키워드만 뽑고, Python 이 처리 기록(원장, data["requests"])에서 찾아 보여줍니다
#
# 답의 출처는 원장입니다. LLM 이 기억으로 "됐어요" 라고 답하지 않습니다 (원칙 6).
# 체크포인터는 새 요청마다 업무 칸을 비우고 끄면 사라지므로, 결과는 파일에 남는 원장에서 읽습니다.
# 읽기만 하므로 인증·승인 없이 끝납니다.

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

import functions
import logger
from agents.result.prompts import result_prompt
from model import llm
from state import BankState

SHOW_MAX = 5    # "다 보여줘" 일 때 최근 몇 건까지 보여줄지


class ResultQuery(BaseModel):
    keyword: Optional[str] = Field(default=None, description="업무를 나타내는 짧은 말 (예: 이체, 잠금, 결제)")
    show_all: bool = Field(default=False, description="여러 건을 보고 싶어 하는지")


llm_with_result_output = llm.with_structured_output(ResultQuery)


def record_text(record):
    # 기록 한 건. 예) 09월 28일 09:31  이체  [완료]
    #                  - 출금 : 생활비 ...
    lines = ["%s  %s  [%s]" % (functions.parse_time(record["created_at"]).strftime("%m월 %d일 %H:%M"),
                               record["task_type"], record["status"])]
    lines += ["    - %s : %s" % (label, value) for label, value in record["content"].items()]
    return "\n".join(lines)


def result_query_node(state: BankState):
    log = logger.get_logger()
    with log.node("result_query"):
        r = llm_with_result_output.invoke([
            SystemMessage(content=result_prompt),
            HumanMessage(content=state["query"]),
        ])
        log.detail("추출  업무=%s  여러 건=%s" % (r.keyword, r.show_all))

        records = functions.find_requests(functions.CURRENT_USER, r.keyword)
        log.detail("처리 기록 %d건" % len(records))
        if not records:
            what = "'%s' " % r.keyword if r.keyword else ""
            return {"answer": "%s처리한 기록이 없습니다. (예약 이체 결과는 '예약 이체 목록 보여줘' 로 볼 수 있습니다)" % what}

        if r.show_all:
            shown = records[:SHOW_MAX]
            lines = ["최근 처리 기록 %d건입니다." % len(shown)]
        else:
            # 한 건만 물으면 가장 최근 기록이 답입니다.
            shown = records[:1]
            lines = ["가장 최근 %s기록입니다." % ("'%s' " % r.keyword if r.keyword else "")]
        lines += [record_text(rec) for rec in shown]
    return {"answer": "\n".join(lines)}
