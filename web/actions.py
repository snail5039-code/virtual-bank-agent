# 메뉴 화면의 버튼으로 바로 하는 업무입니다. LLM 을 거치지 않습니다.
# src/ 는 바꾸지 않고, 에이전트 노드가 쓰는 functions 의 검사·실행 함수를 그대로 부릅니다.
# 처리안 모양, 끝났을 때의 안내 문구, 처리 기록 모양도 에이전트(카드 설정 노드 등)와 같게 맞춥니다.
#
# 업무 하나는 두 함수입니다.
#   preview(data, target) : 검사하고 처리안을 만듭니다. 안 되면 (사유, None), 되면 (None, 처리안)
#   apply(data, target)   : data 안에서 바꾸고 안내 문구를 돌려줍니다. 저장은 server.py 가 합니다.
# 실행 직전에 preview 를 한 번 더 불러 다시 검사합니다 (처리안을 본 사이에 상태가 바뀌었을 수 있어서).

import functions

ME = functions.CURRENT_USER


def my_card(data, card_id):
    card = next((c for c in data["cards"] if c["card_id"] == card_id and c["owner_id"] == ME), None)
    return card


def card_row(card):
    # 에이전트 카드 설정 처리안의 첫 줄과 같은 모양입니다.
    return ["카드", "%s (%s)" % (card["name"], card["card_number"])]


# ---------------------------------------------------------------- 카드 일시 잠금 / 잠금 해제
def card_status_action(action):
    # action : "일시 잠금" / "잠금 해제" (functions.CARD_ACTIONS 의 이름)
    def preview(data, card_id):
        card = my_card(data, card_id)
        if not card:
            return "카드를 찾지 못했습니다.", None
        error = functions.check_card_status(card, action)
        if error:
            return error, None
        rows = [
            card_row(card),
            ["지금 상태", functions.CARD_STATUS[card["status"]]],
            ["바뀔 상태", functions.CARD_STATUS[functions.CARD_ACTIONS[action]]],
        ]
        if action == "일시 잠금":
            rows.append(["주의", "잠금을 풀기 전까지 이 카드는 사용할 수 없습니다"])
        return None, {"task": "카드 " + action, "rows": rows}

    def apply(data, card_id):
        card = my_card(data, card_id)
        old = functions.CARD_STATUS[card["status"]]
        functions.change_card_status(data, card_id, action)
        return "카드 %s 완료 : %s  %s → %s" % (action, card["name"], old, functions.CARD_STATUS[card["status"]])

    return {"preview": preview, "apply": apply}


# ---------------------------------------------------------------- 카드값 전체 결제
# 남은 금액 전부를 그 카드의 결제 계좌에서 냅니다. (에이전트에서 방식·계좌를 말하지 않았을 때와 같음)
# 부분·분할·일괄은 금액·개월 수·대상을 골라야 해서 에이전트로 합니다.
def bill_target(data, statement_id):
    statement = next((s for s in data["card_statements"]
                      if s["statement_id"] == statement_id and s["owner_id"] == ME), None)
    if not statement:
        return None, None, None
    card = next(c for c in data["cards"] if c["card_id"] == statement["card_id"])
    account = next(a for a in data["accounts"] if a["account_id"] == card["account_id"])
    return statement, card, account


def bill_preview(data, statement_id):
    statement, card, account = bill_target(data, statement_id)
    if not statement:
        return "청구서를 찾지 못했습니다.", None
    amount = statement["remaining_amount"]
    error = functions.check_payment(ME, statement, account["account_id"], amount)
    if error:
        return error, None
    # 에이전트 billing_propose 의 전체 결제 처리안과 같은 모양입니다.
    rows = [
        ["청구서", "%s %s분 (기한 %s)" % (card["name"], statement["billing_month"], statement["due_date"])],
        ["방식", "전체 결제"],
        ["낼 금액", "%s원" % format(amount, ",")],
        ["남은 금액", "%s원 → 0원" % format(amount, ",")],
        ["결제 계좌", "%s (%s)  잔액 %s원 → %s원" % (
            account["nickname"], account["account_number"],
            format(account["balance"], ","), format(account["balance"] - amount, ","))],
    ]
    return None, {"task": "카드값 전체 결제", "rows": rows}


def bill_apply(data, statement_id):
    # 에이전트 pay_one(전체) 과 같습니다. 잔액 출금, 청구서 납부 처리, 거래 내역 한 줄.
    statement, card, account = bill_target(data, statement_id)
    amount = statement["remaining_amount"]
    memo = "카드값 %s %s분" % (card["name"], statement["billing_month"])
    functions.pay_statement(data, statement_id, account["account_id"], amount, memo)
    return "카드값을 냈습니다.\n%s  %s원  → 남은 금액 %s원 [%s]" % (
        memo, format(amount, ","), format(statement["remaining_amount"], ","),
        functions.STATEMENT_STATUS[statement["status"]])


ACTIONS = {
    "card_lock": card_status_action("일시 잠금"),
    "card_unlock": card_status_action("잠금 해제"),
    "bill_pay": {"preview": bill_preview, "apply": bill_apply},
}
