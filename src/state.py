# 모든 에이전트가 같이 쓰는 State 입니다.
# 계좌 에이전트는 supervisor 그래프 안의 노드로 들어가므로 같은 State 를 씁니다.

from typing import TypedDict


class BankState(TypedDict):
    query: str          # 사용자 입력
    domain: str         # 1단 supervisor 가 고른 분야  (계좌 / 카드 / 없음)
    reason: str         # 그렇게 고른 이유
    task: str           # 2단 에이전트가 고른 업무    (조회 / 이체 / 설정)
    answer: str         # 사용자에게 보여줄 응답
