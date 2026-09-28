# 후속 결과 조회(5-1) 노드입니다. "아까 이체 됐어?" 처럼 앞서 한 업무의 결과를 묻는 질문에 답합니다.
#
#   result_query : 어느 업무인지(키워드)·언제(기간)·무엇을(대상 이름) LLM 이 뽑고,
#                  Python 이 처리 기록(원장, data["requests"])에서 그 조건으로 걸러 보여줍니다
#
# 답의 출처는 원장입니다. LLM 이 기억으로 "됐어요" 라고 답하지 않습니다 (원칙 6).
# 체크포인터는 새 요청마다 업무 칸을 비우고 끄면 사라지므로, 결과는 파일에 남는 원장에서 읽습니다.
# 읽기만 하므로 인증·승인 없이 끝납니다.

from datetime import date
from typing import Literal, Optional

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
    # 언제 한 업무인지. 카드 이용 내역과 같은 방식입니다.
    period: Literal["오늘", "어제", "이번 주", "지난 주", "이번 달", "지난 달", "전체"] = Field(
        default="전체", description="기간")
    start_date: Optional[date] = Field(default=None, description="직접 말한 시작일 YYYY-MM-DD")
    end_date: Optional[date] = Field(default=None, description="직접 말한 종료일 YYYY-MM-DD")
    target_name: Optional[str] = Field(default=None, description="업무의 대상인 카드나 계좌 이름 (예: 여행 카드, 저축)")
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
        today = functions.base_date()
        r = llm_with_result_output.invoke([
            SystemMessage(content=result_prompt.format(today=today, year=today.year)),
            HumanMessage(content=state["query"]),
        ])
        # 기간 : 직접 말한 날짜가 있으면 그 날짜, 없으면 기간 이름으로 계산합니다. 계산은 Python 이 합니다.
        start, end = functions.period_range(r.period)
        start = r.start_date or start
        end = r.end_date or end
        log.detail("추출  업무=%s  기간=%s %s~%s  대상=%s  여러 건=%s" % (
            r.keyword, r.period, start, end, r.target_name, r.show_all))

        records = functions.find_requests(functions.CURRENT_USER, r.keyword, start, end, r.target_name)
        log.detail("처리 기록 %d건" % len(records))

        # 답에 붙일 조건 설명. 예) "어제 '여행 카드' '잠금' "
        what = ""
        if start or end:
            what += (r.period if r.period != "전체" and not r.start_date else "%s~%s" % (start or "", end or "")) + " "
        if r.target_name:
            what += "'%s' " % r.target_name
        if r.keyword:
            what += "'%s' " % r.keyword
        if not records:
            return {"answer": "%s처리한 기록이 없습니다." % what}

        if r.show_all:
            shown = records[:SHOW_MAX]
            lines = ["%s처리 기록 %d건입니다. (최근순)" % (what, len(shown))]
        else:
            # 한 건만 물으면 조건에 맞는 가장 최근 기록이 답입니다.
            shown = records[:1]
            lines = ["가장 최근 %s기록입니다." % what]
        lines += [record_text(rec) for rec in shown]
    return {"answer": "\n".join(lines)}
