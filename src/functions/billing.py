# 카드 요금 함수입니다. 청구서 조회, 전체·부분·분할 결제.

from datetime import datetime, timedelta

import data_store
from functions.account import get_account
from functions.common import add_month, add_request, add_transaction, next_id, parse_time

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
    # 분할 중인 청구서는 남은 금액을 한 번에 다 낼 때(중도 상환)만 받습니다.
    # 일부만 내면 남은 금액은 줄지만 분할 계획의 회차 금액은 그대로라 둘이 맞지 않게 됩니다.
    if amount < statement["remaining_amount"]:
        for i in data_store.load()["card_installments"]:
            if i["statement_id"] == statement["statement_id"] and i["status"] == "active":
                return ("분할 결제 중인 청구서입니다. (%s  %d/%d회)\n"
                        "남은 금액 %s원을 한 번에 다 낼 때만 결제할 수 있습니다." % (
                            i["installment_id"], i["paid_count"], i["months"], format(statement["remaining_amount"], ",")))
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
    if statement["remaining_amount"] == 0:
        # 분할 중인 청구서를 다 냈으면(중도 상환) 그 분할 계획도 끝냅니다.
        for i in data["card_installments"]:
            if i["statement_id"] == statement_id and i["status"] == "active":
                i["status"] = "paid"
    statement["paid_at"] = now
    statement["paid_account"] = account_id
    add_transaction(data, account, "withdrawal", amount, now, memo)


INSTALLMENT_MONTHS = (2, 12)     # 분할(할부) 개월 수 범위


def check_installment(owner_id, statement, months):
    # 분할 결제를 걸 수 있는지 봅니다. 안 되면 사유를, 되면 None 을 돌려줍니다.
    low, high = INSTALLMENT_MONTHS
    if not months or not low <= months <= high:
        return "분할 개월 수는 %d~%d개월로 정해 주세요. (예: 9월 생활비 신용카드 값 3개월로 나눠 내줘)" % (low, high)
    for i in data_store.load()["card_installments"]:
        if i["statement_id"] == statement["statement_id"] and i["status"] == "active":
            return "이미 분할 결제 중인 청구서입니다. (%s  %d/%d회)" % (i["installment_id"], i["paid_count"], i["months"])
    return None


def installment_amounts(total, months):
    # 분할 금액. 나누어떨어지지 않는 나머지는 첫 회차에 붙입니다. 예) 452,000원 3개월 → [150,668, 150,666, 150,666]
    base = total // months
    return [total - base * (months - 1)] + [base] * (months - 1)


def add_installment(data, statement_id, months):
    # data 에 분할 계획을 한 줄 넣습니다. 첫 회차는 지금 내므로 낸 회차를 1로 둡니다. (첫 회차 결제는 pay_statement 가 합니다)
    # 남은 회차는 next_due_at(다음 납부일, 한 달 뒤)이 되면 pay_due_installments 가 냅니다.
    statement = next(s for s in data["card_statements"] if s["statement_id"] == statement_id)
    amounts = installment_amounts(statement["remaining_amount"], months)
    installment_id = next_id(data["card_installments"], "installment_id", "inst")
    data["card_installments"].append({
        "installment_id": installment_id,
        "statement_id": statement_id,
        "card_id": statement["card_id"],
        "total_amount": statement["remaining_amount"],
        "months": months,
        "paid_count": 1,
        "monthly_amount": amounts[1],
        "next_due_at": add_month(datetime.now().astimezone()).isoformat(timespec="seconds"),
        "status": "active",
    })
    return installment_id


def pay_due_installments(data, now):
    # 분할 계획 중 다음 납부일이 지난 회차를 냅니다. 예약 이체(run_due_schedules)와 같은 방식이고, 거기서 같이 부릅니다.
    # data 안에서만 바꾸고 파일에 저장하지는 않습니다 (run_due_schedules 가 한 번에 저장합니다).
    # 승인은 분할을 걸 때 받았으므로 다시 묻지 않습니다. 첫 회차를 낸 계좌(paid_account)에서 냅니다.
    #   낼 수 있으면 : 낸 회차 +1, 다음 납부일을 한 달 뒤로. 마지막 회차면 pay_statement 가 분할을 끝냅니다 (남은 금액 0)
    #   잔액이 모자라면 : 내지 않고 실패로 기록하고, 다음 납부일을 하루 뒤로 미뤄 다시 시도합니다
    #                    (미루지 않으면 입력할 때마다 같은 실패가 반복해서 뜹니다)
    # 처리한 결과를 한 줄씩 돌려줍니다.
    cards = {c["card_id"]: c["name"] for c in data["cards"]}
    lines = []
    for i in data["card_installments"]:
        if i["status"] != "active" or not i.get("next_due_at") or parse_time(i["next_due_at"]) > now:
            continue
        statement = next(s for s in data["card_statements"] if s["statement_id"] == i["statement_id"])
        account = next(a for a in data["accounts"] if a["account_id"] == statement["paid_account"])
        # 이번 회차 금액. 마지막 회차는 남은 금액을 그대로 냅니다 (나누고 남은 원 단위 차이를 맞추려고).
        number = i["paid_count"] + 1
        amount = i["monthly_amount"] if number < i["months"] else statement["remaining_amount"]
        amount = min(amount, statement["remaining_amount"])
        name = "%s %s분 분할 %d/%d회" % (cards.get(i["card_id"], i["card_id"]), statement["billing_month"], number, i["months"])

        if account["balance"] < amount:
            status = "실패"
            reason = "잔액이 부족합니다. (%s 잔액 %s원)" % (account["nickname"], format(account["balance"], ","))
            i["next_due_at"] = (now + timedelta(days=1)).isoformat(timespec="seconds")
            lines.append("[분할 회차 실패] %s  %s원  %s 내일 다시 시도합니다." % (name, format(amount, ","), reason))
        else:
            status = "완료"
            reason = None
            pay_statement(data, statement["statement_id"], account["account_id"], amount, "카드값 " + name)
            i["paid_count"] = number
            i["next_due_at"] = add_month(parse_time(i["next_due_at"])).isoformat(timespec="seconds")
            lines.append("[분할 회차 완료] %s  %s원  (%s)%s" % (
                name, format(amount, ","), account["nickname"], "  분할 끝" if i["status"] == "paid" else ""))

        content = {"분할": i["installment_id"], "청구서": name, "금액": format(amount, ",") + "원",
                   "결제 계좌": account["nickname"]}
        if reason:
            content["실패 사유"] = reason
        add_request(data, statement["owner_id"], "분할 회차 결제", content, status, now)
    return lines
