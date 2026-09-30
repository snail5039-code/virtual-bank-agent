golden_set = [
    {
        "case_id": "account_list",
        "inputs": {
            "turns": [
                "내 계좌 목록과 잔액 보여줘",
            ],
        },
        "reference": {
            "answer_criteria": "생활비 1,431,800원, 저축 2,280,000원, 여행 자금 390,000원을 안내한다.",
            "expected_interrupts": [],
            "expected_data": {
                "changed": False,
            },
        },
    },

    {
        "case_id": "transfer_approve",
        "inputs": {
            "turns": [
                "생활비에서 저축으로 10만원 보내줘",
                "1234",
                "승인",
            ],
        },
        "reference": {
            "answer_criteria": "생활비에서 저축으로 100,000원 이체 완료를 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "accounts": {
                    "acc-001": {"balance": 1331800},
                    "acc-002": {"balance": 2380000},
                },
                "transactions_added": 2,
                "last_request": {
                    "task_type": "이체",
                    "status": "완료",
                },
            },
        },
    },

    {
        "case_id": "transfer_reject",
        "inputs": {
            "turns": [
                "생활비에서 저축으로 10만원 보내줘",
                "1234",
                "거절",
            ],
        },
        "reference": {
            "answer_criteria": "이체를 진행하지 않았고 바뀐 것이 없다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "accounts": {
                    "acc-001": {"balance": 1431800},
                    "acc-002": {"balance": 2280000},
                },
                "transactions_added": 0,
                "last_request": {
                    "task_type": "이체",
                    "status": "거절",
                },
            },
        },
    },
    {
        "case_id": "transfer_missing_amount",
        "inputs": {
            "turns": [
                "생활비에서 저축으로 보내줘",
            ],
        },
        "reference": {
            "answer_criteria": "이체 금액을 물어본다. 완료됐다고 말하지 않는다.",
            "expected_interrupts": ["question"],
            "expected_data": {
                "changed": False,
            },
        },
    },
    {
        "case_id": "transfer_insufficient",
        "inputs": {
            "turns": [
                "생활비에서 저축으로 1억원 보내줘",
            ],
        },
        "reference": {
            "answer_criteria": "잔액 부족을 안내한다.",
            "expected_interrupts": [],
            "expected_data": {
                "changed": False,
            },
        },
    },
    {
        "case_id": "conditional_transfer",
        "inputs": {
            "turns": [
                "생활비에 40만원 남기고 나머지 저축으로 보내",
                "1234",
                "승인"
            ],
        },
        "reference": {
            "answer_criteria": "1,031,800원 이체 완료를 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "accounts": {
                    "acc-001": {"balance": 400000},
                    "acc-002": {"balance": 3311800},
                },
                "transactions_added": 2,
                "last_request": {
                    "task_type": "이체",
                    "status": "완료",
                },
            },
        },
    },

    {
        "case_id": "account_history",
        "inputs": {
            "turns": [
                "이번 달 생활비 출금 내역 보여줘",
            ],
        },
        "reference": {
            "answer_criteria": "이번 달 생활비 출금 내역을 안내한다",
            "expected_interrupts": [],
            "expected_data": {
                "changed" : False,
            },
        },
    },

    {
        "case_id": "scheduled_transfer",
        "inputs": {
            "turns": [
                "내일 오전 9시에 생활비에서 저축으로 10만원 보내줘",
                "1234",
                "승인"
            ],
        },
        "reference": {
            "answer_criteria": "100000원 예약 이체를 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "accounts": {
                    "acc-001": {"balance": 1431800},
                    "acc-002": {"balance": 2280000},
                },
                "transactions_added": 0,
                "schedules_added": 1,
                "last_schedule": {
                    "from_account": "acc-001",
                    "to_account": "acc-002",
                    "amount": 100000,
                    "status": "예약",
                },
                "last_request": {
                    "task_type": "예약 이체",
                    "status": "완료",
                },                
            },
        },
    },
]