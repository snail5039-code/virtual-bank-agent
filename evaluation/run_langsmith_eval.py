from uuid import uuid4
from langsmith import Client

from golden_set import golden_set
from run_eval import (bank_eval_target, evaluate_answer, evaluate_interrupts, evaluate_data)

def create_dataset():
    client = Client()

    dataset = client.create_dataset(
        dataset_name=f"virtual-bank-eval-{uuid4().hex[:8]}",
    )

    client.create_examples(
        dataset_id=dataset.id,
        examples=[
            {
                "inputs": case["inputs"],
                "outputs": case["reference"],
                "metadata": {"case_id": case["case_id"]},
            }
            for case in golden_set
        ],
    )

    print("Dataset 이름:", dataset.name)
    print("등록한 사례 수:", len(golden_set))

    return dataset

def run_langsmith_eval():
    client = Client()
    dataset = create_dataset()

    experiment = client.evaluate(
        bank_eval_target,
        data=dataset.id,
        evaluators=[
            evaluate_answer,
            evaluate_interrupts,
            evaluate_data,
        ],
        experiment_prefix="virtual-bank",
        metadata={"mode": "langsmith"},
    )

    return experiment

if __name__ == "__main__":
    run_langsmith_eval()
    