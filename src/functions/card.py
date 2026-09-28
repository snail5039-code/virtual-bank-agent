# 카드 함수입니다. 카드 조회·찾기, 상태 바꾸기(분실·잠금·해지), 별칭·비밀번호, 카드 등록, 이용 내역, 멤버십.

import re
from datetime import date, datetime

import data_store
from functions.account import MAX_SETTING_LEN, get_transactions

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
    # 카드 이름은 정확히 같은 카드를 먼저 봅니다. "생활비 카드" → 생활비 카드 1장 (생활비 신용카드, 구 생활비 카드는 빠짐)
    # 정확히 같은 카드가 없을 때만 글자가 들어 있는 카드를 모두 찾습니다. "생활비" → 3장
    cards = get_cards(owner_id)
    if bank_name:
        bank_name = bank_name.replace(" ", "")
        cards = [c for c in cards if bank_name in c["bank_name"].replace(" ", "")]
    if card_name:
        exact = [c for c in cards if c["name"].replace(" ", "") == card_name.replace(" ", "")]
        card_name = card_name.replace("카드", "").strip()
        cards = exact or [c for c in cards if card_name in c["name"]]
    if card_type:
        cards = [c for c in cards if CARD_TYPES[c["card_type"]] == card_type]
    if status:
        cards = [c for c in cards if CARD_STATUS[c["status"]] == status]
    return cards


# 카드 상태를 바꾸는 할 일과, 바꾼 뒤의 상태입니다. 분실·도난·부정사용은 모두 lost 이고 사유만 따로 남깁니다.
# 해지는 목록에서 지우지 않고 cancelled 로 둡니다. 지우면 그 카드의 이용 내역이 참조를 잃습니다. (기획서 5.3)
CARD_ACTIONS = {"분실 신고": "lost", "일시 잠금": "locked", "잠금 해제": "active", "해지": "cancelled"}


def pick_cards(owner_id, name):
    # 설정·재발급·결제할 카드를 이름으로 찾습니다. 정확히 같은 이름을 먼저 보는 것은 find_cards 와 같습니다.
    # 여러 장이면 노드가 후보를 보여주고 번호로 고르게 합니다 (common_pick_card).
    return find_cards(owner_id, card_name=name)


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
