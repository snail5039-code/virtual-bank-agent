# 12장 보완 — 후속 결과 조회(5-1)에 날짜·대상 조건 붙이기 확인용입니다.
# LLM 이 키워드와 함께 기간·대상 이름을 뽑고, find_requests 가 조건문으로 거릅니다.
#
# 실행 : uv run python 테스트/보완_결과조회조건_확인.py
#
# 미리 넣어 두는 처리 기록 (어제 2건, 오늘 2건)
#   req-0001 어제  카드 일시 잠금  여행 카드
#   req-0002 어제  이체            생활비 → 저축
#   req-0003 오늘  카드 일시 잠금  생활비 카드
#   req-0004 오늘  이체            생활비 → 여행 자금
#
# 확인할 것
#   1) "아까 이체 됐어?"               → 조건 없음, 가장 최근 이체 req-0004 (지금과 같음)
#   2) "어제 이체 됐어?"               → 기간 = 어제 → req-0002
#   3) "여행 카드 잠근 거 됐어?"       → 대상 = 여행 카드 → req-0001
#   4) "저축으로 보낸 거 됐어?"        → 대상 = 저축 → req-0002
#   5) "어제 생활비 카드 잠근 거 됐어?" → 조건에 맞는 게 없음 → "어제 '생활비 카드' '잠금' 처리한 기록이 없습니다."
#   6) "오늘 처리한 거 다 보여줘"      → 오늘 2건  ("오늘 한 거" 는 1단이 계좌 거래 내역으로 보낼 수 있어 "처리한" 으로 묻습니다)
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다. 요청마다 새 세션으로 부릅니다.

import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agents.supervisor.graph import bank_graph      # noqa: E402
from state import new_request                       # noqa: E402

DATA = "data/data.json"
today = date.today()
yesterday = today - timedelta(days=1)


def record(number, day, task, content):
    return {"request_id": "req-%04d" % number, "owner_id": "user-001", "task_type": task, "content": content,
            "status": "완료", "created_at": "%sT%02d:00:00+09:00" % (day, 9 + number)}


shutil.copy("data/initial_data.json", DATA)
with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
data["requests"] = [
    record(1, yesterday, "카드 일시 잠금", {"카드": "여행 카드 (0000-0000-0000-0002)", "바뀔 상태": "일시 잠금"}),
    record(2, yesterday, "이체", {"출금": "생활비 (110-001-100001)", "입금": "저축 (110-001-100002)  10,000원"}),
    record(3, today, "카드 일시 잠금", {"카드": "생활비 카드 (0000-0000-0000-0001)", "바뀔 상태": "일시 잠금"}),
    record(4, today, "이체", {"출금": "생활비 (110-001-100001)", "입금": "여행 자금 (110-001-100003)  20,000원"}),
]
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

queries = [
    "아까 이체 됐어?",
    "어제 이체 됐어?",
    "여행 카드 잠근 거 됐어?",
    "저축으로 보낸 거 됐어?",
    "어제 생활비 카드 잠근 거 됐어?",
    "오늘 처리한 거 다 보여줘",
]
for number, query in enumerate(queries, start=1):
    config = {"configurable": {"thread_id": "test-result-%d" % number}}
    result = bank_graph.invoke(new_request(query), config=config)
    print("요청 :", query, "  (경로 :", result["domain"], ")")
    print(result["answer"])
    print()

shutil.copy("data/initial_data.json", DATA)
