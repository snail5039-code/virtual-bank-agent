# 여러 업무가 같이 쓰는 함수입니다. 로그인한 사용자, 기준일, 본인 확인, 기간·시각 계산.

from datetime import date, datetime, timedelta

import data_store

# 로그인한 사용자입니다. 인증(3-5 단계)을 만들기 전까지는 고정해 둡니다.
CURRENT_USER = "user-001"


def base_date():
    # 기준일. "오늘", "이번 주", "이번 달" 을 이 날짜로 계산합니다.
    # 부를 때마다 오늘 날짜를 돌려줍니다. 상수로 두면 켜 둔 채 자정을 넘겼을 때 "오늘" 이 어제로 남습니다.
    return date.today()


def authenticate(owner_id, value):
    # 본인 확인. 계좌 비밀번호 / PIN / 휴대전화번호 / 주민번호 뒷자리 중 하나가 맞으면 True 입니다.
    data = data_store.load()
    user = next(u for u in data["users"] if u["owner_id"] == owner_id)
    value = value.replace("-", "").strip()
    answers = {user["pin"], user["phone"].replace("-", ""), user["ssn_tail"]}
    answers |= {a["account_password"] for a in data["accounts"] if a["owner_id"] == owner_id}
    return value in answers


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


def find_requests(owner_id, keyword=None):
    # 처리 기록(원장)을 최근순으로 돌려줍니다. 쓰기 업무가 끝날 때마다 common_log_request 가 한 줄씩 남깁니다.
    # keyword 를 주면 업무 이름(task_type)에 그 글자가 든 기록만 봅니다. 예) "이체", "잠금", "결제", "재발급"
    # "아까 이체 됐어?" 같은 후속 질문은 LLM 이 기억으로 답하지 않고 여기서 꺼낸 기록으로 답합니다. (원칙 6)
    records = [r for r in data_store.load()["requests"] if r["owner_id"] == owner_id
               and (not keyword or keyword.replace(" ", "") in r["task_type"].replace(" ", ""))]
    # 같은 초에 여러 건이 남을 수 있으므로(예약 여러 건 실행, 일괄 결제) 시각이 같으면 나중 번호(request_id)가 앞입니다.
    return sorted(records, key=lambda r: (r["created_at"], r["request_id"]), reverse=True)


# ---------------------------------------------------------------- 진행 중 업무 (재시작 복구, 5-2)
# 승인·질문을 기다리며 멈춘 업무를 data.json 의 "pending" 에 한 건 적어 둡니다. 예약 이체와 같은 방식입니다.
# 켤 때 남아 있으면 main.py 가 알려주고, 다시 하겠다고 하면 원래 요청을 처음부터 다시 돌립니다.
# 이전 승인은 쓰지 않습니다. 꺼져 있는 동안 잔액·카드 상태가 바뀌었을 수 있기 때문입니다. (기획서 recovery)

def get_pending():
    return data_store.load().get("pending")


def set_pending(record):
    # record : {request_text(원래 요청 문장), task(업무 이름), kind(승인 / 질문 대기), created_at}
    data = data_store.load()
    data["pending"] = record
    data_store.save(data)


def clear_pending():
    data = data_store.load()
    if data.get("pending"):
        data["pending"] = None
        data_store.save(data)


def parse_time(text):
    # "2026-09-27T09:00" 같은 문자열을 시각으로 바꿉니다. 시간대가 없으면 이 컴퓨터 시간대로 봅니다.
    return datetime.fromisoformat(text).astimezone()
