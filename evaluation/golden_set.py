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
    {
        "case_id": "card_list",
        "inputs": {
            "turns": [
                "내 카드 목록 보여줘",
            ],
        },
        "reference": {
            "answer_criteria": "생활비 카드, 여행 카드, 생활비 신용카드, 여행 신용카드 목록과 상태를 안내한다",
            "expected_interrupts": [],
            "expected_data": {
                "changed": False,
            },
        },
    },

    {
        "case_id": "card_lock_approve",
        "inputs": {
            "turns": [
                "생활비 카드 잠가줘",
                "1234",
                "승인",
            ],
        },
        "reference": {
            "answer_criteria": "생활비 카드를 일시 잠금 처리했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "cards": {
                    "card-001": {"status": "locked"},
                },
                "last_request": {
                    "task_type": "카드 일시 잠금",
                    "status": "완료",
                },
            },
        },
    },

    {
        "case_id": "card_lock_reject",
        "inputs": {
            "turns": [
                "생활비 카드 잠가줘",
                "1234",
                "거절",
            ],
        },
        "reference": {
            "answer_criteria": "카드 잠금을 진행하지 않았다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "cards": {
                    "card-001": {"status": "active"},
                },
                "last_request": {
                    "task_type": "카드 일시 잠금",
                    "status": "거절",
                },
            },
        },
    },

    {
        "case_id": "card_lost_report",
        "inputs": {
            "turns": [
                "여행 카드 분실 신고해줘",
                "1234",
                "승인",
            ],
        },
        "reference": {
            "answer_criteria": "여행 카드를 분실 신고 처리했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "cards": {
                    "card-002": {
                        "status": "lost",
                        "report_reason": "분실",
                    },
                },
                "last_request": {
                    "task_type": "카드 분실 신고",
                    "status": "완료",
                },
            },
        },
    },

    {
        "case_id": "card_billing_query",
        "inputs": {
            "turns": [
                "생활비 신용카드 9월 카드값 알려줘",
            ],
        },
        "reference": {
            "answer_criteria": "생활비 신용카드 2026년 9월 청구 금액 452,000원을 안내한다.",
            "expected_interrupts": [],
            "expected_data": {
                "changed": False,
            },
        },
    },

    {
        "case_id": "card_billing_pay",
        "inputs": {
            "turns": [
                "생활비 신용카드 9월 카드값 생활비 계좌에서 내줘",
                "1234",
                "승인",
            ],
        },
        "reference": {
            "answer_criteria": "생활비 신용카드 9월 카드값 452,000원 결제 완료를 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "accounts": {
                    "acc-001": {"balance": 979800},
                },
                "transactions_added": 1,
                "card_statements": {
                    "stmt-003": {
                        "remaining_amount": 0,
                        "status": "paid",
                    },
                },
                "last_request": {
                    "task_type": "카드값 전체 결제",
                    "status": "완료",
                },
            },
        },
    },

    {
        "case_id": "card_reissue_query",
        "inputs": {
            "turns": [
                "재발급 신청 내역 보여줘",
            ],
        },
        "reference": {
            "answer_criteria": "구 생활비 카드와 구 여행 카드의 재발급 신청 상태를 안내한다.",
            "expected_interrupts": [],
            "expected_data": {
                "changed": False,
            },
        },
    },

    {
        "case_id": "card_reissue_already_exists",
        "inputs": {
            "turns": [
                "구 여행 카드 재발급 집으로 신청해줘",
            ],
        },
        "reference": {
            "answer_criteria": "구 여행 카드는 이미 재발급 신청이 있다고 안내한다.",
            "expected_interrupts": [],
            "expected_data": {
                "changed": False,
            },
        },
    },

    # 계좌 조회·설정
    {
        "case_id": "registered_account_list",
        "inputs": {"turns": ["등록해 둔 계좌 목록 보여줘"]},
        "reference": {
            "answer_criteria": "동생 생활비와 친구 민수 등록 계좌를 안내한다.",
            "expected_interrupts": [],
            "expected_data": {"changed": False},
        },
    },
    {
        "case_id": "account_alias_change",
        "inputs": {"turns": ["여행 자금 계좌 별명을 휴가비로 바꿔줘", "1234", "승인"]},
        "reference": {
            "answer_criteria": "여행 자금 계좌의 별명을 휴가비로 변경했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "accounts": {"acc-003": {"nickname": "휴가비"}},
                "last_request": {"task_type": "계좌 별명 변경", "status": "완료"},
            },
        },
    },
    {
        "case_id": "account_purpose_change",
        "inputs": {"turns": ["저축 계좌 용도를 결혼 자금으로 바꿔줘", "1234", "승인"]},
        "reference": {
            "answer_criteria": "저축 계좌의 용도를 결혼 자금으로 변경했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "accounts": {"acc-002": {"purpose": "결혼 자금"}},
                "last_request": {"task_type": "계좌 용도 변경", "status": "완료"},
            },
        },
    },
    {
        "case_id": "registered_account_add",
        "inputs": {"turns": ["미래은행 210-11-223344 이영희 계좌를 영희로 등록해줘", "1234", "승인"]},
        "reference": {
            "answer_criteria": "영희 계좌를 등록했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "registered_accounts_added": 1,
                "registered_accounts": {"reg-003": {"nickname": "영희", "holder_name": "이영희"}},
                "last_request": {"task_type": "계좌 등록", "status": "완료"},
            },
        },
    },
    {
        "case_id": "registered_account_delete",
        "inputs": {"turns": ["친구 민수 등록 계좌 삭제해줘", "1234", "승인"]},
        "reference": {
            "answer_criteria": "친구 민수 등록 계좌를 삭제했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "registered_accounts_added": -1,
                "last_request": {"task_type": "등록 계좌 삭제", "status": "완료"},
            },
        },
    },
    {
        "case_id": "scheduled_transfer_list_empty",
        "inputs": {"turns": ["예약 이체 목록 보여줘"]},
        "reference": {
            "answer_criteria": "예약 이체가 없다고 안내한다.",
            "expected_interrupts": [],
            "expected_data": {"changed": False},
        },
    },
    {
        "case_id": "scheduled_transfer_cancel",
        "inputs": {
            "turns": ["sch-001 예약 이체 취소해줘", "1234", "승인"],
            "fixture": {"append": {"scheduled_transfers": [{
                "schedule_id": "sch-001", "owner_id": "user-001", "from_account": "acc-001",
                "to_account": "acc-002", "amount": 100000,
                "scheduled_at": "2026-10-02T09:00:00+09:00", "status": "예약"
            }]}},
        },
        "reference": {
            "answer_criteria": "sch-001 예약 이체를 취소했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "scheduled_transfers": {"sch-001": {"status": "취소"}},
                "last_request": {"task_type": "예약 이체 취소", "status": "완료"},
            },
        },
    },

    # 카드 조회
    {
        "case_id": "card_payment_account_query",
        "inputs": {"turns": ["생활비 카드 결제 계좌 알려줘"]},
        "reference": {
            "answer_criteria": "생활비 카드의 결제 계좌가 생활비 계좌라고 안내한다.",
            "expected_interrupts": [],
            "expected_data": {"changed": False},
        },
    },
    {
        "case_id": "card_number_query",
        "inputs": {"turns": ["여행 카드 번호 알려줘", "1234"]},
        "reference": {
            "answer_criteria": "여행 카드 번호 0000-0000-0000-0002를 안내한다.",
            "expected_interrupts": ["secret"],
            "expected_data": {"changed": False},
        },
    },
    {
        "case_id": "card_membership_query",
        "inputs": {"turns": ["내 카드 멤버십 보여줘"]},
        "reference": {
            "answer_criteria": "가상포인트 골드 32,400P와 여행 마일리지 실버 8,700P를 안내한다.",
            "expected_interrupts": [],
            "expected_data": {"changed": False},
        },
    },
    {
        "case_id": "card_history_query",
        "inputs": {"turns": ["지난 달 여행 카드 이용 내역 보여줘"]},
        "reference": {
            "answer_criteria": "지난 달 여행 카드 이용 내역과 합계를 안내한다.",
            "expected_interrupts": [],
            "expected_data": {"changed": False},
        },
    },

    # 카드 설정
    {
        "case_id": "card_unlock",
        "inputs": {
            "turns": ["생활비 카드 잠금 풀어줘", "1234", "승인"],
            "fixture": {"set": {"cards": {"card-001": {"status": "locked"}}}},
        },
        "reference": {
            "answer_criteria": "생활비 카드의 잠금을 해제했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "cards": {"card-001": {"status": "active"}},
                "last_request": {"task_type": "카드 잠금 해제", "status": "완료"},
            },
        },
    },
    {
        "case_id": "card_cancel",
        "inputs": {"turns": ["여행 카드 해지해줘", "1234", "승인"]},
        "reference": {
            "answer_criteria": "여행 카드를 해지했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "cards": {"card-002": {"status": "cancelled"}},
                "last_request": {"task_type": "카드 해지", "status": "완료"},
            },
        },
    },
    {
        "case_id": "card_alias_change",
        "inputs": {"turns": ["여행 카드 별칭을 휴가 카드로 바꿔줘", "1234", "승인"]},
        "reference": {
            "answer_criteria": "여행 카드 별칭을 휴가 카드로 변경했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "cards": {"card-002": {"name": "휴가 카드"}},
                "last_request": {"task_type": "카드 별칭 변경", "status": "완료"},
            },
        },
    },
    {
        "case_id": "card_password_change",
        "inputs": {"turns": ["여행 카드 비밀번호 바꿔줘", "1234", "5678", "승인"]},
        "reference": {
            "answer_criteria": "여행 카드 비밀번호를 변경했다고 안내한다.",
            "expected_interrupts": ["secret", "secret", "approval"],
            "expected_data": {"last_request": {"task_type": "카드 비밀번호 변경", "status": "완료"}},
        },
    },
    {
        "case_id": "card_register",
        "inputs": {"turns": ["미래은행 체크카드 1234-5678-1234-5678을 생활비 계좌로 새 카드라는 이름으로 등록해줘", "1234", "승인"]},
        "reference": {
            "answer_criteria": "새 카드를 등록했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "cards_added": 1,
                "last_request": {"task_type": "카드 등록", "status": "완료"},
            },
        },
    },

    # 카드값 조회·결제
    {
        "case_id": "card_statement_query",
        "inputs": {"turns": ["생활비 신용카드 9월 명세서 상세 보여줘"]},
        "reference": {
            "answer_criteria": "생활비 신용카드 2026년 9월 명세서의 백화점, 마트, 식당 이용 내역과 합계를 안내한다.",
            "expected_interrupts": [],
            "expected_data": {"changed": False},
        },
    },
    {
        "case_id": "card_billing_partial_pay",
        "inputs": {"turns": ["생활비 신용카드 9월 카드값 중 10만원만 생활비 계좌에서 내줘", "1234", "승인"]},
        "reference": {
            "answer_criteria": "100,000원을 결제하고 352,000원이 남았다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "accounts": {"acc-001": {"balance": 1331800}},
                "card_statements": {"stmt-003": {"remaining_amount": 352000, "status": "partial"}},
                "transactions_added": 1,
                "last_request": {"task_type": "카드값 부분 결제", "status": "완료"},
            },
        },
    },
    {
        "case_id": "card_billing_installment",
        "inputs": {"turns": ["생활비 신용카드 9월 카드값을 생활비 계좌에서 3개월 분할로 내줘", "1234", "승인"]},
        "reference": {
            "answer_criteria": "3개월 분할 결제를 시작하고 첫 회차 150,668원을 냈다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "accounts": {"acc-001": {"balance": 1281132}},
                "card_statements": {"stmt-003": {"remaining_amount": 301332, "status": "partial"}},
                "transactions_added": 1,
                "installments_added": 1,
                "last_request": {"task_type": "카드값 분할 결제", "status": "완료"},
            },
        },
    },

    # 재발급 변경 기능. 초기 데이터의 신청 상태를 접수 상태로 준비해야 변경·취소가 가능하다.
    {
        "case_id": "card_reissue_apply",
        "inputs": {
            "turns": ["구 생활비 카드 재발급을 회사로 신청해줘", "1234", "승인"],
            "fixture": {"set": {"reissue_applications": {"app-001": {"status": "cancelled"}}}},
        },
        "reference": {
            "answer_criteria": "구 생활비 카드 재발급 신청이 접수됐다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "reissue_applications_added": 1,
                "last_reissue_application": {"card_id": "card-007", "address_id": "addr-work", "status": "received"},
                "last_request": {"task_type": "카드 재발급 신청", "status": "완료"},
            },
        },
    },
    {
        "case_id": "card_reissue_address_change",
        "inputs": {
            "turns": ["구 생활비 카드 재발급 배송지를 회사로 바꿔줘", "1234", "승인"],
            "fixture": {"set": {"reissue_applications": {"app-001": {"status": "received"}}}},
        },
        "reference": {
            "answer_criteria": "app-001 재발급 배송지를 회사로 변경했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "reissue_applications": {"app-001": {"address_id": "addr-work", "status": "received"}},
                "last_request": {"task_type": "카드 재발급 배송지 수정", "status": "완료"},
            },
        },
    },
    {
        "case_id": "card_reissue_cancel",
        "inputs": {
            "turns": ["구 생활비 카드 재발급 신청 취소해줘", "1234", "승인"],
            "fixture": {"set": {"reissue_applications": {"app-001": {"status": "received"}}}},
        },
        "reference": {
            "answer_criteria": "app-001 재발급 신청을 취소했다고 안내한다.",
            "expected_interrupts": ["secret", "approval"],
            "expected_data": {
                "reissue_applications": {"app-001": {"status": "cancelled"}},
                "last_request": {"task_type": "카드 재발급 신청 취소", "status": "완료"},
            },
        },
    },

    # 처리 결과 조회와 지원 범위 밖 안내
    {
        "case_id": "result_query",
        "inputs": {
            "turns": ["최근 이체 결과 알려줘"],
            "fixture": {"append": {"requests": [{
                "request_id": "req-001", "owner_id": "user-001", "task_type": "이체",
                "content": {"출금": "생활비", "입금": "저축", "금액": "100,000원"},
                "status": "완료", "created_at": "2026-10-01T09:00:00+09:00"
            }]}},
        },
        "reference": {
            "answer_criteria": "가장 최근 이체 처리 기록이 완료 상태라고 안내한다.",
            "expected_interrupts": [],
            "expected_data": {"changed": False},
        },
    },
    {
        "case_id": "unsupported_guide",
        "inputs": {"turns": ["오늘 날씨 알려줘"]},
        "reference": {
            "answer_criteria": "은행 업무 밖의 요청이며 지원 가능한 계좌·카드 업무를 안내한다.",
            "expected_interrupts": [],
            "expected_data": {"changed": False},
        },
    },

]
