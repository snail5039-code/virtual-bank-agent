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


ACTIONS = {
    "card_lock": card_status_action("일시 잠금"),
    "card_unlock": card_status_action("잠금 해제"),
}
