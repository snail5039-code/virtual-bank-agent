# 계좌·카드 업무를 처리하는 Python 함수들입니다.
# 금액 같은 숫자는 여기서 낸 값을 그대로 씁니다. LLM 이 만들지 않습니다.

import data_store

# 로그인한 사용자입니다. 인증(3-5 단계)을 만들기 전까지는 고정해 둡니다.
CURRENT_USER = "user-001"


def get_accounts(owner_id):
    # 이 사용자의 계좌만 골라 돌려줍니다. 다른 사람 계좌는 빼야 합니다.
    data = data_store.load()
    return [account for account in data["accounts"] if account["owner_id"] == owner_id]
