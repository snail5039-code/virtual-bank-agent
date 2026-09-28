# 5-3 도메인 반송 경로 점검 확인용입니다.
#
# 실행 : uv run python 테스트/5-3_도메인반송_확인.py
#
# 1단(supervisor)이 틀리는 상황을 일부러 만듭니다.
# update_state(..., as_node="supervisor") 로 "supervisor 가 이 분야를 골랐다" 고 넣은 뒤 그다음부터 실행합니다.
#
# 확인할 것 (user-001 의 가상 계좌 비밀번호 1234 를 씁니다)
#   1) 카드 요청을 계좌로 잘못 보냄 : 계좌 라우터가 "카드 업무" → bounce → 카드로 가서 제대로 처리 (잠금 → 인증 → 승인)
#   2) 계좌 요청을 카드로 잘못 보냄 : 카드 라우터가 "계좌 업무" → bounce → 계좌 조회
#   3) 반송은 1번까지 : 이미 반송한 요청이 또 "내 도메인 아님" 이면 오가지 않고 안내로 끝난다
#   4) 평소         : 1단이 맞게 고르면 반송 없이 그대로 처리된다
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다.

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from langgraph.types import Command

from agents.supervisor.graph import bank_graph
from state import new_request

DATA = "data/data.json"


def run_forced(name, query, domain, answers=(), bounced=None):
    # supervisor 가 domain 을 고른 것처럼 넣고 그다음부터 실행합니다. 질문·승인에는 answers 를 차례로 답합니다.
    config = {"configurable": {"thread_id": "test-5-3-" + name}}
    bank_graph.update_state(config, {**new_request(query), "domain": domain, "reason": "테스트: 일부러 넣은 분야",
                                     "bounced": bounced}, as_node="supervisor")
    result = bank_graph.invoke(None, config=config)
    for answer in answers:
        if "__interrupt__" not in result:
            break
        result = bank_graph.invoke(Command(resume=answer), config=config)
    print("요청     :", query)
    print("1단(강제):", domain, " / 반송 :", "있음" if result.get("bounced") else "없음",
          " / 최종 분야 :", result.get("domain"), "→", result.get("task"))
    if "__interrupt__" in result:
        print(result["__interrupt__"][0].value["text"])
    else:
        print(result["answer"])
    print()


shutil.copy("data/initial_data.json", DATA)

print("===== 1) 카드 요청을 계좌로 잘못 보냄 =====")
run_forced("1", "여행 카드 잠가줘", "계좌", answers=["1234", "승인"])

print("===== 2) 계좌 요청을 카드로 잘못 보냄 =====")
run_forced("2", "내 계좌 잔액 알려줘", "카드")

print("===== 3) 이미 반송한 요청이 또 아니면 안내 =====")
run_forced("3", "여행 카드 잠가줘", "계좌", bounced=True)

print("===== 4) 평소 (1단이 맞게 고름) =====")
config = {"configurable": {"thread_id": "test-5-3-4"}}
result = bank_graph.invoke(new_request("내 카드 목록 보여줘"), config=config)
print("1단 :", result["domain"], "/ 반송 :", "있음" if result.get("bounced") else "없음", "→", result.get("task"))
print(result["answer"])

shutil.copy("data/initial_data.json", DATA)
