# 계좌·카드 업무를 처리하는 Python 함수들입니다.
# 금액 같은 숫자는 여기서 낸 값을 그대로 씁니다. LLM 이 만들지 않습니다.
#
# 계산 로직은 전부 이 파일로 뺍니다. (기획서 원칙 7)
#   노드(agents/*/nodes.py) : 흐름만 맡습니다. 여기 함수를 부르고 결과를 State 에 넣습니다.
#   이 파일                 : 계산만 맡습니다. 조회, 금액 계산, 검사, 데이터 변경.
#   data_store.py           : 파일 읽기·쓰기만 맡습니다.
# 노드 안에 계산이 길어지면 여기로 옮깁니다.

from datetime import date, datetime, timedelta

import data_store
import logger

# 로그인한 사용자입니다. 인증(3-5 단계)을 만들기 전까지는 고정해 둡니다.
CURRENT_USER = "user-001"

# 기준일. "오늘", "이번 주", "이번 달" 을 이 날짜로 계산합니다. 프로그램을 켠 날짜입니다.
BASE_DATE = date.today()

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


def get_cards(owner_id):
    data = data_store.load()
    return [card for card in data["cards"] if card["owner_id"] == owner_id]


def period_range(period):
    # 기간 이름을 (시작일, 종료일) 로 바꿉니다. 둘 다 포함입니다. 전체면 (None, None).
    if period == "오늘":
        return BASE_DATE, BASE_DATE
    if period == "어제":
        day = BASE_DATE - timedelta(days=1)
        return day, day
    if period in ("이번 주", "지난 주"):   # 월요일 ~ 일요일
        start = BASE_DATE - timedelta(days=BASE_DATE.weekday())
        if period == "지난 주":
            start -= timedelta(days=7)
        return start, start + timedelta(days=6)
    if period == "이번 달":
        start = BASE_DATE.replace(day=1)
    elif period == "지난 달":
        start = (BASE_DATE.replace(day=1) - timedelta(days=1)).replace(day=1)
    else:
        return None, None
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month - timedelta(days=1)


def get_transactions(owner_id, account_ids=None, start=None, end=None,
                     kind=None, min_amount=None, max_amount=None):
    # 조건을 조합해 거래 내역을 거릅니다. 비워 둔 조건은 보지 않습니다. 최근순으로 돌려줍니다.
    # kind : 입금 / 출금 / 결제 (결제 = 카드를 써서 나간 거래)
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
    try:
        parse_time(scheduled_at)
    except ValueError:
        return "예약 시각을 알아듣지 못했습니다. (예: 내일 오전 9시에)"
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
