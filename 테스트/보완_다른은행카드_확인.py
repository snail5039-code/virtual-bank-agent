# 12장 보완 — "OO은행 말고 다른 은행은?" 확인용입니다.
# 기준 은행은 사용자가 말한 은행입니다. LLM 이 뺄 은행(exclude_banks)을 뽑고, find_cards 가 그 은행 카드만 빼고,
# 남은 카드를 은행별로 나눠 보여줍니다. 은행 이름 없이 "다른 은행은?" 이면 대화 기억(rewrite)이 앞에서 말한 은행을 채워 줍니다.
#
# 실행 : uv run python 테스트/보완_다른은행카드_확인.py
#
# 확인할 것
#   1) 남는 카드가 없을 때 : "가상은행 말고 다른 은행 카드 있어?" → "가상은행 말고 다른 은행 카드는 없습니다."
#   (여기서 user-001 에게 미래은행 체크카드 한 장을 넣습니다. 카드 등록으로 생기는 것과 같은 모양)
#   2) "우리은행 말고 다른 은행은 뭐가 있어?" → 우리은행 카드는 없으니 [가상은행] 6장 + [미래은행] 1장
#   3) "가상은행 빼고 카드 보여줘"            → [미래은행] 1장
#   4) "미래은행 말고 신용카드 보여줘"        → [가상은행] 신용카드 2장
#   5) 앞 대화 "미래은행 카드 보여줘" 뒤에 "다른 은행은?" → 대화 기억이 "미래은행 말고 ..." 로 바꿔 → [가상은행] 6장
#   6) 앞 대화 없이 "다른 은행 카드는?"       → 뺄 은행을 모르므로 전체 7장
#   7) "미래은행 카드 보여줘"                 → 은행 이름으로 물으면 1장 (지금과 같음)
#
# 시작과 끝에 data.json 을 원본으로 되돌립니다. 요청마다 새 세션으로 부릅니다.

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agents.supervisor.graph import bank_graph      # noqa: E402
from state import new_request                       # noqa: E402

DATA = "data/data.json"


def ask(number, query, history=None):
    config = {"configurable": {"thread_id": "test-other-bank-%d" % number}}
    result = bank_graph.invoke(new_request(query, history), config=config)
    f = result.get("card_filter") or {}
    print("요청 :", query, "  → 다듬은 문장 :", result["query"])
    print("       (은행 =", f.get("bank_names"), " 뺄 은행 =", f.get("exclude_banks"), ")")
    print(result["answer"])
    print()


shutil.copy("data/initial_data.json", DATA)
ask(1, "가상은행 말고 다른 은행 카드 있어?")

with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
data["cards"].append({
    "card_id": "card-009", "owner_id": "user-001", "name": "미래은행 체크카드", "account_id": "acc-001",
    "status": "active", "card_number": "1234-5678-1234-5678", "card_type": "debit", "bank_code": None,
    "bank_name": "미래은행", "card_password": None, "credit_limit": None, "report_reason": None, "reported_at": None})
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("(미래은행 체크카드를 넣었습니다)")
print()

ask(2, "우리은행 말고 다른 은행은 뭐가 있어?")
ask(3, "가상은행 빼고 카드 보여줘")
ask(4, "미래은행 말고 신용카드 보여줘")
ask(5, "다른 은행은?", history=[{"request": "미래은행 카드 보여줘",
                                "answer": "카드 1장입니다.\n- 미래은행 체크카드 (미래은행 체크) : 연결 계좌 생활비  [사용 가능]"}])
ask(6, "다른 은행 카드는?")
ask(7, "미래은행 카드 보여줘")

shutil.copy("data/initial_data.json", DATA)
