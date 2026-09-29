# 사용자 입력을 반복해서 받고 응답을 출력합니다.
# 같은 대화 세션(thread_id)을 유지하고, 종료 명령을 처리합니다.
# 그래프가 질문하거나 승인을 기다리며 멈춰 있으면, 다음 입력을 그 답으로 넘깁니다. (분기 0)
# 멈춘 채 꺼졌다가 다시 켜면, 끊긴 업무를 알려주고 처음부터 다시 할지 묻습니다. (재시작 복구, 5-2)
# 켜 있는 동안 스케줄러 스레드가 30초마다 예약 이체·분할 회차를 확인해 시각이 되면 바로 실행합니다. (실시간 스케줄러, 12장 보완)
#
# 실행 : uv run python src/main.py
#        uv run python src/main.py --debug   (로그를 화면에도 띄웁니다)

import getpass
import queue
import re
import sys
import threading
from datetime import datetime

from langgraph.types import Command
from rich.console import Console

import data_store
import functions
import logger
from agents.common.nodes import APPROVAL, QUESTION, SECRET, common_pending_check
from agents.supervisor.graph import bank_graph
from state import new_request

# 세션은 사람마다 하나씩 둡니다. (웹 여러 사람용)
#   thread_id : 그 사람의 그래프 State 가 저장되는 칸. 멈춘 질문·처리안, 본인 확인이 사람마다 따로 남습니다.
#   history   : 그 사람의 최근 대화
# 처음 요청할 때 만들고, 서버를 끌 때까지 씁니다. 터미널(main)은 functions.CURRENT_USER 한 사람만 씁니다.
STARTED = datetime.now().strftime("%Y%m%d-%H%M%S")
sessions = {}
console = Console()

# 대화 기억 : 끝난 턴마다 {요청, 답} 을 한 줄씩 남기고 최근 HISTORY_TURNS 개만 둡니다. 세션(켜고 끌 때까지) 동안만 있습니다.
# 중간에 오간 것(본인 확인, 승인, 번호 고르기)은 넣지 않습니다. 답은 앞부분만 남깁니다.
HISTORY_TURNS = 5
HISTORY_ANSWER_LINES = 4


def session(owner_id):
    # 그 사람의 세션을 돌려줍니다. 없으면 만듭니다.  {"thread_id", "config", "history"}
    if owner_id not in sessions:
        thread_id = "%s-session-%s" % (owner_id, STARTED)
        sessions[owner_id] = {"thread_id": thread_id, "config": {"configurable": {"thread_id": thread_id}}, "history": []}
    return sessions[owner_id]


def config_of(owner_id):
    return session(owner_id)["config"]

# 실시간 스케줄러 : 입력을 기다리는 동안에도 SCHEDULE_SECONDS 마다 예약 이체·분할 회차를 확인합니다.
#   work_lock : data.json 을 읽고 쓰는 일을 한 번에 한쪽만 하게 합니다.
#               사용자 입력 한 번을 처리하는 동안(handle_turn)과 스케줄러가 한 번 도는 동안 잡습니다.
#               둘이 겹치면 먼저 읽은 쪽이 나중에 저장하면서 다른 쪽이 바꾼 내용을 덮어씁니다.
#               승인·질문을 기다리는 동안은 그래프가 멈춰 있어 잡지 않으므로, 그 사이에는 스케줄러가 돕니다.
#   outbox    : 스케줄러는 화면에 바로 쓰지 않고 결과 줄을 여기에 넣습니다. 치고 있는 줄에 글자가 끼어들지 않게,
#               main 이 입력을 받은 직후 답을 보여주기 전에 꺼내 보여줍니다. (실행은 제시각, 화면에는 다음 입력 때)
SCHEDULE_SECONDS = 30
work_lock = threading.Lock()
outbox = queue.Queue()
stop_event = threading.Event()


def respond(owner_id, user_input, log):
    # [분기 0] 멈춰 있는 업무가 있으면 입력을 그 답으로 넘기고, 없으면 새 요청으로 시작합니다.
    # 멈춘 업무도, 새 요청도 그 사람의 세션(thread_id)에서만 봅니다.
    config = config_of(owner_id)
    pending = common_pending_check(bank_graph, config)
    if pending == APPROVAL:
        log.interrupt_resume()
        result = bank_graph.invoke(Command(resume=user_input), config=config)
    elif pending in (QUESTION, SECRET):
        log.branch(0, "질문 대기 있음 → 답으로 재개")
        result = bank_graph.invoke(Command(resume=user_input), config=config)
    else:
        log.branch(0, "대기 중인 업무 없음 → 새 요청")
        result = bank_graph.invoke(new_request(user_input, list(session(owner_id)["history"]), owner_id), config=config)

    if "__interrupt__" in result:
        return result["__interrupt__"][0].value["text"]     # 그래프가 던진 질문이나 처리안
    return result["answer"]


def turn_result(pending):
    # pending : 턴이 끝난 뒤의 common_pending_check 결과 (handle_turn 이 한 번 구해 넘깁니다)
    if pending == APPROVAL:
        return "승인 대기"
    if pending in (QUESTION, SECRET):
        return "질문 대기"
    return "완료"


def run_due(log):
    # 시각이 지난 예약 이체·분할 회차를 실행하고 결과 줄을 로그에 남긴 뒤 돌려줍니다. 그래프를 거치지 않습니다.
    # 승인은 예약할 때(분할을 걸 때) 받았기 때문입니다.
    # 여기서 예외가 나도 프로그램·스케줄러 스레드가 죽지 않게 막습니다. 다음 확인 때 다시 봅니다.
    try:
        lines = functions.run_due_schedules()
    except Exception as e:
        log.error(e)
        lines = ["[예약 이체·분할 회차] 확인 중 오류가 나 처리하지 못했습니다. 다음 확인 때 다시 봅니다."]
    for line in lines:
        log.note(line)
    return lines


def run_schedules(log):
    # 켤 때와 입력을 처리하기 전에 부릅니다. 결과를 바로 화면에 보여줍니다.
    for line in run_due(log):
        print(line)


def scheduler_loop(log):
    # 스케줄러 스레드가 도는 함수입니다. SCHEDULE_SECONDS 동안 쉬었다가(쉬는 동안은 CPU 를 쓰지 않습니다) 확인하기를 반복합니다.
    # "종료" 로 stop_event 가 켜지면 쉬던 중이라도 바로 끝납니다.
    # 결과는 화면에 바로 쓰지 않고 outbox 에 넣습니다. (치고 있는 줄에 끼어들지 않게)
    while not stop_event.wait(SCHEDULE_SECONDS):
        with work_lock, log.background("스케줄러") as job:
            lines = run_due(log)
            for line in lines:
                outbox.put(line)
            job["keep"] = bool(lines)


def show_outbox():
    # 스케줄러가 모아 둔 결과를 보여줍니다. 입력을 받은 직후, 답을 보여주기 전에 부릅니다.
    while not outbox.empty():
        print(outbox.get())


def read_input():
    # 본인 확인을 묻는 중이면 입력한 글자가 화면에 보이지 않게 받습니다.
    # 사람이 치는 터미널일 때만 가립니다. 확인 스크립트처럼 입력을 넣어 줄 때는 그대로 받습니다.
    prompt = "요청을 입력하세요 : "
    if common_pending_check(bank_graph, config_of(functions.CURRENT_USER)) == SECRET and sys.stdin.isatty():
        return getpass.getpass(prompt).strip()
    return input(prompt).strip()


def remember_pending(owner_id, kind):
    # [재시작 복구] 턴이 끝났을 때 그래프가 승인·질문을 기다리고 있으면(kind) 진행 중 업무로 적어 두고,
    # 기다리는 것이 없으면(끝났으면) 지웁니다. 예약 이체처럼 data.json 에 남겨 켤 때 확인합니다.
    saved = functions.get_pending()
    if kind:
        snapshot = bank_graph.get_state(config_of(owner_id))
        # 업무 이름은 멈출 때 보여준 처리안 제목에서 꺼냅니다. 예) "[이체 처리안]" → 이체
        # (처리안은 3단 그래프 안에 있어서 바깥 State 에는 아직 없습니다. 처리안 전 질문이면 분야 이름을 씁니다)
        title = re.search(r"\[(.+?) 처리안\]", snapshot.interrupts[0].value["text"])
        record = {
            "request_text": snapshot.values.get("request_text"),
            "task": title.group(1) if title else snapshot.values.get("domain"),
            "kind": "승인 대기" if kind == APPROVAL else "질문 대기",
        }
        if not saved or {k: saved.get(k) for k in record} != record:     # 같은 업무면 다시 쓰지 않습니다
            record["created_at"] = functions.now_text()
            functions.set_pending(record)
    elif saved:
        functions.clear_pending()


def remember_turn(owner_id, pending):
    # 업무가 끝난 턴(승인·질문을 기다리지 않음)이면 그 요청과 마지막 답을 최근 대화에 한 줄 남깁니다.
    # 요청은 "그거" 를 풀었으면 푼 문장(request_text)입니다. 그래야 다음 턴에서 또 가리킬 때 이름이 남아 있습니다.
    values = bank_graph.get_state(config_of(owner_id)).values
    if pending or not values.get("answer"):
        return
    answer = "\n".join(values["answer"].splitlines()[:HISTORY_ANSWER_LINES])
    history = session(owner_id)["history"]
    history.append({"request": values["request_text"], "answer": answer})
    del history[:-HISTORY_TURNS]


def handle_turn(user_input, log):
    # 입력 한 번을 처리하고 답을 화면에 보여줍니다. 복구로 다시 돌릴 때도 이 함수를 씁니다.
    # 본인 확인 답(비밀번호 등)은 로그 파일에 그대로 남기지 않습니다.
    # 입력 한 번을 처리하는 동안은 잠금을 잡습니다. 스케줄러가 끼어들어 data.json 을 동시에 쓰지 않게 합니다.
    me = functions.CURRENT_USER
    with work_lock:
        secret = common_pending_check(bank_graph, config_of(me)) == SECRET
        log.turn_start("****" if secret else user_input, session(me)["thread_id"])
        # 예약 이체 : 요청을 처리하기 전에, 시각이 된 예약을 처리합니다. (스케줄러가 30초마다 보지만, 그 사이에 된 것까지 확실히)
        run_schedules(log)
        try:
            with console.status("[bold green]에이전트가 작업 중입니다...[/bold green]", spinner="dots"):
                answer = respond(me, user_input, log)
            # 턴이 끝난 뒤 멈춰 있는지를 한 번만 보고, 아래 세 곳에 넘깁니다.
            pending = common_pending_check(bank_graph, config_of(me))
            try:
                remember_pending(me, pending)
            except data_store.DataStoreError:
                pass    # 진행 중 기록을 못 남겨도 이번 답은 그대로 보여줍니다. (사유는 data_store 가 로그에 남깁니다)
            remember_turn(me, pending)
            log.turn_end(turn_result(pending))
        except Exception as e:
            log.error(e)
            log.turn_end("오류")
            answer = "처리 중 오류가 발생했습니다."

    print(answer)
    print()


YES_WORDS = ("예", "네", "응", "ㅇㅇ", "진행", "다시", "좋아", "yes", "y")


def recover_pending(log):
    # [재시작 복구] 켤 때 진행 중이던 업무가 남아 있으면 알려주고 다시 할지 묻습니다.
    # 다시 하면 원래 요청 문장을 새 요청으로 처음부터 돌립니다. 지금 잔액·상태로 다시 검사하고, 승인도 다시 받습니다.
    # 이전 승인만으로 자동 실행하지 않습니다. (예약 이체는 예약할 때 승인을 받았으므로 켤 때 바로 실행하는 것과 다릅니다)
    try:
        record = functions.get_pending()
    except data_store.DataStoreError:
        return
    if not record:
        return

    when = functions.when_text(record["created_at"])
    print("[진행 중이던 업무] %s  '%s' (%s) 요청이 끝나기 전에 종료되었습니다." % (when, record["request_text"], record["task"]))
    print("  처음부터 다시 진행할까요? 잔액·카드 상태를 다시 확인하고 승인도 다시 받습니다. (예 / 아니오)")
    answer = read_input().lower()
    log.note("재시작 복구  '%s' → %s" % (record["request_text"], answer))
    functions.clear_pending()
    if answer.startswith(YES_WORDS):
        print()
        handle_turn(record["request_text"], log)
    else:
        print("진행 중이던 업무를 지웠습니다. 바뀐 것은 없습니다.")
        print()


def main():
    log = logger.setup(debug="--debug" in sys.argv)
    data_store.ensure()

    print("가상 금융 업무 에이전트")
    print("==== 종료하려면 exit 또는 종료를 입력하세요 ====")

    # 예약 이체 : 꺼져 있던 동안 시각이 지난 예약을 먼저 처리합니다.
    run_schedules(log)
    # 재시작 복구 : 지난번에 끝나기 전에 꺼진 업무가 있으면 먼저 묻습니다.
    recover_pending(log)

    # 실시간 스케줄러 : 켜 있는 동안 SCHEDULE_SECONDS 마다 예약 이체·분할 회차를 확인합니다.
    # daemon 스레드라 프로그램이 끝나면 같이 끝납니다.
    threading.Thread(target=scheduler_loop, args=(log,), daemon=True).start()

    while True:
        user_input = read_input()
        show_outbox()       # 입력을 기다리는 동안 스케줄러가 실행한 결과

        if user_input == "":
            continue

        if user_input in ["exit", "종료"]:
            stop_event.set()
            print("시스템을 종료합니다.")
            break

        handle_turn(user_input, log)


if __name__ == "__main__":
    main()
