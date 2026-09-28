# 이체 함수입니다. 즉시 이체, 조건부·나눠 이체, 예약 이체.

from datetime import datetime

import data_store
import logger
from functions.account import find_accounts, find_registered, get_account
from functions.common import parse_time


# ---------------------------------------------------------------- 입금 대상 (내 계좌 + 등록 계좌)
# 입금 대상 ID 는 두 종류입니다.
#   acc-001 : 내 계좌
#   reg-001 : 등록 계좌 (상대 계좌 주소록). 가상은행이면 그 계좌에 돈이 들어가고, 다른 은행이면 출금만 남깁니다.

def find_targets(owner_id, name):
    # 입금 대상을 이름으로 찾습니다. 내 계좌와 등록 계좌를 함께 봅니다. 0개 없음 / 1개 확정 / 2개 이상 고르게 합니다.
    # 등록 계좌는 내 계좌와 같은 칸(account_id, nickname, account_number)으로 맞춰서 후보 고르기를 그대로 씁니다.
    found = find_accounts(owner_id, name)
    for r in find_registered(owner_id, name):
        found.append({"account_id": r["registered_id"], "nickname": r["nickname"],
                      "account_number": "%s %s, 예금주 %s, 등록 계좌" % (r["bank_name"], r["account_number"], r["holder_name"])})
    return found


def get_target(data, to_id):
    # 입금 대상 ID 로 화면에 쓸 이름·설명과, 돈을 실제로 넣을 가상은행 계좌 ID(deposit_id)를 돌려줍니다.
    # 다른 은행 등록 계좌는 deposit_id 가 None 입니다. 등록 계좌를 지웠으면 None 을 돌려줍니다.
    for a in data["accounts"]:
        if a["account_id"] == to_id:
            return {"nickname": a["nickname"], "text": "%s (%s)" % (a["nickname"], a["account_number"]),
                    "deposit_id": to_id}
    for r in data["registered_accounts"]:
        if r["registered_id"] == to_id:
            return {"nickname": r["nickname"],
                    "text": "%s (%s %s, 예금주 %s)" % (r["nickname"], r["bank_name"], r["account_number"], r["holder_name"]),
                    "deposit_id": r["account_id"]}
    return None


def target_name(data, to_id):
    # 입금 대상의 이름만 돌려줍니다. 찾을 수 없으면 ID 를 그대로 씁니다.
    target = get_target(data, to_id)
    return target["nickname"] if target else to_id


def transfer(data, from_id, to_id, amount):
    # data 안에서 잔액을 옮기고 거래 내역을 출금 1건, 입금 1건 붙입니다. 파일에 저장하지는 않습니다.
    # 다른 은행 등록 계좌로 보내면 받는 쪽 잔액이 없으므로 출금 1건만 붙입니다.
    # 실행 직전에 잔액을 다시 봅니다. 승인한 뒤에 잔액이 줄었을 수 있기 때문입니다.
    # 진행할 수 없으면 사유를, 성공하면 None 을 돌려줍니다.
    accounts = {account["account_id"]: account for account in data["accounts"]}
    from_account = accounts[from_id]
    target = get_target(data, to_id)
    if not target:
        return "입금 계좌를 찾을 수 없습니다. (등록 계좌를 삭제했을 수 있습니다)"
    if from_account["balance"] < amount:
        return "잔액이 부족합니다. (%s 잔액 %s원)" % (from_account["nickname"], format(from_account["balance"], ","))

    from_account["balance"] -= amount
    moves = [(from_account, "withdrawal")]
    if target["deposit_id"]:
        to_account = accounts[target["deposit_id"]]
        to_account["balance"] += amount
        moves.append((to_account, "deposit"))

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for account, kind in moves:
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


def resolve_splits(owner_id, splits):
    # 나눠 이체의 입금 목록을 위 줄부터 봅니다. 한 줄이 모자라도 전체를 멈추지 않고, 그 줄만 되묻게 합니다.
    # 계좌를 찾은 줄에는 to_account 를 적어 둡니다. 되물은 뒤 다시 볼 때 또 찾지 않게 하려는 것입니다.
    # 계좌 이름을 먼저 전부 정하고, 그다음 빠진 금액을 봅니다.
    # (splits, 줄 번호, 후보, 사유) 를 돌려줍니다.
    #   이름이 애매한 줄 : (splits, 줄 번호, 후보 목록, None)  → 번호를 고르게 합니다
    #   금액이 빠진 줄   : (splits, 줄 번호, None, None)       → 금액을 묻습니다
    #   계좌가 없는 줄   : (splits, None, None, 사유)
    #   다 채워짐        : (splits, None, None, None)
    splits = [dict(split) for split in splits]      # State 의 목록을 직접 바꾸지 않게 복사합니다
    for index, split in enumerate(splits):
        if split.get("to_account"):
            continue
        found = find_targets(owner_id, split["to_name"])
        logger.get_logger().resolve(split["to_name"], len(found), found[0]["account_id"] if found else None)
        if not found:
            return splits, None, None, "'%s' 계좌를 찾을 수 없습니다." % split["to_name"]
        if len(found) > 1:
            return splits, index, found, None
        split["to_account"] = found[0]["account_id"]
        split["to_name"] = found[0]["nickname"]
    for index, split in enumerate(splits):
        if not split.get("amount"):
            return splits, index, None, None
    return splits, None, None, None


def build_targets(owner_id, from_account, to_account, to_name, amount, keep, splits):
    # 입금 목록(targets)을 만듭니다. 한 곳이면 1개, 나눠 이체면 여러 개입니다.
    # 조건부 이체면 이체액 = 잔액 - 남길 금액 으로 계산합니다.
    # 나눠 이체는 resolve_splits 로 줄마다 계좌·금액을 다 채운 뒤에 부릅니다.
    # (targets, 사유) 를 돌려줍니다. 아직 정보가 모자라면 (None, None) 입니다.
    if not from_account:
        return None, None

    if splits:
        return [{"to_account": s["to_account"], "to_name": s["to_name"], "amount": s["amount"]} for s in splits], None

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
    # 등록 계좌가 내 계좌를 가리킬 수도 있으므로, 돈이 실제로 들어갈 계좌(deposit_id)로 비교합니다.
    data = data_store.load()
    if any((get_target(data, target["to_account"]) or {}).get("deposit_id") == from_account for target in targets):
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


# ---------------------------------------------------------------- 예약 이체
# 상태 : 예약 → 완료 / 실패 / 취소. 목록에서 지우지 않고 상태만 바꿉니다 (나중에 결과를 물을 수 있게).


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
    data = data_store.load()
    pending = [s for s in get_schedules(owner_id) if s["status"] == "예약"]
    if not name:
        return pending
    return [s for s in pending
            if name in s["schedule_id"] or name in target_name(data, s["to_account"]) or name in s["scheduled_at"]]


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
            s["status"], nicknames[s["from_account"]], target_name(data, s["to_account"]), format(s["amount"], ","),
            parse_time(s["scheduled_at"]).strftime("%m월 %d일 %H:%M"), "  " + error if error else ""))
    if lines:
        try:
            data_store.save(data)
        except data_store.DataStoreError:
            return ["[예약 이체] 저장에 실패해 처리하지 못했습니다. 다음 입력 때 다시 확인합니다."]
    return lines
