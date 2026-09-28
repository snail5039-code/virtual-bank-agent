# 계좌·카드 업무를 처리하는 Python 함수들입니다.
# 금액 같은 숫자는 여기서 낸 값을 그대로 씁니다. LLM 이 만들지 않습니다.
#
# 계산 로직은 전부 이 파일로 뺍니다. (기획서 원칙 7)
#   노드(agents/*/nodes.py) : 흐름만 맡습니다. 여기 함수를 부르고 결과를 State 에 넣습니다.
#   이 파일                 : 계산만 맡습니다. 조회, 금액 계산, 검사, 데이터 변경.
#   data_store.py           : 파일 읽기·쓰기만 맡습니다.
# 노드 안에 계산이 길어지면 여기로 옮깁니다.

import re
from datetime import date, datetime, timedelta

import data_store
import logger

# 로그인한 사용자입니다. 인증(3-5 단계)을 만들기 전까지는 고정해 둡니다.
CURRENT_USER = "user-001"

def base_date():
    # 기준일. "오늘", "이번 주", "이번 달" 을 이 날짜로 계산합니다.
    # 부를 때마다 오늘 날짜를 돌려줍니다. 상수로 두면 켜 둔 채 자정을 넘겼을 때 "오늘" 이 어제로 남습니다.
    return date.today()

TYPES = {"입금": "deposit", "출금": "withdrawal"}


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


def authenticate(owner_id, value):
    # 본인 확인. 계좌 비밀번호 / PIN / 휴대전화번호 / 주민번호 뒷자리 중 하나가 맞으면 True 입니다.
    data = data_store.load()
    user = next(u for u in data["users"] if u["owner_id"] == owner_id)
    value = value.replace("-", "").strip()
    answers = {user["pin"], user["phone"].replace("-", ""), user["ssn_tail"]}
    answers |= {a["account_password"] for a in data["accounts"] if a["owner_id"] == owner_id}
    return value in answers


# 카드 상태와 종류를 화면에 보여줄 한국어로 바꾸는 표입니다.
CARD_STATUS = {"active": "사용 가능", "locked": "일시 잠금", "lost": "분실 정지", "cancelled": "해지"}
CARD_TYPES = {"debit": "체크", "credit": "신용"}


def get_cards(owner_id):
    data = data_store.load()
    return [card for card in data["cards"] if card["owner_id"] == owner_id]


def find_cards(owner_id, bank_name=None, card_name=None, card_type=None, status=None):
    # 조건으로 카드를 거릅니다. 비어 있는(None) 조건은 거르지 않습니다.
    # card_type 은 체크 / 신용, status 는 사용 가능 / 일시 잠금 / 분실 정지 / 해지 (한국어로 받습니다)
    # "가상 은행", "여행 카드" 처럼 띄어 쓰거나 붙은 말이 있어도 찾도록 공백과 "카드" 를 떼고 비교합니다.
    cards = get_cards(owner_id)
    if bank_name:
        bank_name = bank_name.replace(" ", "")
        cards = [c for c in cards if bank_name in c["bank_name"].replace(" ", "")]
    if card_name:
        card_name = card_name.replace("카드", "").strip()
        cards = [c for c in cards if card_name in c["name"]]
    if card_type:
        cards = [c for c in cards if CARD_TYPES[c["card_type"]] == card_type]
    if status:
        cards = [c for c in cards if CARD_STATUS[c["status"]] == status]
    return cards


# 카드 상태를 바꾸는 할 일과, 바꾼 뒤의 상태입니다. 분실·도난·부정사용은 모두 lost 이고 사유만 따로 남깁니다.
# 해지는 목록에서 지우지 않고 cancelled 로 둡니다. 지우면 그 카드의 이용 내역이 참조를 잃습니다. (기획서 5.3)
CARD_ACTIONS = {"분실 신고": "lost", "일시 잠금": "locked", "잠금 해제": "active", "해지": "cancelled"}


def pick_cards(owner_id, name):
    # 상태를 바꿀 카드를 이름으로 찾습니다. 한 장으로 정해야 하므로 이름이 정확히 같은 카드를 먼저 봅니다.
    # "생활비 카드" → 생활비 카드 1장 (생활비 신용카드, 구 생활비 카드는 빠짐)
    # 정확히 같은 카드가 없으면 글자가 들어 있는 카드를 모두 돌려줍니다. (여러 장이면 노드가 후보를 보여줍니다)
    exact = [c for c in get_cards(owner_id) if c["name"].replace(" ", "") == name.replace(" ", "")]
    return exact or find_cards(owner_id, card_name=name)


def check_card_status(card, action):
    # 지금 상태에서 이 할 일을 할 수 있는지 봅니다. (기획서 5.3 전이 불가 목록)
    # 할 수 없으면 사유를, 할 수 있으면 None 을 돌려줍니다.
    # 별칭·비밀번호 변경은 상태를 바꾸지 않으므로 해지된 카드만 막습니다.
    status = card["status"]
    if status == "cancelled":
        return "해지된 카드는 바꿀 수 없습니다. (%s)" % card["name"]
    if action not in CARD_ACTIONS:
        return None
    if status == "lost" and action in ("일시 잠금", "잠금 해제"):
        return "분실 정지된 카드는 잠그거나 해제할 수 없습니다. 재발급을 신청해 주세요. (%s)" % card["name"]
    if status == CARD_ACTIONS[action]:
        return "이미 %s 상태인 카드입니다. (%s)" % (CARD_STATUS[status], card["name"])
    return None


def check_card_alias(owner_id, card, value):
    # 카드 별칭(name)을 바꿀 수 있는지 봅니다. 계좌 별명(check_setting)과 같은 규칙입니다.
    value = (value or "").strip()
    if not 1 <= len(value) <= MAX_SETTING_LEN:
        return "새 별칭은 1~%d자로 정해 주세요." % MAX_SETTING_LEN
    if card["name"] == value:
        return "바뀌는 것이 없습니다. (지금 별칭 : %s)" % value
    for other in get_cards(owner_id):
        if other["card_id"] != card["card_id"] and other["name"] == value:
            return "다른 카드가 이미 '%s' 별칭을 쓰고 있습니다." % value
    return None


def check_card_password(card, value):
    # 새 카드 비밀번호를 쓸 수 있는지 봅니다. 숫자 4자리이고 지금 비밀번호와 달라야 합니다.
    if not (len(value) == 4 and value.isdigit()):
        return "카드 비밀번호는 숫자 4자리여야 합니다."
    if card["card_password"] == value:
        return "지금 비밀번호와 같습니다. 다른 번호로 정해 주세요."
    return None


def set_card_value(data, card_id, key, value):
    # data 안에서 카드 한 칸(name 별칭 / card_password 비밀번호)을 바꿉니다. 파일에 저장하지는 않습니다.
    card = next(c for c in data["cards"] if c["card_id"] == card_id)
    card[key] = value.strip()


def check_card_register(owner_id, info):
    # 카드를 등록할 수 있는지 봅니다. 안 되면 사유를, 되면 None 을 돌려줍니다. (계좌 등록 check_register 와 같은 방식)
    # info : {bank_name, card_number, card_type(체크/신용), account_id(결제 계좌), name}
    if not info.get("bank_name") or not info.get("card_number") or not info.get("card_type") or not info.get("account_id"):
        return ("등록하려면 은행, 카드 번호, 체크/신용, 결제 계좌가 필요합니다.\n"
                "(예: 미래은행 체크카드 1234-5678-1234-5678 생활비 계좌로 등록해줘)")
    if not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{4}", info["card_number"]):
        return "카드 번호는 16자리 숫자입니다. (예: 1234-5678-1234-5678)"
    if not 1 <= len(info["name"]) <= MAX_SETTING_LEN:
        return "별칭은 1~%d자로 정해 주세요." % MAX_SETTING_LEN
    # 카드 번호는 사용자와 상관없이 겹치면 안 됩니다. 별칭은 내 카드끼리만 겹치지 않으면 됩니다.
    for card in data_store.load()["cards"]:
        if card["card_number"] == info["card_number"]:
            return "이미 등록된 카드 번호입니다."
        if card["owner_id"] == owner_id and card["name"] == info["name"]:
            return "다른 카드가 이미 '%s' 별칭을 쓰고 있습니다." % info["name"]
    return None


def normalize_card_number(text):
    # "1234567812345678", "1234 5678 1234 5678" 을 "1234-5678-1234-5678" 로 맞춥니다. 16자리가 아니면 그대로 둡니다.
    digits = re.sub(r"\D", "", text or "")
    if len(digits) != 16:
        return text
    return "-".join(digits[i:i + 4] for i in range(0, 16, 4))


def register_card(data, owner_id, info):
    # data 에 카드를 한 장 덧붙입니다. 파일에 저장하지는 않습니다.
    # 한도·비밀번호는 모르므로 비워 둡니다. 비밀번호는 비밀번호 변경으로 정합니다.
    numbers = [int(c["card_id"].split("-")[1]) for c in data["cards"]]
    card_id = "card-%03d" % (max(numbers, default=0) + 1)
    data["cards"].append({
        "card_id": card_id,
        "owner_id": owner_id,
        "name": info["name"],
        "account_id": info["account_id"],
        "status": "active",
        "card_number": info["card_number"],
        "card_type": "credit" if info["card_type"] == "신용" else "debit",
        "bank_code": None,
        "bank_name": info["bank_name"],
        "card_password": None,
        "credit_limit": None,
        "report_reason": None,
        "reported_at": None,
    })
    return card_id


def change_card_status(data, card_id, action, reason=None):
    # data 안에서 카드 상태를 바꿉니다. 파일에 저장하지는 않습니다 (저장은 common_save).
    # 분실 신고면 사유와 신고 시각도 남깁니다.
    card = next(c for c in data["cards"] if c["card_id"] == card_id)
    card["status"] = CARD_ACTIONS[action]
    if action == "분실 신고":
        card["report_reason"] = reason or "분실"
        card["reported_at"] = datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- 카드 청구서 (요금)
# 청구서는 신용카드에만 있습니다. 체크카드는 쓰는 즉시 계좌에서 빠지므로 낼 돈이 따로 없습니다.
# 남은 금액 = 청구 총액 - 낸 금액 (데이터에 remaining_amount 로 들어 있습니다)
STATEMENT_STATUS = {"unpaid": "미납", "partial": "일부 납부", "paid": "납부 완료"}


def get_statements(owner_id, card_ids=None, month=None):
    # 청구서를 거릅니다. card_ids 를 주면 그 카드만, month("2026-08")를 주면 그 달만 봅니다. 최근 달부터 돌려줍니다.
    result = [s for s in data_store.load()["card_statements"] if s["owner_id"] == owner_id
              and (not card_ids or s["card_id"] in card_ids)
              and (not month or s["billing_month"] == month)]
    return sorted(result, key=lambda s: (s["billing_month"], s["card_id"]), reverse=True)


def get_statement_items(owner_id, statement):
    # 청구서 한 건의 상세 내역. items 에는 이용 내역 ID 만 있으므로 card_usages 에서 찾아 붙입니다. 날짜순입니다.
    usages = {u["usage_id"]: u for u in data_store.load()["card_usages"] if u["owner_id"] == owner_id}
    items = [usages[usage_id] for usage_id in statement["items"] if usage_id in usages]
    return sorted(items, key=lambda u: u["occurred_at"])


def check_payment(owner_id, statement, account_id, amount):
    # 카드값을 낼 수 있는지 봅니다. 안 되면 사유를, 되면 None 을 돌려줍니다.
    # 전체 결제는 "남은 금액 전부를 내는 부분 결제" 라서 같은 검사를 씁니다.
    if statement["remaining_amount"] <= 0:
        return "이미 납부 완료된 청구서입니다. (%s)" % statement["billing_month"]
    if amount <= 0:
        return "결제 금액은 1원 이상이어야 합니다."
    if amount > statement["remaining_amount"]:
        return "남은 금액(%s원)보다 많이 낼 수 없습니다." % format(statement["remaining_amount"], ",")
    account = get_account(owner_id, account_id)
    if account["balance"] < amount:
        return "잔액이 부족합니다. (%s 잔액 %s원)" % (account["nickname"], format(account["balance"], ","))
    return None


def pay_statement(data, statement_id, account_id, amount, memo):
    # data 안에서 카드값을 냅니다. 파일에 저장하지는 않습니다 (저장은 common_save).
    #   1) 계좌 잔액에서 뺍니다
    #   2) 청구서의 낸 금액·남은 금액을 바꾸고, 남은 금액이 0 이면 납부 완료, 남아 있으면 일부 납부로 둡니다
    #   3) 계좌 거래 내역에 출금 한 줄을 남깁니다 (카드 이용이 아니므로 card_id 는 비웁니다)
    # 세 가지를 한 번에 저장하므로, 저장이 실패하면 셋 다 반영되지 않습니다. (기획서 5.2 전체·부분 = 전부 롤백)
    account = next(a for a in data["accounts"] if a["account_id"] == account_id)
    statement = next(s for s in data["card_statements"] if s["statement_id"] == statement_id)
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    account["balance"] -= amount
    statement["paid_amount"] += amount
    statement["remaining_amount"] -= amount
    statement["status"] = "paid" if statement["remaining_amount"] == 0 else "partial"
    statement["paid_at"] = now
    statement["paid_account"] = account_id
    data["transactions"].append({
        "transaction_id": "tx-%03d" % (len(data["transactions"]) + 1),
        "owner_id": account["owner_id"],
        "account_id": account_id,
        "type": "withdrawal",
        "amount": amount,
        "occurred_at": now,
        "card_id": None,
        "merchant": memo,
    })


# ---------------------------------------------------------------- 재발급
# 신청 상태 : 접수 → 제작중 → 배송중. 취소하면 취소됨. 실제 제작·배송 진행은 만들지 않습니다. (기획서 5.4)
REISSUE_STATUS = {"received": "접수", "making": "제작중", "shipping": "배송중", "cancelled": "취소됨"}


def get_addresses(owner_id):
    return [a for a in data_store.load()["addresses"] if a["owner_id"] == owner_id]


def find_addresses(owner_id, name):
    # 배송지를 이름(집 / 회사)이나 주소 글자로 찾습니다. "집으로" 처럼 붙은 말이 있어도 찾게 이름이 들어 있는지 봅니다.
    name = (name or "").strip()
    if not name:
        return []
    return [a for a in get_addresses(owner_id) if a["label"] in name or name in a["address"]]


def get_applications(owner_id):
    # 재발급 신청 목록. 최근순입니다.
    apps = [a for a in data_store.load()["reissue_applications"] if a["owner_id"] == owner_id]
    return sorted(apps, key=lambda a: a["created_at"], reverse=True)


def check_reissue(owner_id, card):
    # 재발급을 신청할 수 있는지 봅니다. 안 되면 사유를, 되면 None 을 돌려줍니다.
    if card["status"] != "lost":
        return "분실 정지된 카드만 재발급을 신청할 수 있습니다. 먼저 분실 신고를 해 주세요. (%s : %s)" % (
            card["name"], CARD_STATUS[card["status"]])
    # 취소되지 않은 신청이 있으면 새로 만들지 않고 그 신청을 안내합니다.
    for app in get_applications(owner_id):
        if app["card_id"] == card["card_id"] and app["status"] != "cancelled":
            return "이미 재발급 신청이 있습니다. (%s  %s  [%s])" % (
                app["application_id"], card["name"], REISSUE_STATUS[app["status"]])
    return None


def find_open_application(owner_id, card_id):
    # 이 카드의 취소되지 않은 신청을 돌려줍니다. 카드마다 하나만 있을 수 있으므로(check_reissue) 하나이거나 None 입니다.
    return next((a for a in get_applications(owner_id)
                 if a["card_id"] == card_id and a["status"] != "cancelled"), None)


def check_application(app, action, address_id=None):
    # 신청을 수정·취소할 수 있는지 봅니다. 접수 상태일 때만 됩니다. (기획서 5.4 표)
    # 할 수 없으면 사유를, 할 수 있으면 None 을 돌려줍니다.
    if app["status"] != "received":
        return "%s 상태라 %s할 수 없습니다. 접수 상태일 때만 됩니다. (%s)" % (
            REISSUE_STATUS[app["status"]], "배송지를 수정" if action == "배송지 수정" else "취소", app["application_id"])
    if action == "배송지 수정" and app["address_id"] == address_id:
        return "지금 배송지와 같습니다. (%s)" % app["application_id"]
    return None


def change_application(data, app_id, action, address_id=None):
    # data 안에서 신청의 배송지를 바꾸거나 취소합니다. 취소도 지우지 않고 상태만 바꿉니다. 파일에 저장하지는 않습니다.
    app = next(a for a in data["reissue_applications"] if a["application_id"] == app_id)
    if action == "배송지 수정":
        app["address_id"] = address_id
    else:
        app["status"] = "cancelled"


def add_reissue(data, owner_id, card_id, address_id):
    # data 에 재발급 신청을 한 줄 덧붙입니다. 파일에 저장하지는 않습니다.
    # 기존 카드의 분실 정지는 그대로 둡니다. (기획서 5.4)
    numbers = [int(a["application_id"].split("-")[1]) for a in data["reissue_applications"]]
    app_id = "app-%03d" % (max(numbers, default=0) + 1)
    data["reissue_applications"].append({
        "application_id": app_id,
        "owner_id": owner_id,
        "card_id": card_id,
        "address_id": address_id,
        "status": "received",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    })
    return app_id


def get_card_history(owner_id, card_ids, start=None, end=None):
    # 카드 이용 내역. 두 곳을 합칩니다. (기획서 8장)
    #   체크카드 : transactions 에 출금으로 남아 있으므로 거래내역 함수에 카드 필터만 줘서 재사용합니다
    #   신용카드 : card_usages 에 따로 있습니다
    # 둘 다 {card_id, amount, occurred_at, merchant} 가 있어서 그대로 합쳐 최근순으로 돌려줍니다.
    result = get_transactions(owner_id, start=start, end=end, card_ids=card_ids)
    for usage in data_store.load()["card_usages"]:
        day = date.fromisoformat(usage["occurred_at"][:10])
        if usage["owner_id"] != owner_id or usage["card_id"] not in card_ids:
            continue
        if (start and day < start) or (end and day > end):
            continue
        result.append(usage)
    return sorted(result, key=lambda item: item["occurred_at"], reverse=True)


def get_memberships(owner_id, card_ids):
    # 이 카드들에 붙은 멤버십을 돌려줍니다.
    return [m for m in data_store.load()["memberships"]
            if m["owner_id"] == owner_id and m["card_id"] in card_ids]


def period_range(period):
    # 기간 이름을 (시작일, 종료일) 로 바꿉니다. 둘 다 포함입니다. 전체면 (None, None).
    today = base_date()
    if period == "오늘":
        return today, today
    if period == "어제":
        day = today - timedelta(days=1)
        return day, day
    if period in ("이번 주", "지난 주"):   # 월요일 ~ 일요일
        start = today - timedelta(days=today.weekday())
        if period == "지난 주":
            start -= timedelta(days=7)
        return start, start + timedelta(days=6)
    if period == "이번 달":
        start = today.replace(day=1)
    elif period == "지난 달":
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    else:
        return None, None
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month - timedelta(days=1)


def get_transactions(owner_id, account_ids=None, start=None, end=None,
                     kind=None, min_amount=None, max_amount=None, card_ids=None):
    # 조건을 조합해 거래 내역을 거릅니다. 비워 둔 조건은 보지 않습니다. 최근순으로 돌려줍니다.
    # kind : 입금 / 출금 / 결제 (결제 = 카드를 써서 나간 거래)
    # card_ids : 이 카드로 결제한 거래만 봅니다 (카드 이용 내역에서 씁니다)
    result = []
    for tx in data_store.load()["transactions"]:
        day = date.fromisoformat(tx["occurred_at"][:10])
        if tx["owner_id"] != owner_id:
            continue
        if account_ids and tx["account_id"] not in account_ids:
            continue
        if (start and day < start) or (end and day > end):
            continue
        if kind == "결제" and not tx["card_id"]:
            continue
        if card_ids and tx["card_id"] not in card_ids:
            continue
        if kind in TYPES and tx["type"] != TYPES[kind]:
            continue
        if (min_amount and tx["amount"] < min_amount) or (max_amount and tx["amount"] > max_amount):
            continue
        result.append(tx)
    return sorted(result, key=lambda tx: tx["occurred_at"], reverse=True)


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


def build_targets(owner_id, from_account, to_account, to_name, amount, keep, splits):
    # 입금 목록(targets)을 만듭니다. 한 곳이면 1개, 나눠 이체면 여러 개입니다.
    # 조건부 이체면 이체액 = 잔액 - 남길 금액 으로 계산합니다.
    # (targets, 사유) 를 돌려줍니다. 아직 정보가 모자라면 (None, None) 입니다.
    if not from_account:
        return None, None

    if splits:
        targets = []
        for split in splits:
            found = find_accounts(owner_id, split["to_name"])
            logger.get_logger().resolve(split["to_name"], len(found), found[0]["account_id"] if found else None)
            if len(found) != 1:
                return None, "'%s' 계좌를 하나로 정할 수 없습니다. 정확한 이름으로 다시 요청해 주세요." % split["to_name"]
            targets.append({"to_account": found[0]["account_id"], "to_name": found[0]["nickname"],
                            "amount": split["amount"] or 0})
        return targets, None

    if keep is not None:
        amount = get_account(owner_id, from_account)["balance"] - keep
    if to_account and amount is not None:
        return [{"to_account": to_account, "to_name": to_name, "amount": amount}], None
    return None, None


def check_transfer(owner_id, from_account, targets, keep):
    # [분기 2] 실행할 수 있는지 봅니다. 안 되면 사유를, 되면 None 을 돌려줍니다.
    balance = get_account(owner_id, from_account)["balance"]
    total = sum(target["amount"] for target in targets)
    if keep is not None and keep < 0:
        return "남길 금액은 0원 이상이어야 합니다."
    if keep is not None and total <= 0:
        return "잔액이 %s원이라 %s원을 남기면 보낼 금액이 없습니다." % (format(balance, ","), format(keep, ","))
    if any(target["amount"] <= 0 for target in targets):
        return "이체 금액은 0원보다 커야 합니다."
    if any(target["to_account"] == from_account for target in targets):
        return "출금 계좌와 입금 계좌가 같습니다."
    if balance < total:
        return "잔액이 부족합니다. (잔액 %s원 / 보낼 금액 %s원)" % (format(balance, ","), format(total, ","))
    return None


def transfer_all(data, from_id, targets, keep):
    # 승인된 목록을 data 안에서 한꺼번에 이체합니다. 파일에 저장하지는 않습니다.
    # 실행 직전에 다시 봅니다. 승인한 뒤에 잔액이 바뀌었을 수 있기 때문입니다.
    # 진행할 수 없으면 사유를, 성공하면 None 을 돌려줍니다.
    balance = next(a["balance"] for a in data["accounts"] if a["account_id"] == from_id)
    total = sum(target["amount"] for target in targets)

    # 조건부 이체 : 잔액이 바뀌면 이체액도 바뀝니다. 그러면 실행하지 않고 다시 요청하게 합니다.
    if keep is not None and balance - keep != total:
        return "잔액이 바뀌어 이체할 금액이 달라졌습니다. 다시 요청해 주세요."
    # 반복하기 전에 총액을 먼저 봅니다. 하나씩 보내다 중간에 멈추지 않게 합니다.
    if balance < total:
        return "잔액이 부족합니다. (잔액 %s원 / 보낼 금액 %s원)" % (format(balance, ","), format(total, ","))

    for target in targets:
        error = transfer(data, from_id, target["to_account"], target["amount"])
        if error:
            return error
    return None


SETTING_FIELDS = {"별명": "nickname", "용도": "purpose"}
MAX_SETTING_LEN = 20


def check_setting(owner_id, account_id, field, value):
    # 계좌 별명·용도를 바꿀 수 있는지 봅니다. 안 되면 사유를, 되면 None 을 돌려줍니다.
    # 별명은 같은 사용자의 다른 계좌와 겹치면 안 됩니다. 용도는 겹쳐도 됩니다.
    value = value.strip()
    account = get_account(owner_id, account_id)
    if not 1 <= len(value) <= MAX_SETTING_LEN:
        return "새 %s: 1~%d자로 정해 주세요." % (field, MAX_SETTING_LEN)
    if account[SETTING_FIELDS[field]] == value:
        return "바뀌는 것이 없습니다. (지금 %s : %s)" % (field, value)
    if field == "별명":
        for other in get_accounts(owner_id):
            if other["account_id"] != account_id and other["nickname"] == value:
                return "다른 계좌가 이미 '%s' 별명을 쓰고 있습니다." % value
    return None


def change_setting(data, account_id, field, value):
    # data 안에서 계좌 별명·용도를 바꿉니다. 파일에 저장하지는 않습니다.
    account = next(a for a in data["accounts"] if a["account_id"] == account_id)
    account[SETTING_FIELDS[field]] = value.strip()


def get_registered(owner_id):
    # 등록 계좌(돈을 보낼 상대 계좌 주소록)를 돌려줍니다. 잔액은 없습니다.
    data = data_store.load()
    return [r for r in data["registered_accounts"] if r["owner_id"] == owner_id]


def find_registered(owner_id, name):
    # 별명이나 예금주 이름으로 등록 계좌를 찾습니다. 0개 없음 / 1개 확정 / 2개 이상 고르게 합니다.
    name = name.replace("계좌", "").strip()
    return [r for r in get_registered(owner_id) if name and (name in r["nickname"] or name in r["holder_name"])]


def check_register(owner_id, info):
    # 계좌를 등록할 수 있는지 봅니다. 안 되면 사유를, 되면 None 을 돌려줍니다.
    if not info.get("bank_name") or not info.get("account_number") or not info.get("holder_name"):
        return "등록하려면 은행, 계좌번호, 예금주 이름이 필요합니다. (예: 미래은행 210-11-223344 이영희 계좌 등록해줘)"
    if not 1 <= len(info["nickname"].strip()) <= MAX_SETTING_LEN:
        return "별명은 1~%d자로 정해 주세요." % MAX_SETTING_LEN
    for r in get_registered(owner_id):
        if r["account_number"] == info["account_number"]:
            return "이미 등록한 계좌입니다. (%s)" % r["nickname"]
    return None


def register_account(data, owner_id, info):
    # data 에 등록 계좌를 한 줄 덧붙입니다. 파일에 저장하지는 않습니다.
    # 가상은행 계좌면 그 계좌 ID 를 이어 둡니다. 다른 은행이면 None 입니다.
    linked = next((a["account_id"] for a in data["accounts"]
                   if a["bank_name"] == info["bank_name"] and a["account_number"] == info["account_number"]), None)
    numbers = [int(r["registered_id"].split("-")[1]) for r in data["registered_accounts"]]
    data["registered_accounts"].append({
        "registered_id": "reg-%03d" % (max(numbers, default=0) + 1),
        "owner_id": owner_id,
        "bank_name": info["bank_name"],
        "account_number": info["account_number"],
        "holder_name": info["holder_name"],
        "nickname": info["nickname"].strip(),
        "account_id": linked,
    })


def delete_registered(data, registered_id):
    # data 에서 등록 계좌를 뺍니다. 파일에 저장하지는 않습니다.
    data["registered_accounts"] = [r for r in data["registered_accounts"] if r["registered_id"] != registered_id]


# ---------------------------------------------------------------- 예약 이체
# 상태 : 예약 → 완료 / 실패 / 취소. 목록에서 지우지 않고 상태만 바꿉니다 (나중에 결과를 물을 수 있게).

def parse_time(text):
    # "2026-09-27T09:00" 같은 문자열을 시각으로 바꿉니다. 시간대가 없으면 이 컴퓨터 시간대로 봅니다.
    return datetime.fromisoformat(text).astimezone()


def check_schedule(scheduled_at, targets, keep):
    # 예약할 수 있는지 봅니다. 안 되면 사유를, 되면 None 을 돌려줍니다.
    if keep is not None or len(targets) != 1:
        return "예약은 금액을 정한 한 곳 이체만 됩니다. (예: 내일 9시에 생활비에서 저축으로 10만원 보내줘)"
    if parse_time(scheduled_at) <= datetime.now().astimezone():
        return "예약 시각이 이미 지났습니다. (%s)" % parse_time(scheduled_at).strftime("%m월 %d일 %H:%M")
    return None


def add_schedule(data, owner_id, from_id, target, scheduled_at):
    # data 에 예약을 한 줄 덧붙입니다. 돈은 옮기지 않습니다. 파일에 저장하지는 않습니다.
    numbers = [int(s["schedule_id"].split("-")[1]) for s in data["scheduled_transfers"]]
    data["scheduled_transfers"].append({
        "schedule_id": "sch-%03d" % (max(numbers, default=0) + 1),
        "owner_id": owner_id,
        "from_account": from_id,
        "to_account": target["to_account"],
        "amount": target["amount"],
        "scheduled_at": parse_time(scheduled_at).isoformat(timespec="seconds"),
        "status": "예약",
    })


def get_schedules(owner_id):
    data = data_store.load()
    return [s for s in data["scheduled_transfers"] if s["owner_id"] == owner_id]


def find_schedules(owner_id, name):
    # 취소할 예약을 찾습니다. 아직 실행 전(예약)인 것만 봅니다.
    # 예약 번호(sch-001), 입금 계좌 이름, 날짜(09-27) 중 하나가 맞으면 후보입니다.
    nicknames = {a["account_id"]: a["nickname"] for a in get_accounts(owner_id)}
    pending = [s for s in get_schedules(owner_id) if s["status"] == "예약"]
    if not name:
        return pending
    return [s for s in pending
            if name in s["schedule_id"] or name in nicknames.get(s["to_account"], "") or name in s["scheduled_at"]]


def cancel_schedule(data, schedule_id):
    # data 안에서 예약을 취소 상태로 바꿉니다. 파일에 저장하지는 않습니다.
    schedule = next(s for s in data["scheduled_transfers"] if s["schedule_id"] == schedule_id)
    schedule["status"] = "취소"


def run_due_schedules():
    # 시각이 지난 예약을 이체합니다. main.py 가 켤 때와 입력을 받을 때마다 부릅니다.
    # 승인은 예약할 때 받았으므로 다시 묻지 않습니다. 잔액이 모자라면 이체하지 않고 실패로 남깁니다.
    # 처리한 결과를 한 줄씩 돌려줍니다. 처리할 게 없으면 빈 목록입니다.
    data = data_store.load()
    now = datetime.now().astimezone()
    nicknames = {a["account_id"]: a["nickname"] for a in data["accounts"]}
    lines = []
    for s in data["scheduled_transfers"]:
        if s["status"] != "예약" or parse_time(s["scheduled_at"]) > now:
            continue
        error = transfer(data, s["from_account"], s["to_account"], s["amount"])
        s["status"] = "실패" if error else "완료"
        lines.append("[예약 이체 %s] %s → %s  %s원  (%s)%s" % (
            s["status"], nicknames[s["from_account"]], nicknames[s["to_account"]], format(s["amount"], ","),
            parse_time(s["scheduled_at"]).strftime("%m월 %d일 %H:%M"), "  " + error if error else ""))
    if lines:
        try:
            data_store.save(data)
        except data_store.DataStoreError:
            return ["[예약 이체] 저장에 실패해 처리하지 못했습니다. 다음 입력 때 다시 확인합니다."]
    return lines


def get_account(owner_id, account_id):
    # ID 로 계좌 하나를 찾습니다. 없거나 다른 사람 계좌면 None 입니다.
    for account in get_accounts(owner_id):
        if account["account_id"] == account_id:
            return account
    return None
