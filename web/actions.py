# 메뉴 화면의 버튼으로 바로 하는 업무입니다. LLM 을 거치지 않습니다.
# 에이전트 노드가 쓰는 functions(web/bank/functions) 의 검사·실행 함수를 그대로 부릅니다.
# 처리안 모양, 끝났을 때의 안내 문구, 처리 기록 모양도 에이전트(카드 설정 노드 등)와 같게 맞춥니다.
#
# 업무 하나는 두 함수입니다.
#   preview(data, target, params) : 검사하고 처리안을 만듭니다. 안 되면 (사유, None), 되면 (None, 처리안)
#   apply(data, target, params)   : data 안에서 바꾸고 안내 문구를 돌려줍니다. 저장은 server.py 가 합니다.
#   target 은 대상 ID, params 는 이체처럼 화면에서 입력받는 값입니다 (없으면 빈 dict).
# 실행 직전에 preview 를 한 번 더 불러 다시 검사합니다 (처리안을 본 사이에 상태가 바뀌었을 수 있어서).

import functions

ME = functions.CURRENT_USER


def my_card(data, card_id):
    card = next((c for c in data["cards"] if c["card_id"] == card_id and c["owner_id"] == ME), None)
    return card


def card_row(card):
    # 에이전트 카드 설정 처리안의 첫 줄과 같은 모양입니다.
    return ["카드", "%s (%s)" % (card["name"], card["card_number"])]


# ---------------------------------------------------------------- 카드 일시 잠금 / 잠금 해제 / 해지
def card_status_action(action):
    # action : "일시 잠금" / "잠금 해제" / "해지" (functions.CARD_ACTIONS 의 이름)
    def preview(data, card_id, params):
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
        # 주의 문구는 에이전트 card_setting_propose 와 같습니다.
        if action == "일시 잠금":
            rows.append(["주의", "잠금을 풀기 전까지 이 카드는 사용할 수 없습니다"])
        if action == "해지":
            rows.append(["주의", "해지하면 되돌릴 수 없습니다"])
        return None, {"task": "카드 " + action, "rows": rows}

    def apply(data, card_id, params):
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


def bill_preview(data, statement_id, params):
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


def bill_apply(data, statement_id, params):
    # 에이전트 pay_one(전체) 과 같습니다. 잔액 출금, 청구서 납부 처리, 거래 내역 한 줄.
    statement, card, account = bill_target(data, statement_id)
    amount = statement["remaining_amount"]
    memo = "카드값 %s %s분" % (card["name"], statement["billing_month"])
    functions.pay_statement(data, statement_id, account["account_id"], amount, memo)
    return "카드값을 냈습니다.\n%s  %s원  → 남은 금액 %s원 [%s]" % (
        memo, format(amount, ","), format(statement["remaining_amount"], ","),
        functions.STATEMENT_STATUS[statement["status"]])


# ---------------------------------------------------------------- 예약 이체 취소
# 아직 실행 전(예약)인 것만 취소합니다. (functions.find_schedules 가 고르는 기준과 같음)
def my_schedule(data, schedule_id):
    return next((s for s in data["scheduled_transfers"]
                 if s["schedule_id"] == schedule_id and s["owner_id"] == ME), None)


def schedule_preview(data, schedule_id, params):
    s = my_schedule(data, schedule_id)
    if not s:
        return "예약을 찾지 못했습니다.", None
    if s["status"] != "예약":
        return "이미 %s된 예약이라 취소할 수 없습니다. (%s)" % (s["status"], schedule_id), None
    # 에이전트 계좌 설정의 예약 취소 처리안(schedule_text)과 같은 한 줄입니다.
    line = "%s  %s  %s → %s  %s원  [%s]" % (
        s["schedule_id"], functions.when_text(s["scheduled_at"]),
        functions.target_name(data, s["from_account"]), functions.target_name(data, s["to_account"]),
        format(s["amount"], ","), s["status"])
    return None, {"task": "예약 이체 취소", "rows": [["예약", line]]}


def schedule_apply(data, schedule_id, params):
    functions.cancel_schedule(data, schedule_id)
    return "예약 이체를 취소했습니다. (%s)" % schedule_id


# ---------------------------------------------------------------- 이체 / 예약 이체
# 한 곳, 금액을 정한 이체만 합니다. 예약 시각을 넣으면 예약 이체입니다. (에이전트 예약 규칙과 같음)
# 조건부("40만원 남기고")·나눠 이체는 에이전트로 합니다.
#   params : {"from": 출금 계좌 ID, "to": 입금 계좌 ID(내 계좌 acc- / 등록 계좌 reg-), "amount": 금액, "at": 예약 시각 또는 ""}
def transfer_input(data, params):
    # 화면에서 받은 값을 확인하고 (출금 계좌, 입금 목록, 예약 시각) 을 만듭니다. 안 되면 사유를 돌려줍니다.
    from_account = next((a for a in data["accounts"]
                         if a["account_id"] == params.get("from") and a["owner_id"] == ME), None)
    if not from_account:
        return "출금 계좌를 골라 주세요.", None
    to_id = params.get("to")
    mine = any(a["account_id"] == to_id and a["owner_id"] == ME for a in data["accounts"])
    registered = any(r["registered_id"] == to_id and r["owner_id"] == ME for r in data["registered_accounts"])
    if not (mine or registered):
        return "입금 계좌를 골라 주세요.", None
    try:
        amount = int(str(params.get("amount") or "").replace(",", ""))
    except ValueError:
        return "금액은 숫자로 입력해 주세요.", None
    targets = [{"to_account": to_id, "to_name": functions.target_name(data, to_id), "amount": amount}]
    return None, (from_account, targets, params.get("at") or None)


def transfer_preview(data, target, params):
    error, parsed = transfer_input(data, params)
    if error:
        return error, None
    from_account, targets, at = parsed
    # 검사는 에이전트 transfer_check 와 같은 함수입니다. (금액 0 이하, 같은 계좌, 잔액 부족 / 예약 시각)
    error = functions.check_transfer(ME, from_account["account_id"], targets, None)
    if not error and at:
        error = functions.check_schedule(at, targets, None)
    if error:
        return error, None
    # 처리안은 에이전트 transfer_propose 와 같은 모양입니다.
    t = targets[0]
    rows = [
        ["출금", "%s (%s)" % (from_account["nickname"], from_account["account_number"])],
        ["입금", "%s  %s원" % (functions.get_target(data, t["to_account"])["text"], format(t["amount"], ","))],
        ["총액", format(t["amount"], ",") + "원"],
        ["출금 후 잔액", format(from_account["balance"] - t["amount"], ",") + "원"],
    ]
    proposal = {"task": "이체", "rows": rows}
    if at:
        proposal["task"] = "예약 이체"
        rows.insert(0, ["예약 시각", functions.parse_time(at).strftime("%Y-%m-%d %H:%M")])
    return None, proposal


def transfer_apply(data, target, params):
    # 에이전트 transfer_execute 와 같습니다. 예약이면 돈은 옮기지 않고 예약만 남깁니다.
    _, (from_account, targets, at) = transfer_input(data, params)
    t = targets[0]
    if at:
        functions.add_schedule(data, ME, from_account["account_id"], t, at)
        return "%s → %s  %s원\n%s 에 이체하도록 예약했습니다." % (
            from_account["nickname"], t["to_name"], format(t["amount"], ","), functions.when_text(at))
    error = functions.transfer_all(data, from_account["account_id"], targets, None)
    if error:
        raise ValueError("이체하지 않았습니다. " + error)     # server.py 가 저장하지 않고 사유를 보여줍니다
    balance = next(a["balance"] for a in data["accounts"] if a["account_id"] == from_account["account_id"])
    return "%s → %s  %s원\n이체했습니다. %s 잔액 %s원" % (
        from_account["nickname"], t["to_name"], format(t["amount"], ","), from_account["nickname"], format(balance, ","))


# ---------------------------------------------------------------- 카드 재발급 신청
# 분실 정지된 카드만, 취소되지 않은 신청이 없을 때만 됩니다. (functions.check_reissue)
#   params : {"address": 배송지 ID (집 / 회사)}
def my_address(data, address_id):
    return next((a for a in data["addresses"] if a["address_id"] == address_id and a["owner_id"] == ME), None)


def reissue_preview(data, card_id, params):
    card = my_card(data, card_id)
    if not card:
        return "카드를 찾지 못했습니다.", None
    error = functions.check_reissue(ME, card)
    if error:
        return error, None
    address = my_address(data, params.get("address"))
    if not address:
        return "배송지를 골라 주세요.", None
    # 에이전트 reissue_propose 의 신청 처리안과 같은 모양입니다.
    rows = [
        card_row(card),
        ["지금 상태", functions.CARD_STATUS[card["status"]]],
        ["배송지", "%s (%s)" % (address["label"], address["address"])],
        ["안내", "신청해도 기존 카드의 분실 정지는 그대로입니다"],
    ]
    return None, {"task": "카드 재발급 신청", "rows": rows}


def reissue_apply(data, card_id, params):
    app_id = functions.add_reissue(data, ME, card_id, params["address"])
    return "재발급을 신청했습니다. (%s  [접수])" % app_id


# ---------------------------------------------------------------- 상대 계좌 등록
# 돈을 보낼 상대 계좌를 주소록처럼 등록합니다. 별명을 안 쓰면 예금주 이름으로 붙입니다. (에이전트와 같음)
#   params : {"bank_name", "account_number", "holder_name", "nickname"(선택)}
def account_reg_info(params):
    info = {key: (params.get(key) or "").strip() for key in ["bank_name", "account_number", "holder_name", "nickname"]}
    info["nickname"] = info["nickname"] or info["holder_name"]
    return info


def account_register_preview(data, target, params):
    info = account_reg_info(params)
    error = functions.check_register(ME, info)
    if error:
        return error, None
    # 에이전트 setting_propose 의 등록 처리안과 같은 모양입니다.
    rows = [["은행", info["bank_name"]], ["계좌번호", info["account_number"]],
            ["예금주", info["holder_name"]], ["별명", info["nickname"]]]
    return None, {"task": "계좌 등록", "rows": rows}


def account_register_apply(data, target, params):
    info = account_reg_info(params)
    functions.register_account(data, ME, info)
    return "계좌를 등록했습니다. (%s)" % info["nickname"]


# ---------------------------------------------------------------- 카드 등록
# 다른 은행 카드 등을 등록합니다. 별칭을 안 쓰면 "은행 이름 + 체크/신용카드" 로 붙입니다. (에이전트와 같음)
#   params : {"bank_name", "card_number", "card_type"(체크 / 신용), "account_id"(결제 계좌), "name"(선택)}
def card_reg_info(params):
    info = {key: (params.get(key) or "").strip() for key in ["bank_name", "card_number", "card_type", "account_id", "name"]}
    info["card_number"] = functions.normalize_card_number(info["card_number"])   # 숫자 16자리 → 1234-5678-…
    info["name"] = info["name"] or "%s %s카드" % (info["bank_name"], info["card_type"])
    return info


def card_register_preview(data, target, params):
    info = card_reg_info(params)
    if info["account_id"] and not any(a["account_id"] == info["account_id"] and a["owner_id"] == ME
                                      for a in data["accounts"]):
        return "결제 계좌를 골라 주세요.", None
    error = functions.check_card_register(ME, info)
    if error:
        return error, None
    account = next(a for a in data["accounts"] if a["account_id"] == info["account_id"])
    # 에이전트 card_setting_propose 의 등록 처리안과 같은 모양입니다.
    rows = [["은행", info["bank_name"]], ["카드 번호", info["card_number"]], ["종류", info["card_type"]],
            ["결제 계좌", "%s (%s)" % (account["nickname"], account["account_number"])], ["별칭", info["name"]]]
    return None, {"task": "카드 등록", "rows": rows}


def card_register_apply(data, target, params):
    info = card_reg_info(params)
    functions.register_card(data, ME, info)
    return "카드를 등록했습니다. (%s)\n카드 비밀번호는 '비밀번호 변경' 으로 정해 주세요." % info["name"]


# ---------------------------------------------------------------- 등록 계좌 삭제
def my_registered(data, registered_id):
    return next((r for r in data["registered_accounts"]
                 if r["registered_id"] == registered_id and r["owner_id"] == ME), None)


def registered_delete_preview(data, registered_id, params):
    r = my_registered(data, registered_id)
    if not r:
        return "등록 계좌를 찾지 못했습니다.", None
    # 에이전트 setting_propose 의 삭제 처리안과 같은 모양입니다.
    rows = [["별명", r["nickname"]],
            ["계좌", "%s %s (예금주 %s)" % (r["bank_name"], r["account_number"], r["holder_name"])]]
    return None, {"task": "등록 계좌 삭제", "rows": rows}


def registered_delete_apply(data, registered_id, params):
    nickname = my_registered(data, registered_id)["nickname"]
    functions.delete_registered(data, registered_id)
    return "등록 계좌를 삭제했습니다. (%s)" % nickname


# ---------------------------------------------------------------- 내 계좌 새로 만들기 (웹에만 있는 기능)
# functions 에는 계좌를 새로 만드는 함수가 없어서 여기서 만듭니다. (에이전트는 별명·용도 변경까지만 합니다)
# 규칙은 기존 것과 맞춥니다.
#   별명   : 앞뒤 공백을 뗀 1~20자, 내 다른 계좌와 겹치면 안 됨 (functions.check_setting 과 같은 기준)
#   비밀번호 : 숫자 4자리, 평문이 아니라 해시로 저장 (functions.hash_secret). 처리안·처리 기록에는 **** 로만
#   계좌번호 : 가상은행 계좌 중 가장 큰 번호 + 1 (예: 110-001-100005 까지 있으면 110-001-100006), 잔액 0원
#   params : {"nickname", "purpose"(선택), "password"}
BANK_CODE, BANK_NAME = "001", "가상은행"


def new_account_number(data):
    numbers = [int(a["account_number"].split("-")[-1]) for a in data["accounts"] if a["bank_code"] == BANK_CODE]
    return "110-001-%06d" % (max(numbers, default=100000) + 1)


def account_open_info(params):
    return {key: (params.get(key) or "").strip() for key in ["nickname", "purpose", "password"]}


def account_open_preview(data, target, params):
    info = account_open_info(params)
    if not 1 <= len(info["nickname"]) <= functions.MAX_SETTING_LEN:
        return "별명은 1~%d자로 정해 주세요." % functions.MAX_SETTING_LEN, None
    if any(a["owner_id"] == ME and a["nickname"] == info["nickname"] for a in data["accounts"]):
        return "다른 계좌가 이미 '%s' 별명을 쓰고 있습니다." % info["nickname"], None
    if len(info["purpose"]) > functions.MAX_SETTING_LEN:
        return "용도는 %d자까지 쓸 수 있습니다." % functions.MAX_SETTING_LEN, None
    if not (len(info["password"]) == 4 and info["password"].isdigit()):
        return "계좌 비밀번호는 숫자 4자리여야 합니다.", None
    rows = [["은행", BANK_NAME], ["계좌번호", new_account_number(data)], ["별명", info["nickname"]],
            ["용도", info["purpose"] or "-"], ["비밀번호", "****"], ["잔액", "0원으로 시작합니다"]]
    return None, {"task": "계좌 만들기", "rows": rows}


def account_open_apply(data, target, params):
    info = account_open_info(params)
    number = new_account_number(data)
    data["accounts"].append({
        "account_id": functions.next_id(data["accounts"], "account_id", "acc"),
        "owner_id": ME,
        "nickname": info["nickname"],
        "purpose": info["purpose"] or None,
        "balance": 0,
        "bank_code": BANK_CODE,
        "bank_name": BANK_NAME,
        "account_number": number,
        "account_password": functions.hash_secret(info["password"]),
    })
    return "계좌를 만들었습니다. (%s  %s %s)" % (info["nickname"], BANK_NAME, number)


ACTIONS = {
    "account_open": {"preview": account_open_preview, "apply": account_open_apply},
    "registered_delete": {"preview": registered_delete_preview, "apply": registered_delete_apply},
    "card_cancel": card_status_action("해지"),
    "account_register": {"preview": account_register_preview, "apply": account_register_apply},
    "card_register": {"preview": card_register_preview, "apply": card_register_apply},
    "reissue": {"preview": reissue_preview, "apply": reissue_apply},
    "card_lock": card_status_action("일시 잠금"),
    "card_unlock": card_status_action("잠금 해제"),
    "bill_pay": {"preview": bill_preview, "apply": bill_apply},
    "schedule_cancel": {"preview": schedule_preview, "apply": schedule_apply},
    "transfer": {"preview": transfer_preview, "apply": transfer_apply},
}
