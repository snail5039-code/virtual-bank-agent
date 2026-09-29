# 웹에서 에이전트를 쓰게 해 주는 서버입니다. (web 1단계 : 서버 + 채팅)
# src/ 의 코드는 바꾸지 않고, main.py 가 하는 일을 그대로 가져다 씁니다.
#   - 입력 한 번 처리 : main.respond (분기 0 → 재개 / 새 요청)
#   - 턴이 끝난 뒤   : 진행 중 업무 기록(remember_pending), 최근 대화(remember_turn)
#   - 파일 잠금      : main.work_lock
#
# 실행 : uv run python web/server.py   → 브라우저에서 http://127.0.0.1:8000
#
# 지금은 한 사람이 한 창에서 쓰는 것만 생각합니다. (세션은 main.py 처럼 서버를 켤 때 하나)

import sys
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR.parent / "src"))     # src 의 모듈(main, data_store …)을 불러오기 위해

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import data_store
import logger
import main as bank     # src/main.py
from agents.common.nodes import SECRET, common_pending_check
from agents.supervisor.graph import bank_graph

log = logger.setup()
data_store.ensure()

app = FastAPI()
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


class ChatIn(BaseModel):
    text: str


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "static" / "index.html")


@app.post("/api/chat")
def chat(body: ChatIn):
    # main.handle_turn 과 같은 순서로 입력 한 번을 처리하고, 화면에 보여줄 것을 돌려줍니다.
    #   answer  : 답이나 질문·처리안
    #   pending : 멈춰 있으면 그 종류 (approval / question / secret), 끝났으면 None
    #   notices : 처리 전에 실행된 예약 이체·분할 회차 결과
    user_input = body.text.strip()
    with bank.work_lock:
        secret = common_pending_check(bank_graph, bank.config) == SECRET
        log.turn_start("****" if secret else user_input, bank.thread_id)
        notices = bank.run_due(log)
        try:
            answer = bank.respond(user_input, log)
            pending = common_pending_check(bank_graph, bank.config)
            try:
                bank.remember_pending(pending)
            except data_store.DataStoreError:
                pass
            bank.remember_turn(pending)
            log.turn_end(bank.turn_result(pending))
        except Exception as e:
            log.error(e)
            log.turn_end("오류")
            answer, pending = "처리 중 오류가 발생했습니다.", None
    return {"answer": answer, "pending": pending, "notices": notices}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
