# 4-1 카드 에이전트 라우팅 + 은행별 카드 조회 확인용입니다.
#
# 실행 : uv run python 테스트/4-1_카드조회_확인.py
#
# 확인할 것
#   1) get_cards 가 user-001 카드만 돌려주고, find_cards 가 조건(은행·이름·종류·상태)으로 거른다
#   2) 카드 조회 요청은 카드 → 조회 로 가서 목록이 상태(한국어)와 함께 나온다
#      LLM 이 뽑은 조건은 로그 대신 결과 장수로 확인합니다
#   3) 없는 은행("미래은행 카드") 은 "조건에 맞는 카드가 없습니다" 로 끝난다
#   4) 결제 요청은 카드 → 결제 로 가서 "준비 중" 이 나온다 (설정·재발급은 4-3 ~ 4-5 테스트에서 확인)
# 조회만 하므로 data.json 은 바뀌지 않습니다.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import functions
from agents.supervisor.graph import bank_graph

# ============================================================ 1) 함수만
print("1) get_cards")
cards = functions.get_cards("user-001")
print("   user-001 카드 %d장, 다른 사람 카드 섞임: %s" % (len(cards), any(c["owner_id"] != "user-001" for c in cards)))
print("   가상 은행 %d장 / 미래은행 %d장" % (len(functions.find_cards("user-001", bank_name="가상 은행")),
                                           len(functions.find_cards("user-001", bank_name="미래은행"))))
print("   여행 카드 %d장 / 신용 %d장 / 분실 정지 %d장" % (
    len(functions.find_cards("user-001", card_name="여행 카드")),
    len(functions.find_cards("user-001", card_type="신용")),
    len(functions.find_cards("user-001", status="분실 정지"))))
print()

# ============================================================ 2) 3) 4) 그래프
config = {"configurable": {"thread_id": "test-4-1"}}

queries = [
    "내 카드 목록 보여줘",
    "가상은행 카드 보여줘",
    "가상 은행 카드 보여줘",
    "미래은행 카드 보여줘",
    "여행 카드만 보여줘",
    "신용카드만 보여줘",
    "정지된 카드 보여줘",
    "쓸 수 있는 체크카드 보여줘",
    "이번 달 카드값 내줘",
]

for query in queries:
    result = bank_graph.invoke({"query": query}, config=config)
    print("요청 :", query)
    print("경로 :", result["domain"], "→", result.get("task"))
    print(result["answer"])
    print()
