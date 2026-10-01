import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from langgraph.types import Command

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from state import new_request
from agents.supervisor.graph import bank_graph
from openevals.llm import create_llm_as_judge
from openevals.prompts import CORRECTNESS_PROMPT
from langchain_google_genai import ChatGoogleGenerativeAI
from golden_set import golden_set
import data_store

MODEL_NAME = "gemini-3.6-flash"
model = ChatGoogleGenerativeAI(model=MODEL_NAME)

answer_judge = create_llm_as_judge(
    prompt=CORRECTNESS_PROMPT,
    judge=model,
    feedback_key="answer_correct",
)

INITIAL_DATA = ROOT / "data" / "initial_data.json"
DATA = ROOT / "data" / "data.json"


def load_data():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def apply_fixture(data, fixture):
    """평가 사례가 필요로 하는 시작 상태만 초기 데이터 위에 덮어쓴다."""
    for collection, records in fixture.get("set", {}).items():
        key = fixture.get("keys", {}).get(collection)
        if not key:
            key = {
                "accounts": "account_id",
                "registered_accounts": "registered_id",
                "cards": "card_id",
                "card_statements": "statement_id",
                "reissue_applications": "application_id",
                "scheduled_transfers": "schedule_id",
            }[collection]
        indexed = {record[key]: record for record in data[collection]}
        for record_id, values in records.items():
            indexed[record_id].update(values)
    for collection, records in fixture.get("append", {}).items():
        data[collection].extend(deepcopy(records))

def run_agent(inputs):
    # 새 thread_id로 이전 사례의 대화·승인 상태와 분리한다.
    config = {
        "configurable": {"thread_id": str(uuid4())},
        "recursion_limit": 40,
    }
    turns = iter(inputs["turns"])
    interrupt_seen = []
    used_turns = []

    shutil.copy(INITIAL_DATA, DATA)
    data_store.setup(DATA, INITIAL_DATA)

    fixture = inputs.get("fixture")
    if fixture:
        prepared = load_data()
        apply_fixture(prepared, fixture)
        data_store.save(prepared)

    before = load_data()

    first_turn = next(turns)
    used_turns.append(first_turn)
    result = bank_graph.invoke(
        new_request(first_turn, []),
        config=config,
    )

    while result.get("__interrupt__"):
        interrupts = result["__interrupt__"]

        for item in interrupts:
            interrupt_seen.append(item.value["kind"])

        next_turn = next(turns, None)

        if next_turn is None:
            break

        used_turns.append(next_turn)

        result = bank_graph.invoke(
            Command(resume=next_turn),
            config=config,
        )

    pending_left = bool(result.get("__interrupt__"))
    after = load_data()

    return {
        "answer": result["__interrupt__"][0].value["text"] if pending_left else result["answer"],
        "interrupts": interrupt_seen,
        "used_turns": used_turns,
        "pending": pending_left,
        "before": before,
        "after": after,
    }


def bank_eval_target(inputs):
    return run_agent(inputs)


def evaluate_answer(inputs, outputs, reference_outputs):
    # 사례 딕셔너리에서 답변 평가에 필요한 값만 꺼내 평가 함수에 전달한다.
    return answer_judge(
        inputs=inputs["turns"][0],  # Agent에 전달한 사용자 질문
        outputs=outputs["answer"],  # Agent가 생성한 실제 답변
        reference_outputs=reference_outputs["answer_criteria"],  # Golden set의 기대 답변 기준
    )

def evaluate_interrupts(inputs, outputs, reference_outputs):
    expected = reference_outputs["expected_interrupts"]
    actual = outputs["interrupts"]
    passed = actual == expected

    return {
        "key": "interrupt_flow",
        "score": passed,
        "comment": f"기대 interrupt: {expected}, 실제 interrupt: {actual}",
    }

def evaluate_data(inputs, outputs, reference_outputs):
    expected = reference_outputs["expected_data"]
    before = outputs["before"]
    after = outputs["after"]

    checks = []

    if "changed" in expected:
        checks.append(after == before if expected["changed"] is False else after != before)

    if "accounts" in expected:
        accounts = {a["account_id"]: a for a in after["accounts"]}
        for account_id, values in expected["accounts"].items():
            for key, expected_value in values.items():
                checks.append(accounts[account_id][key] == expected_value)

    if "cards" in expected:
        cards = {c["card_id"]: c for c in after["cards"]}
        for card_id, values in expected["cards"].items():
            for key, expected_value in values.items():
                checks.append(cards[card_id][key] == expected_value)

    if "card_statements" in expected:
        statements = {s["statement_id"]: s for s in after["card_statements"]}
        for statement_id, values in expected["card_statements"].items():
            for key, expected_value in values.items():
                checks.append(statements[statement_id][key] == expected_value)

    if "transactions_added" in expected:
        added = len(after["transactions"]) - len(before["transactions"])
        checks.append(added == expected["transactions_added"])

    if "schedules_added" in expected:
        added = len(after["scheduled_transfers"]) - len(before["scheduled_transfers"])
        checks.append(added == expected["schedules_added"])

    if "reissue_applications_added" in expected:
        added = len(after["reissue_applications"]) - len(before["reissue_applications"])
        checks.append(added == expected["reissue_applications_added"])

    if "registered_accounts_added" in expected:
        added = len(after["registered_accounts"]) - len(before["registered_accounts"])
        checks.append(added == expected["registered_accounts_added"])

    if "cards_added" in expected:
        added = len(after["cards"]) - len(before["cards"])
        checks.append(added == expected["cards_added"])

    if "installments_added" in expected:
        added = len(after["card_installments"]) - len(before["card_installments"])
        checks.append(added == expected["installments_added"])

    for collection, id_key in {
        "registered_accounts": "registered_id",
        "reissue_applications": "application_id",
        "scheduled_transfers": "schedule_id",
        "card_installments": "installment_id",
    }.items():
        if collection in expected:
            records = {record[id_key]: record for record in after[collection]}
            for record_id, values in expected[collection].items():
                checks.append(record_id in records)
                if record_id in records:
                    for key, expected_value in values.items():
                        checks.append(records[record_id].get(key) == expected_value)

    if "last_schedule" in expected:
        last = after["scheduled_transfers"][-1] if after["scheduled_transfers"] else {}
        for key, expected_value in expected["last_schedule"].items():
            checks.append(last.get(key) == expected_value)

    if "last_reissue_application" in expected:
        last = after["reissue_applications"][-1] if after["reissue_applications"] else {}
        for key, expected_value in expected["last_reissue_application"].items():
            checks.append(last.get(key) == expected_value)

    if "last_request" in expected:
        last = after["requests"][-1] if after["requests"] else {}
        for key, expected_value in expected["last_request"].items():
            checks.append(last.get(key) == expected_value)

    passed = all(checks)

    return {
        "key": "data_state",
        "score": passed,
        "comment": f"expected_data={expected}",
    }

# 출력 보기 좋게 하기
def print_case_header(case):
    case_id = case["case_id"]
    turns = case["inputs"]["turns"]

    print("=" * 80)
    print(f"[{case_id}]")
    print("입력:", " -> ".join(turns))

def main():
    rows = []

    for case in golden_set:
        print_case_header(case)

        inputs = case["inputs"]
        reference = case["reference"]

        outputs = bank_eval_target(inputs)
        print("실제 답변:", outputs["answer"])
        print()
        print("기대 interrupt:", reference["expected_interrupts"])
        print()
        print("실제 interrupt:", outputs["interrupts"])
        print()


        answer_result = evaluate_answer(inputs, outputs, reference)
        interrupt_result = evaluate_interrupts(inputs, outputs, reference)
        data_result = evaluate_data(inputs, outputs, reference)

        print("답변 평가:", "PASS" if answer_result["score"] else "FAIL")
        print()
        print("interrupt 평가:", "PASS" if interrupt_result["score"] else "FAIL")
        print()
        print("data 평가:", "PASS" if data_result["score"] else "FAIL")
        print()
        print("pending:", outputs["pending"])
        print()
        
        all_passed = (
            answer_result["score"]
            and interrupt_result["score"]
            and data_result["score"]
        )

        print("전체 결과 : ", "PASS" if all_passed else "FAIL")

        print("답변 평가 코멘트 : ", answer_result.get("comment"))

        rows.append({
            "case_id": case["case_id"],
            "answer": answer_result["score"],
            "interrupt": interrupt_result["score"],
            "data": data_result["score"],
            "pending": outputs["pending"],
        })

    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
