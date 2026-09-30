from langgraph.types import Command
from state import new_request
from agents.supervisor.graph import bank_graph
from openevals.llm import create_llm_as_judge
from openevals.prompts import CORRECTNESS_PROMPT
from langchain_google_genai import ChatGoogleGenerativeAI

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

def run_agent(inputs):
    # 새 thread_id로 이전 사례의 대화·승인 상태와 분리한다.
    config = {
        "configurable": {"thread_id": str(uuid4())},
        "recursion_limit": 40,
    }
    turns = iter(inputs["turns"])
    interrupt_seen = {}
    used_turns = []

    shutil.copy(INITIAL_DATA, DATA)
    data_store.setup(DATA, INITIAL_DATA)

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

    if "transactions_added" in expected:
        added = len(after["transactions"]) - len(before["transactions"])
        checks.append(added == expected["transactions_added"])

    if "schedules_added" in expected:
        added = len(after["scheduled_transfers"]) - len(before["scheduled_transfers"])
        checks.append(added == expected["schedules_added"])

    if "last_schedule" in expected:
        last = after["scheduled_transfers"][-1] if after["scheduled_transfers"] else {}
        for key, expected_value in expected["last_schedule"].items():
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

def main():
    pass