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


def parse_time(text):
    # "2026-09-27T09:00" 같은 문자열을 시각으로 바꿉니다. 시간대가 없으면 이 컴퓨터 시간대로 봅니다.
    return datetime.fromisoformat(text).astimezone()
