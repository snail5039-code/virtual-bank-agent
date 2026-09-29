# 계좌 함수입니다. 계좌 조회, 거래 내역, 계좌 별명·용도 변경, 등록 계좌(상대 계좌 주소록).

from datetime import date

import data_store
from functions.common import next_id

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


def get_account(owner_id, account_id):
    # ID 로 계좌 하나를 찾습니다. 없거나 다른 사람 계좌면 None 입니다.
    for account in get_accounts(owner_id):
        if account["account_id"] == account_id:
            return account
    return None


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


# 고를 수 있는 은행과 은행 코드입니다. (계좌 만들기, 상대 계좌 등록, 카드 등록)
# 실제 은행처럼 보이게 실제 은행 이름과 표준 은행 코드를 씁니다. 가상은행은 처음 데이터가 쓰는 이 앱의 은행입니다.
# 실제 은행과 연결되지는 않습니다. 이름과 계좌번호 모양만 빌려 씁니다.
BANKS = {
    "가상은행": "001",
    "KB국민은행": "004",
    "신한은행": "088",
    "우리은행": "020",
    "하나은행": "081",
    "NH농협은행": "011",
    "IBK기업은행": "003",
    "SC제일은행": "023",
    "카카오뱅크": "090",
    "케이뱅크": "089",
    "토스뱅크": "092",
    "iM뱅크": "031",
    "부산은행": "032",
    "우체국": "071",
}


def match_bank(text):
    # 말한 은행 이름을 목록(BANKS)의 이름 하나로 맞춥니다. 못 맞추면 None.
    #   "신한은행" → 신한은행 (그대로),  "국민" / "kb" → KB국민은행 (한 곳에만 들어 있으면)
    # 두 곳 이상에 들어 있거나 없는 은행이면 None 이고, 그때는 에이전트가 목록을 보여주고 고르게 합니다.
    if not text:
        return None
    key = text.replace(" ", "").casefold()
    names = {name.casefold(): name for name in BANKS}
    if key in names:
        return names[key]
    short = key.replace("은행", "")
    if not short:
        return None
    found = [name for folded, name in names.items() if short in folded]
    return found[0] if len(found) == 1 else None


# 은행별 계좌번호 모양입니다. 예시의 "-" 로 나뉜 칸 길이가 규칙입니다. (예: 신한은행 3-3-6 = 12자리)
# 실제 은행은 계좌 종류·만든 때에 따라 모양이 여러 가지라, 은행마다 가장 흔한 모양 하나만 씁니다.
ACCOUNT_EXAMPLES = {
    "가상은행": "110-001-123456",
    "KB국민은행": "123456-01-123456",
    "신한은행": "110-123-456789",
    "우리은행": "1002-123-456789",
    "하나은행": "123-456789-12345",
    "NH농협은행": "302-1234-5678-91",
    "IBK기업은행": "123-456789-01-012",
    "SC제일은행": "123-45-678901",
    "카카오뱅크": "3333-01-1234567",
    "케이뱅크": "100-123-456789",
    "토스뱅크": "1000-1234-5678",
    "iM뱅크": "508-10-123456-7",
    "부산은행": "101-2345-6789-01",
    "우체국": "123456-01-123456",
}


def normalize_account_number(bank_name, text):
    # 적은 계좌번호를 그 은행 모양(예시와 같은 "-" 자리)으로 맞춥니다. 숫자만 적어도, "-" 를 넣어 적어도 됩니다.
    # 숫자 개수가 모양과 다르거나 숫자가 아닌 글자가 있으면 None. 목록에 없는 은행(예전 데이터)은 적은 그대로 둡니다.
    example = ACCOUNT_EXAMPLES.get(bank_name)
    if not example:
        return text
    digits = (text or "").replace("-", "").replace(" ", "")
    groups = [len(part) for part in example.split("-")]
    if not digits.isdigit() or len(digits) != sum(groups):
        return None
    parts, start = [], 0
    for size in groups:
        parts.append(digits[start:start + size])
        start += size
    return "-".join(parts)


def account_number_rule(bank_name):
    # 안내 문구. 예) "신한은행 계좌번호는 12자리예요. (예: 110-123-456789)"
    example = ACCOUNT_EXAMPLES[bank_name]
    return "%s 계좌번호는 %d자리예요. (예: %s)" % (bank_name, len(example.replace("-", "")), example)


REGISTER_FIELDS = {"bank_name": "은행", "account_number": "계좌번호", "holder_name": "예금주 이름"}


def register_missing(info):
    # 등록에 꼭 필요한데 아직 모르는 칸의 이름을 돌려줍니다. 예) ["계좌번호", "예금주 이름"]. 다 있으면 빈 목록입니다.
    return [label for key, label in REGISTER_FIELDS.items() if not info.get(key)]


def check_register(owner_id, info):
    # 계좌를 등록할 수 있는지 봅니다. 안 되면 사유를, 되면 None 을 돌려줍니다.
    if register_missing(info):
        return "등록하려면 은행, 계좌번호, 예금주 이름이 필요합니다. (예: 신한은행 110-123-456789 이영희 계좌 등록해줘)"
    if not normalize_account_number(info["bank_name"], info["account_number"]):
        return account_number_rule(info["bank_name"])
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
    data["registered_accounts"].append({
        "registered_id": next_id(data["registered_accounts"], "registered_id", "reg"),
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
