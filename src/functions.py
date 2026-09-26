# 계좌·카드 업무를 처리하는 Python 함수들입니다.
# 금액 같은 숫자는 여기서 낸 값을 그대로 씁니다. LLM 이 만들지 않습니다.

from datetime import datetime

import data_store

# 로그인한 사용자입니다. 인증(3-5 단계)을 만들기 전까지는 고정해 둡니다.
CURRENT_USER = "user-001"


def get_accounts(owner_id):
    # 이 사용자의 계좌만 골라 돌려줍니다. 다른 사람 계좌는 빼야 합니다.
    data = data_store.load()
    return [account for account in data["accounts"] if account["owner_id"] == owner_id]


def find_accounts(owner_id, name):
    # 이름으로 계좌를 찾습니다. 별명이나 은행 이름에 들어 있으면 후보입니다.
    # 결과가 0개면 없음, 1개면 확정, 2개 이상이면 사용자에게 고르게 합니다.
    # "생활비 통장", "가상은행 계좌" 처럼 붙은 말은 떼고 찾습니다.
    name = name.replace("계좌", "").replace("통장", "").strip()
    if not name:
        return []
    return [account for account in get_accounts(owner_id)
            if name in account["nickname"] or name in account["bank_name"]]


def transfer(data, from_id, to_id, amount):
    # data 안에서 잔액을 옮기고 거래 내역을 출금 1건, 입금 1건 붙입니다. 파일에 저장하지는 않습니다.
    # 실행 직전에 잔액을 다시 봅니다. 승인한 뒤에 잔액이 줄었을 수 있기 때문입니다.
    # 진행할 수 없으면 사유를, 성공하면 None 을 돌려줍니다.
    accounts = {account["account_id"]: account for account in data["accounts"]}
    from_account, to_account = accounts[from_id], accounts[to_id]
    if from_account["balance"] < amount:
        return "잔액이 부족합니다. (%s 잔액 %s원)" % (from_account["nickname"], format(from_account["balance"], ","))

    from_account["balance"] -= amount
    to_account["balance"] += amount

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for account, kind in [(from_account, "withdrawal"), (to_account, "deposit")]:
        data["transactions"].append({
            "transaction_id": "tx-%03d" % (len(data["transactions"]) + 1),
            "owner_id": account["owner_id"],
            "account_id": account["account_id"],
            "type": kind,
            "amount": amount,
            "occurred_at": now,
            "card_id": None,
            "merchant": None,
        })
    return None


def get_account(owner_id, account_id):
    # ID 로 계좌 하나를 찾습니다. 없거나 다른 사람 계좌면 None 입니다.
    for account in get_accounts(owner_id):
        if account["account_id"] == account_id:
            return account
    return None
