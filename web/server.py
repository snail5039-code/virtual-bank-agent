# 웹에서 에이전트를 쓰게 해 주는 서버입니다.
# 에이전트 코드는 src 를 복사해 온 web/bank 를 씁니다 (src 는 터미널 버전으로 그대로 둠). main.py 가 하는 일을 그대로 가져다 씁니다.
# 데이터도 웹 전용 web/data 를 씁니다 (web/bank/data_store.py 가 자기 위치 기준으로 찾음).
#   - 입력 한 번 처리 : main.respond (분기 0 → 재개 / 새 요청)
#   - 턴이 끝난 뒤   : 진행 중 업무 기록(remember_pending), 최근 대화(remember_turn)
#   - 파일 잠금      : main.work_lock
#   - 30초 스케줄러  : main.scheduler_loop (결과는 main.outbox 에 쌓이고, /api/alerts 가 사람별로 나눠 줌)
#   - 재시작 복구    : 켤 때 남아 있던 진행 중 업무를 화면이 처음 열릴 때 묻습니다 (/api/recovery)
#
# 실행 : uv run python web/server.py   → 브라우저에서 http://127.0.0.1:8000
#
# 로그인 (여러 사람용 2단계) : /login 화면에서 아이디·로그인 비밀번호로 들어옵니다. 로그인하지 않으면 화면과 /api 를 못 씁니다.
#   시험용 계정 (web/data 에는 비밀번호가 해시로만 있음)
#     doyoon  / doyoon1234   → user-001 김도윤
#     seoyeon / seoyeon1234  → user-002 김서연
#     jiho    / jiho1234     → user-003 박지호
#     test    / test         → user-005 테스트 (계좌·카드 없음. 본인 확인 PIN 1234, 주민번호 뒷자리 1234567)
#   회원가입 : /signup 화면. 이름·휴대전화번호·아이디·비밀번호·PIN(본인 확인용 4자리)·주민번호 뒷자리(7자리)를 받아 users 에 새 사람을 넣고 바로 로그인합니다.
#   화면(요약·메뉴)과 버튼 업무는 로그인한 사람 것만 보여주고 바꿉니다. (3단계)
#   에이전트도 사람마다 세션(thread_id)·최근 대화가 따로입니다. 요청마다 로그인한 사람을 State 의 owner_id 로 넣습니다. (4단계)
#   재시작 복구·스케줄러 알림도 사람별입니다. 복구 기록은 data.json 의 pending 에 사람마다, 알림은 그 예약의 주인에게만. (5단계)

import re
import secrets
import sys
import threading
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR / "bank"))     # web/bank : src 를 복사해 온 웹 전용 에이전트 코드 (src 는 터미널 버전으로 그대로 둠)

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from datetime import datetime

import actions          # web/actions.py : 메뉴 화면 버튼 업무
import data_store
import functions
import logger
import main as bank     # web/bank/main.py
from agents.common.nodes import APPROVAL, SECRET, common_pending_check
from agents.supervisor.graph import bank_graph

log = logger.setup()
data_store.ensure()

# 켤 때 할 일은 main.main() 과 같은 순서입니다.
# 1) 꺼져 있던 동안 시각이 지난 예약 이체·분할 회차를 먼저 실행합니다. 결과는 화면 알림으로 보냅니다.
#    결과는 (owner_id, 한 줄) 이고, 그 사람이 로그인해 화면을 열면 /api/alerts 로 받습니다.
for item in bank.run_due(log):
    bank.outbox.put(item)
# 2) 지난번에 끝나기 전에 꺼진 업무가 있으면 기억해 두고, 그 사람이 화면을 처음 열 때 다시 할지 묻습니다.
#    이 서버에서 새로 멈춘 업무(remember_pending 이 적는 것)와 헷갈리지 않게 켤 때 한 번만 읽습니다.
#    interrupted : {owner_id: 기록}
try:
    interrupted = functions.pending_records(data_store.load())
except data_store.DataStoreError:
    interrupted = {}
# 3) 켜 있는 동안 30초마다 예약을 확인하는 스레드를 띄웁니다. (서버가 끝나면 같이 끝남)
threading.Thread(target=bank.scheduler_loop, args=(log,), daemon=True).start()

app = FastAPI()
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


# ---------------------------------------------------------------- 로그인
# 세션 : 로그인하면 임의의 글자(토큰)를 만들어 쿠키로 주고, 서버는 {토큰: owner_id} 로 기억합니다.
# 서버 메모리에만 두므로 서버를 다시 켜면 모두 로그아웃됩니다.
SESSION_COOKIE = "session"
sessions = {}


def login_user(request: Request):
    # 요청의 쿠키로 로그인한 사람(owner_id)을 찾습니다. 없으면 None.
    return sessions.get(request.cookies.get(SESSION_COOKIE))


@app.middleware("http")
async def require_login(request: Request, call_next):
    # 로그인 화면과 로그인 요청, 화면 파일(static) 말고는 로그인해야 씁니다.
    # 화면(/)은 로그인 화면으로 보내고, /api 는 401 을 돌려줍니다 (app.js 가 로그인 화면으로 보냄).
    path = request.url.path
    if path in ("/login", "/api/login", "/signup", "/api/signup") or path.startswith("/static/") or login_user(request):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "로그인이 필요합니다"}, status_code=401)
    return RedirectResponse("/login")


class LoginIn(BaseModel):
    login_id: str
    password: str


@app.get("/login")
def login_page(request: Request):
    if login_user(request):
        return RedirectResponse("/")
    return FileResponse(WEB_DIR / "static" / "login.html")


@app.post("/api/login")
def login(body: LoginIn):
    # 아이디로 사람을 찾고, 로그인 비밀번호를 해시로 비교합니다. (본인 확인 PIN 과는 다른 값)
    # 아이디가 없을 때와 비밀번호가 틀렸을 때 같은 문구를 써서, 어떤 아이디가 있는지 알 수 없게 합니다.
    with bank.work_lock:
        data = data_store.load()
    user = next((u for u in data["users"] if u.get("login_id") == body.login_id.strip()), None)
    if not user or not functions.check_secret(body.password, user.get("password")):
        log.note("로그인 실패  %s" % body.login_id.strip())
        return JSONResponse({"error": "아이디 또는 비밀번호가 맞지 않습니다."}, status_code=401)
    log.note("로그인  %s (%s)" % (user["login_id"], user["owner_id"]))
    return start_session(user)


def start_session(user):
    # 토큰을 만들어 기억하고 쿠키로 줍니다. 로그인과 회원가입이 같이 씁니다.
    token = secrets.token_hex(16)
    sessions[token] = user["owner_id"]
    response = JSONResponse({"name": user["name"]})
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")
    return response


class SignupIn(BaseModel):
    name: str
    phone: str
    login_id: str
    password: str
    pin: str
    ssn_tail: str


def check_signup(data, info):
    # 회원가입 값 검사. 문제가 있으면 사유, 없으면 None.
    if not 1 <= len(info["name"]) <= 20:
        return "이름을 1~20자로 적어 주세요."
    if not re.fullmatch(r"010-\d{4}-\d{4}", info["phone"]):
        return "휴대전화번호는 010-1234-5678 모양으로 적어 주세요."
    if not re.fullmatch(r"[a-z0-9]{4,20}", info["login_id"]):
        return "아이디는 영어 소문자·숫자 4~20자로 정해 주세요."
    if any(u.get("login_id") == info["login_id"] for u in data["users"]):
        return "이미 쓰는 아이디입니다."
    if len(info["password"]) < 8:
        return "비밀번호는 8자 이상으로 정해 주세요."
    if not re.fullmatch(r"\d{4}", info["pin"]):
        return "PIN 은 숫자 4자리로 정해 주세요."
    if not re.fullmatch(r"\d{7}", info["ssn_tail"]):
        return "주민등록번호 뒷자리는 숫자 7자리로 적어 주세요."
    return None


@app.get("/signup")
def signup_page(request: Request):
    if login_user(request):
        return RedirectResponse("/")
    return FileResponse(WEB_DIR / "static" / "signup.html")


@app.post("/api/signup")
def signup(body: SignupIn):
    # 새 사람을 users 에 넣습니다. 비밀번호·PIN·주민번호 뒷자리는 해시로만 둡니다. 계좌·카드는 없이 시작합니다.
    # 본인 확인은 기존 사람과 같이 PIN·휴대전화번호·주민번호 뒷자리·계좌 비밀번호 중 하나로 합니다.
    info = {key: value.strip() for key, value in body.model_dump().items()}
    with bank.work_lock:
        data = data_store.load()
        error = check_signup(data, info)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        user = {
            "owner_id": functions.next_id(data["users"], "owner_id", "user"),
            "name": info["name"],
            "phone": info["phone"],
            "ssn_tail": functions.hash_secret(info["ssn_tail"]),
            "pin": functions.hash_secret(info["pin"]),
            "login_id": info["login_id"],
            "password": functions.hash_secret(info["password"]),
        }
        data["users"].append(user)
        try:
            data_store.save(data)
        except data_store.DataStoreError:
            return JSONResponse({"error": "저장에 실패해 가입하지 못했습니다."}, status_code=500)
    log.note("회원가입  %s (%s)" % (user["login_id"], user["owner_id"]))
    return start_session(user)


@app.post("/api/logout")
def logout(request: Request):
    owner = sessions.pop(request.cookies.get(SESSION_COOKIE), None)
    log.note("로그아웃  %s" % owner)
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


class ChatIn(BaseModel):
    text: str


class RecoveryIn(BaseModel):
    again: bool     # True : 처음부터 다시 진행 / False : 지우기


class ActionIn(BaseModel):
    kind: str                   # actions.ACTIONS 의 이름 (예: card_lock)
    target: str = ""            # 대상 ID (카드 ID 등)
    params: dict = {}           # 화면에서 입력받는 값 (이체의 출금·입금·금액·예약 시각)
    approve: bool = True        # False 면 거절
    secret: str | None = None   # 본인 확인 답 (아직 본인 확인 전일 때만)


# 버튼 업무의 본인 확인 : 에이전트처럼 한 번 맞히면 서버를 끌 때까지 다시 묻지 않고, 3번 틀리면 처음부터 다시입니다.
# 사람마다 따로 기억합니다. {owner_id: {"ok": 맞혔는지, "tries": 틀린 횟수}}
# 에이전트에서 이미 본인 확인을 했으면 그것도 인정합니다. (반대로 여기서 한 확인을 그래프 State 에 넣지는 않습니다)
AUTH_TRIES = 3
button_auth = {}

# 스케줄러 알림 : 사람마다 아직 안 가져간 알림 줄 {owner_id: [줄, ...]}
alert_box = {}


def deliver(items):
    # (owner_id, 한 줄) 들을 그 사람 알림함에 넣습니다.
    # 누구 것도 아닌 줄(저장 실패 같은 오류, owner_id 가 None)은 모든 사람에게 넣습니다.
    for owner_id, line in items:
        owners = [owner_id] if owner_id else [u["owner_id"] for u in data_store.load()["users"]]
        for owner in owners:
            alert_box.setdefault(owner, []).append(line)


def auth_of(me):
    return button_auth.setdefault(me, {"ok": False, "tries": 0})


def agent_pending(me):
    # 이 사람의 에이전트가 질문·승인을 기다리는 중이면 그 종류, 아니면 None.
    return common_pending_check(bank_graph, bank.config_of(me))


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "static" / "index.html")


@app.get("/api/summary")
def summary(request: Request):
    # 화면 옆 패널(총 잔액, 계좌, 카드, 카드값, 예약 이체, 최근 처리)에 쓸 값을 data.json 에서 모읍니다. (3단계)
    # 읽기만 하고, 금액은 파일에 있는 값을 그대로 씁니다.
    with bank.work_lock:
        data = data_store.load()
        me = login_user(request)
        authenticated = is_authenticated(me)
    mine = lambda items: [item for item in items if item["owner_id"] == me]

    accounts = mine(data["accounts"])
    names = {a["account_id"]: a["nickname"] for a in accounts}
    names.update({r["registered_id"]: r["nickname"] for r in mine(data["registered_accounts"])})
    unpaid = [s for s in mine(data["card_statements"]) if s["status"] != "paid"]

    return {
        "user": next(u["name"] for u in data["users"] if u["owner_id"] == me),
        "authenticated": authenticated,
        "total": sum(a["balance"] for a in accounts),
        "accounts": [{"name": a["nickname"], "balance": a["balance"]} for a in accounts],
        "cards": [{"name": c["name"], "status": c["status"], "label": functions.CARD_STATUS[c["status"]]}
                  for c in mine(data["cards"]) if c["status"] != "cancelled"],
        "bills": {"count": len(unpaid), "amount": sum(s["remaining_amount"] for s in unpaid)},
        "schedules": [{"at": s["scheduled_at"], "to": names.get(s["to_account"], s["to_account"]), "amount": s["amount"]}
                      for s in mine(data["scheduled_transfers"]) if s["status"] == "예약"],
        "requests": [{"task": r["task_type"], "status": r["status"], "at": r["created_at"]}
                     for r in mine(data["requests"])[-5:][::-1]],
    }


TX_TYPE = {"deposit": "입금", "withdrawal": "출금"}
CARD_TYPE = {"credit": "신용", "debit": "체크"}


@app.get("/api/view/{name}")
def view(name: str, request: Request):
    # 왼쪽 메뉴 화면(계좌, 거래 내역, 카드, 카드값, 예약 이체, 처리 기록)에 쓸 목록입니다.
    # LLM 을 거치지 않고 data.json 을 읽기만 합니다. 바꾸는 일은 에이전트(승인 흐름)로만 합니다.
    with bank.work_lock:
        data = data_store.load()
    me = login_user(request)
    mine = lambda key: [item for item in data[key] if item["owner_id"] == me]
    nick = {a["account_id"]: a["nickname"] for a in data["accounts"]}
    card_names = {c["card_id"]: c["name"] for c in data["cards"]}

    if name == "accounts":
        return [{"id": a["account_id"], "name": a["nickname"], "bank": a["bank_name"], "number": a["account_number"],
                 "purpose": a.get("purpose"), "balance": a["balance"]} for a in mine("accounts")]
    if name == "transactions":
        rows = sorted(mine("transactions"), key=lambda t: t["occurred_at"], reverse=True)
        return [{"at": t["occurred_at"], "account": nick.get(t["account_id"], t["account_id"]),
                 "type": TX_TYPE.get(t["type"], t["type"]), "amount": t["amount"], "merchant": t.get("merchant"),
                 "card": card_names.get(t.get("card_id"))} for t in rows]
    if name == "cards":
        return [{"id": c["card_id"], "name": c["name"], "type": CARD_TYPE.get(c.get("card_type"), c.get("card_type")),
                 "bank": c.get("bank_name"), "account": nick.get(c.get("account_id")),
                 "status": c["status"], "label": functions.CARD_STATUS[c["status"]]} for c in mine("cards")]
    if name == "bills":
        rows = sorted(mine("card_statements"), key=lambda s: s["billing_month"], reverse=True)
        return [{"id": s["statement_id"], "card": card_names.get(s["card_id"], s["card_id"]), "month": s["billing_month"],
                 "total": s["total_amount"], "remaining": s["remaining_amount"], "due": s["due_date"],
                 "status": s["status"], "label": functions.STATEMENT_STATUS[s["status"]]} for s in rows]
    if name == "schedules":
        rows = sorted(mine("scheduled_transfers"), key=lambda s: s["scheduled_at"], reverse=True)
        return [{"id": s["schedule_id"], "at": s["scheduled_at"], "from": nick.get(s["from_account"]),
                 "to": functions.target_name(data, s["to_account"]), "amount": s["amount"], "status": s["status"]}
                for s in rows]
    if name == "registered":
        # 등록 계좌 (돈을 보낼 상대 계좌 주소록)
        return [{"id": r["registered_id"], "name": r["nickname"], "bank": r["bank_name"], "number": r["account_number"],
                 "holder": r["holder_name"]} for r in mine("registered_accounts")]
    if name == "banks":
        # 계좌 만들기·상대 계좌 등록·카드 등록 창의 은행 고르기 목록
        return list(actions.BANKS)
    if name == "addresses":
        # 재발급 창의 배송지 고르기 목록 (집 / 회사)
        return [{"id": a["address_id"], "label": a["label"], "address": a["address"]} for a in mine("addresses")]
    if name == "transfer_options":
        # 이체 창의 고르기 목록 : 출금은 내 계좌, 입금은 내 계좌 + 등록 계좌(상대 계좌)
        accounts = [{"id": a["account_id"], "name": a["nickname"], "balance": a["balance"]} for a in mine("accounts")]
        targets = [{"id": a["id"], "name": a["name"]} for a in accounts]
        targets += [{"id": r["registered_id"], "name": "%s (%s %s)" % (r["nickname"], r["bank_name"], r["holder_name"])}
                    for r in mine("registered_accounts")]
        return {"accounts": accounts, "targets": targets}
    if name == "requests":
        return [{"id": r["request_id"], "at": r["created_at"], "task": r["task_type"], "status": r["status"],
                 "content": r["content"]} for r in mine("requests")[::-1]]
    raise HTTPException(status_code=404, detail="없는 화면입니다")


def is_authenticated(me):
    # 버튼에서 본인 확인을 했거나, 이 사람의 에이전트 세션에서 했으면 True 입니다.
    # 업무 중간(멈춘 동안)에는 에이전트의 본인 확인 결과가 안쪽 그래프 State 에만 있어서 안쪽까지 봅니다.
    return auth_of(me)["ok"] or any(values.get("authenticated") for values in state_values(me))


# ---------------------------------------------------------------- 메뉴 화면 버튼 업무
def action_reply(answer=None, error=None, **extra):
    return {"answer": answer, "error": error, **extra}


@app.post("/api/action/preview")
def action_preview(body: ActionIn, request: Request):
    # 버튼을 누르면 먼저 검사하고 처리안을 돌려줍니다. 화면은 이걸 확인 창으로 보여줍니다.
    action = actions.ACTIONS.get(body.kind)
    if not action:
        raise HTTPException(status_code=404, detail="없는 업무입니다")
    me = login_user(request)
    with bank.work_lock:
        # 내 업무로 에이전트가 질문·승인을 기다리는 중이면 막습니다. 같은 데이터를 두 곳에서 동시에 바꾸지 않게 합니다.
        if agent_pending(me):
            return action_reply(error="에이전트에서 진행 중인 업무가 있어요. 그 업무를 먼저 끝내거나 취소해 주세요.")
        error, proposal = action["preview"](data_store.load(), me, body.target, body.params)
        need_auth = not is_authenticated(me)
    if error:
        return action_reply(error=error)
    return action_reply(proposal=proposal, need_auth=need_auth)


@app.post("/api/action/run")
def action_run(body: ActionIn, request: Request):
    # 확인 창에서 승인(또는 거절)하면 옵니다. 에이전트와 같은 순서입니다.
    #   본인 확인 → 실행 직전 다시 검사 → 실행 → 처리 기록 → 저장(3번까지) → 안내
    #   거절 : 바꾸지 않고 처리 기록만 "거절" 로 남깁니다.
    action = actions.ACTIONS.get(body.kind)
    if not action:
        raise HTTPException(status_code=404, detail="없는 업무입니다")

    me = login_user(request)
    auth = auth_of(me)
    with bank.work_lock:
        if agent_pending(me):
            return action_reply(error="에이전트에서 진행 중인 업무가 있어요. 그 업무를 먼저 끝내거나 취소해 주세요.")
        data = data_store.load()
        error, proposal = action["preview"](data, me, body.target, body.params)      # 실행 직전 다시 검사
        if error:
            return action_reply(error=error)
        task = proposal["task"]
        log.turn_start("[버튼 %s] %s %s" % (me, task, "승인" if body.approve else "거절"), bank.session(me)["thread_id"])

        if not body.approve:
            answer = "%s 요청을 진행하지 않았습니다. 바뀐 것은 없습니다." % task
            functions.add_request(data, me, task, dict(proposal["rows"]), "거절", datetime.now().astimezone())
            result = "거절"
        else:
            if not is_authenticated(me):
                if not body.secret or not functions.authenticate(me, body.secret):
                    auth["tries"] += 1
                    log.note("본인 확인 실패 %d/%d" % (auth["tries"], AUTH_TRIES))
                    if auth["tries"] >= AUTH_TRIES:
                        auth["tries"] = 0
                        log.turn_end("실패")
                        return action_reply(error="본인 확인에 %d번 실패했습니다. 처음부터 다시 요청해 주세요." % AUTH_TRIES)
                    log.turn_end("질문 대기")
                    return action_reply(auth_error="일치하지 않습니다. (%d/%d)" % (auth["tries"], AUTH_TRIES))
                auth.update(ok=True, tries=0)
                log.note("본인 확인 성공")
            try:
                answer = action["apply"](data, me, body.target, body.params)
            except ValueError as e:     # 실행하다 막힌 경우 (예: 이체 직전 잔액) : 저장하지 않습니다
                log.turn_end("실패")
                return action_reply(error=str(e))
            functions.add_request(data, me, task, dict(proposal["rows"]), "완료", datetime.now().astimezone())
            result = "완료"

        for attempt in range(1, 4):     # 저장은 3번까지 (에이전트의 common_save 와 같음)
            try:
                data_store.save(data)
                break
            except data_store.DataStoreError:
                log.detail("저장 실패 %d/3" % attempt)
        else:
            log.turn_end("실패")
            return action_reply(error="저장에 실패해 처리하지 못했습니다. 바뀐 것은 없습니다.")
        log.turn_end(result)
    return action_reply(answer=answer, result=result)


def state_values(me):
    # 바깥(1단) State 부터 멈춘 안쪽 그래프(2단, 3단) State 까지의 값을 차례로 돌려줍니다.
    # 그래프가 멈춰 있는 동안 안쪽에서 바뀐 값(처리안, 본인 확인)은 바깥 State 에 아직 없기 때문입니다.
    snapshot = bank_graph.get_state(bank.config_of(me), subgraphs=True)
    values = []
    while snapshot:
        values.append(snapshot.values)
        inner = [task.state for task in snapshot.tasks if task.state]
        snapshot = inner[0] if inner else None
    return values


def waiting_proposal(me):
    # 승인을 기다리는 처리안을 꺼냅니다. 화면이 글자 상자 대신 카드로 그리게 합니다.
    # 처리안은 3단 그래프(안쪽) State 에만 있어서, 가장 안쪽 값을 씁니다.
    #   {"task": "이체", "rows": [["출금", "생활비 (…)"], …], "retry": 답을 못 알아들어 다시 묻는 중인지}
    found = None
    for values in state_values(me):
        if values.get("proposal"):
            found = {**values["proposal"], "retry": values.get("approval") == "모름"}
    return found


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    return run_turn(login_user(request), body.text.strip())


@app.get("/api/waiting")
def waiting(request: Request):
    # 화면을 새로 열었을 때(새로고침) 그래프가 멈춰 있으면, 멈춘 질문이나 처리안을 다시 그리게 알려줍니다.
    # 그래프는 서버에 그대로 멈춰 있으므로 다음 입력은 그 답으로 들어갑니다.
    me = login_user(request)
    with bank.work_lock:
        pending = agent_pending(me)
        if not pending:
            return {"pending": None, "answer": None, "proposal": None}
        text = bank_graph.get_state(bank.config_of(me)).interrupts[0].value["text"]
        proposal = waiting_proposal(me) if pending == APPROVAL else None
    return {"pending": pending, "answer": text, "proposal": proposal}


@app.get("/api/alerts")
def alerts(request: Request):
    # 스케줄러가 입력 없이 실행한 예약 이체·분할 회차 결과를 꺼내 줍니다. 화면이 몇 초마다 부릅니다. (4단계)
    # 스케줄러가 쌓은 것을 먼저 사람별 알림함으로 나누고, 로그인한 사람 것만 꺼내 줍니다.
    # 다른 사람 것은 그 사람이 화면을 열 때까지 알림함에 남습니다.
    with bank.work_lock:
        items = []
        while not bank.outbox.empty():
            items.append(bank.outbox.get())
        deliver(items)
        lines = alert_box.pop(login_user(request), [])
    return {"alerts": lines}


@app.get("/api/recovery")
def recovery(request: Request):
    # 켤 때 남아 있던 이 사람의 진행 중 업무를 알려줍니다. 없으면 None. (main.recover_pending 과 같은 내용)
    record = interrupted.get(login_user(request))
    if not record:
        return {"record": None}
    return {"record": {**record, "when": functions.when_text(record["created_at"])}}


@app.post("/api/recovery")
def recover(body: RecoveryIn, request: Request):
    # 다시 하면 원래 요청 문장으로 처음부터 돌립니다. 잔액·상태를 다시 검사하고 승인도 다시 받습니다.
    # 이전 승인만으로 자동 실행하지 않습니다.
    me = login_user(request)
    record = interrupted.pop(me, None)
    if not record:
        return {"answer": "다시 진행할 업무가 없습니다.", "pending": None, "proposal": None, "notices": []}
    with bank.work_lock:     # data.json 을 쓰므로 스케줄러와 겹치지 않게
        log.note("재시작 복구  '%s' → %s" % (record["request_text"], "다시" if body.again else "지움"))
        functions.clear_pending(me)
    if body.again:
        return run_turn(me, record["request_text"])
    return {"answer": "진행 중이던 업무를 지웠습니다. 바뀐 것은 없습니다.", "pending": None, "proposal": None, "notices": []}


def run_turn(me, user_input):
    # main.handle_turn 과 같은 순서로 입력 한 번을 처리하고, 화면에 보여줄 것을 돌려줍니다.
    #   answer   : 답이나 질문·처리안 (글자)
    #   pending  : 멈춰 있으면 그 종류 (approval / question / secret), 끝났으면 None
    #   proposal : 승인 대기면 처리안 값 (카드로 그림), 아니면 None
    #   notices  : 처리 전에 실행된 예약 이체·분할 회차 결과 중 이 사람 것 (다른 사람 것은 그 사람 알림함으로)
    proposal = None
    with bank.work_lock:
        secret = agent_pending(me) == SECRET
        log.turn_start("****" if secret else user_input, bank.session(me)["thread_id"])
        deliver(bank.run_due(log))
        notices = alert_box.pop(me, [])
        try:
            answer = bank.respond(me, user_input, log)
            pending = agent_pending(me)
            try:
                bank.remember_pending(me, pending)
            except data_store.DataStoreError:
                pass
            bank.remember_turn(me, pending)
            if pending == APPROVAL:
                proposal = waiting_proposal(me)
            log.turn_end(bank.turn_result(pending))
        except Exception as e:
            log.error(e)
            log.turn_end("오류")
            answer, pending = "처리 중 오류가 발생했습니다.", None
    return {"answer": answer, "pending": pending, "proposal": proposal, "notices": notices}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
