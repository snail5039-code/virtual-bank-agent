# 모든 에이전트가 같이 쓰는 State 입니다.
# 계좌·이체 에이전트는 supervisor 그래프 안의 노드로 들어가므로 같은 State 를 씁니다.
#
# checkpointer 가 thread_id 별로 State 를 저장하므로, 턴이 바뀌어도 값이 남아 있습니다.
# 그래서 새 요청을 시작할 때는 new_request() 로 이번 업무 칸을 비웁니다.
# last_transfer 는 비우지 않습니다. "아까 그 계좌" 를 찾을 때 쓰는 맥락이기 때문입니다.

from typing import TypedDict


class BankState(TypedDict):
    query: str              # 사용자 입력 (질문에 답하면 그 답으로 바뀝니다)
    domain: str             # 1단 supervisor 가 고른 분야  (계좌 / 카드 / 없음)
    reason: str             # 그렇게 고른 이유
    task: str               # 2단 에이전트가 고른 업무    (조회 / 이체 / 설정)
    answer: str             # 사용자에게 보여줄 응답

    # 이체에 필요한 정보
    from_name: str          # 사용자가 말한 출금 계좌 이름
    to_name: str            # 사용자가 말한 입금 계좌 이름
    from_account: str       # 찾아낸 출금 계좌 ID
    to_account: str         # 찾아낸 입금 계좌 ID
    amount: int             # 이체 금액
    candidates: list        # 이름에 맞는 계좌가 여러 개일 때 후보 목록
    confirm_for: str        # 후보를 고르는 칸 (from / to)
    question: str           # 방금 사용자에게 한 질문 (짧은 답이 어느 칸인지 알려고)
    error: str              # 더 진행할 수 없을 때 사유

    # 맥락 (새 요청에도 남겨 둡니다)
    last_transfer: str      # 직전 이체. 예) "출금=생활비, 입금=저축"


def new_request(query):
    # 새 요청의 시작값입니다. 지난 업무의 값이 섞이지 않게 비웁니다.
    return {
        "query": query,
        "domain": None, "reason": None, "task": None, "answer": None,
        "from_name": None, "to_name": None,
        "from_account": None, "to_account": None, "amount": None,
        "candidates": None, "confirm_for": None, "question": None, "error": None,
    }
