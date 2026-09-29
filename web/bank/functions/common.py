# 여러 업무가 같이 쓰는 함수입니다. 로그인한 사용자, 기준일, 본인 확인, 기간·시각 계산.

import calendar
import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta
from typing import Literal

import data_store

# 기본 사용자입니다. 웹은 로그인한 사람을 State 의 owner_id 로 넘기고, 이 값은 owner_id 가 없을 때(터미널 main)만 씁니다.
# (본인 확인은 authenticate 가 따로 합니다)
CURRENT_USER = "user-001"


def base_date():
    # 기준일. "오늘", "이번 주", "이번 달" 을 이 날짜로 계산합니다.
    # 부를 때마다 오늘 날짜를 돌려줍니다. 상수로 두면 켜 둔 채 자정을 넘겼을 때 "오늘" 이 어제로 남습니다.
    return date.today()


# ---------------------------------------------------------------- 비밀 값 해시
# 계좌 비밀번호 / PIN / 주민번호 뒷자리 / 카드 비밀번호는 data.json 에 평문이 아니라 해시로 둡니다.
# 저장할 때 hash_secret 으로 바꾸고, 확인할 때는 입력값을 같은 방법으로 해시해 비교합니다 (되돌릴 수 없음).
# 숫자 4자리는 해시만 하면 0000~9999 를 다 해시해 보면 금방 풀리므로,
#   salt : 값마다 다른 임의의 글자를 붙여 같은 비밀번호라도 해시가 다르게 나오게 하고
#   반복 : pbkdf2 로 10만 번 반복해 한 번 해 보는 데 시간이 걸리게 합니다.
# 저장 모양 : "salt$해시"   (Python 기본 라이브러리 hashlib 만 씁니다)
HASH_ROUNDS = 100_000


def hash_secret(value, salt=None):
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), salt.encode(), HASH_ROUNDS).hex()
    return "%s$%s" % (salt, digest)


def check_secret(value, stored):
    # 입력값(value)이 저장된 해시(stored)와 맞는지 봅니다. 저장된 값이 없으면(비밀번호를 정하지 않은 카드) False.
    if not stored:
        return False
    salt = stored.split("$")[0]
    return hmac.compare_digest(hash_secret(value, salt), stored)


def authenticate(owner_id, value):
    # 본인 확인. 계좌 비밀번호 / PIN / 휴대전화번호 / 주민번호 뒷자리 중 하나가 맞으면 True 입니다.
    # 휴대전화번호는 연락처라 평문으로 두고, 나머지는 해시로 비교합니다.
    data = data_store.load()
    user = next(u for u in data["users"] if u["owner_id"] == owner_id)
    value = value.replace("-", "").strip()
    # 웹의 간단 계정은 휴대전화번호·주민번호 뒷자리 없이 만들 수 있어서, 빈 값끼리 맞았다고 보지 않게 막습니다.
    phone = (user.get("phone") or "").replace("-", "")
    if value and phone and value == phone:
        return True
    hashes = [user["pin"], user.get("ssn_tail")]
    hashes += [a["account_password"] for a in data["accounts"] if a["owner_id"] == owner_id]
    return any(check_secret(value, stored) for stored in hashes)


# LLM 이 고르는 기간 이름입니다. 거래 내역·카드 이용 내역·결과 조회가 같이 씁니다.
Period = Literal["오늘", "어제", "이번 주", "지난 주", "이번 달", "지난 달", "전체"]


def date_range(period, start_date=None, end_date=None):
    # 조회할 (시작일, 종료일). 직접 말한 날짜가 있으면 그 날짜, 없으면 기간 이름으로 계산합니다.
    start, end = period_range(period)
    return start_date or start, end_date or end


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


def find_requests(owner_id, keyword=None, start=None, end=None, target=None):
    # 처리 기록(원장)을 최근순으로 돌려줍니다. 쓰기 업무가 끝날 때마다 common_log_request 가 한 줄씩 남깁니다.
    # "아까 이체 됐어?" 같은 후속 질문은 LLM 이 기억으로 답하지 않고 여기서 꺼낸 기록으로 답합니다. (원칙 6)
    # 조건을 조합해 거릅니다. 비워 둔 조건은 보지 않습니다. (거래 내역 get_transactions 와 같은 방식)
    #   keyword    : 업무 이름(task_type)에 그 글자가 든 기록.     예) "이체", "잠금", "결제", "재발급"
    #   start, end : 기록한 날짜가 그 기간 안인 기록 (둘 다 포함).  예) 어제 → (어제, 어제)
    #   target     : 기록 내용(content)에 그 이름이 든 기록.        예) "여행 카드", "저축"
    result = []
    for r in data_store.load()["requests"]:
        day = date.fromisoformat(r["created_at"][:10])
        if r["owner_id"] != owner_id:
            continue
        if keyword and keyword.replace(" ", "") not in r["task_type"].replace(" ", ""):
            continue
        if (start and day < start) or (end and day > end):
            continue
        if target and not any(target.replace(" ", "") in str(value).replace(" ", "") for value in r["content"].values()):
            continue
        result.append(r)
    # 같은 초에 여러 건이 남을 수 있으므로(예약 여러 건 실행, 일괄 결제) 시각이 같으면 나중 번호(request_id)가 앞입니다.
    return sorted(result, key=lambda r: (r["created_at"], r["request_id"]), reverse=True)


# ---------------------------------------------------------------- 진행 중 업무 (재시작 복구, 5-2)
# 승인·질문을 기다리며 멈춘 업무를 data.json 의 "pending" 에 사람마다 한 건씩 적어 둡니다. 예약 이체와 같은 방식입니다.
#   모양 : {"user-001": 기록, "user-002": 기록}   (웹 여러 사람용. 터미널 버전은 기록 하나였습니다)
# 켤 때 남아 있으면 main.py 가 알려주고, 다시 하겠다고 하면 원래 요청을 처음부터 다시 돌립니다.
# 이전 승인은 쓰지 않습니다. 꺼져 있는 동안 잔액·카드 상태가 바뀌었을 수 있기 때문입니다. (기획서 recovery)

def pending_records(data):
    # 사람별 기록을 {owner_id: 기록} 으로 돌려줍니다.
    # 예전 모양(기록 하나)이 남아 있으면 그때는 한 사람만 썼으므로 CURRENT_USER 것으로 봅니다.
    value = data.get("pending") or {}
    if "request_text" in value:
        return {CURRENT_USER: value}
    return dict(value)


def get_pending(owner_id):
    return pending_records(data_store.load()).get(owner_id)


def set_pending(owner_id, record):
    # record : {request_text(원래 요청 문장), task(업무 이름), kind(승인 / 질문 대기), created_at}
    data = data_store.load()
    records = pending_records(data)
    records[owner_id] = record
    data["pending"] = records
    data_store.save(data)


def drop_pending(data, owner_id):
    # data 안에서 그 사람 기록만 지웁니다. 지운 게 있으면 True. (저장은 부르는 쪽이 합니다)
    records = pending_records(data)
    found = records.pop(owner_id, None)
    data["pending"] = records or None
    return found is not None


def clear_pending(owner_id):
    data = data_store.load()
    if drop_pending(data, owner_id):
        data_store.save(data)


def add_month(when):
    # 한 달 뒤 같은 날·같은 시각. 그 달에 그날이 없으면(1월 31일 → 2월) 그 달 마지막 날로 맞춥니다.
    year, month = (when.year + 1, 1) if when.month == 12 else (when.year, when.month + 1)
    day = min(when.day, calendar.monthrange(year, month)[1])
    return when.replace(year=year, month=month, day=day)


def add_request(data, owner_id, task_type, content, status, now):
    # data 에 처리 기록을 한 줄 덧붙입니다. 파일에 저장하지는 않습니다.
    # 업무가 끝날 때(common_log_request)와, 사용자 요청 없이 자동으로 한 일(예약 이체 실행, 분할 회차 결제)이 씁니다.
    data["requests"].append({
        "request_id": "req-%04d" % (len(data["requests"]) + 1),
        "owner_id": owner_id,
        "task_type": task_type,
        "content": content,
        "status": status,
        "created_at": now.isoformat(timespec="seconds"),
    })


def next_id(items, key, prefix):
    # 목록에서 가장 큰 번호 + 1 로 새 ID 를 만듭니다. 예) reg-003 까지 있으면 reg-004. 비어 있으면 reg-001.
    # 개수 + 1 이 아니라 가장 큰 번호를 보는 이유 : 지운 항목(등록 계좌 삭제)이 있으면 번호가 겹칩니다.
    # 시험 계정(test)의 미리 넣은 데이터는 use-t01 처럼 숫자가 아닌 ID 라서 번호 셈에서 뺍니다.
    parts = [item[key].split("-")[1] for item in items]
    numbers = [int(part) for part in parts if part.isdigit()]
    return "%s-%03d" % (prefix, max(numbers, default=0) + 1)


def add_transaction(data, account, kind, amount, occurred_at, merchant=None):
    # data 에 계좌 거래 내역을 한 줄 덧붙입니다. 파일에 저장하지는 않습니다.
    # kind : deposit(입금) / withdrawal(출금). 이체와 카드값 결제가 씁니다. 카드 이용이 아니므로 card_id 는 비웁니다.
    data["transactions"].append({
        "transaction_id": "tx-%03d" % (len(data["transactions"]) + 1),
        "owner_id": account["owner_id"],
        "account_id": account["account_id"],
        "type": kind,
        "amount": amount,
        "occurred_at": occurred_at,
        "card_id": None,
        "merchant": merchant,
    })


def parse_time(text):
    # "2026-09-27T09:00" 같은 문자열을 시각으로 바꿉니다. 시간대가 없으면 이 컴퓨터 시간대로 봅니다.
    return datetime.fromisoformat(text).astimezone()


def now_text():
    # 지금 시각을 data.json 에 넣는 모양으로 돌려줍니다. 예) "2026-09-28T17:14:53+09:00"
    return datetime.now().astimezone().isoformat(timespec="seconds")


def when_text(text):
    # 저장된 시각 문자열을 화면에 보여줄 모양으로 바꿉니다. 예) "09월 28일 17:14"
    return parse_time(text).strftime("%m월 %d일 %H:%M")
