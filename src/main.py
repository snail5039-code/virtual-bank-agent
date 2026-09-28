# 사용자 입력을 반복해서 받고 응답을 출력합니다.
# 같은 대화 세션(thread_id)을 유지하고, 종료 명령을 처리합니다.
# 그래프가 질문하거나 승인을 기다리며 멈춰 있으면, 다음 입력을 그 답으로 넘깁니다. (분기 0)
# 멈춘 채 꺼졌다가 다시 켜면, 끊긴 업무를 알려주고 처음부터 다시 할지 묻습니다. (재시작 복구, 5-2)
#
# 실행 : uv run python src/main.py
#        uv run python src/main.py --debug   (로그를 화면에도 띄웁니다)

import getpass
import re
import sys
from datetime import datetime

from langgraph.types import Command
from rich.console import Console

import data_store
import functions
import logger
from agents.common.nodes import APPROVAL, QUESTION, SECRET, common_pending_check
from agents.supervisor.graph import bank_graph
from state import new_request

# 프로그램을 켤 때 세션 아이디를 하나 만들고, 끝날 때까지 이것만 씁니다.
thread_id = "session-" + datetime.now().strftime("%Y%m%d-%H%M%S")
config = {"configurable": {"thread_id": thread_id}}
console = Console()


def respond(user_input, log):
    # [분기 0] 멈춰 있는 업무가 있으면 입력을 그 답으로 넘기고, 없으면 새 요청으로 시작합니다.
    pending = common_pending_check(bank_graph, config)
    if pending == APPROVAL:
        log.interrupt_resume()
        result = bank_graph.invoke(Command(resume=user_input), config=config)
    elif pending in (QUESTION, SECRET):
        log.branch(0, "질문 대기 있음 → 답으로 재개")
        result = bank_graph.invoke(Command(resume=user_input), config=config)
    else:
        log.branch(0, "대기 중인 업무 없음 → 새 요청")
        result = bank_graph.invoke(new_request(user_input), config=config)

    if "__interrupt__" in result:
        return result["__interrupt__"][0].value["text"]     # 그래프가 던진 질문이나 처리안
    return result["answer"]


def turn_result():
    pending = common_pending_check(bank_graph, config)
    if pending == APPROVAL:
        return "승인 대기"
    if pending in (QUESTION, SECRET):
        return "질문 대기"
    return "완료"


def run_schedules(log):
    # 시각이 지난 예약 이체를 실행하고 결과를 화면에 알립니다. 그래프를 거치지 않습니다.
    # 승인은 예약할 때 받았기 때문입니다.
    # 여기서 예외가 나도 프로그램이 꺼지지 않게 막습니다. 예약은 다음 입력 때 다시 확인합니다.
    try:
        lines = functions.run_due_schedules()
    except Exception as e:
        log.error(e)
        lines = ["[예약 이체] 확인 중 오류가 나 처리하지 못했습니다. 다음 입력 때 다시 확인합니다."]
    for line in lines:
        log.note(line)
        print(line)


def read_input():
    # 본인 확인을 묻는 중이면 입력한 글자가 화면에 보이지 않게 받습니다.
    # 사람이 치는 터미널일 때만 가립니다. 확인 스크립트처럼 입력을 넣어 줄 때는 그대로 받습니다.
    prompt = "요청을 입력하세요 : "
    if common_pending_check(bank_graph, config) == SECRET and sys.stdin.isatty():
        return getpass.getpass(prompt).strip()
    return input(prompt).strip()


def remember_pending():
    # [재시작 복구] 턴이 끝났을 때 그래프가 승인·질문을 기다리고 있으면 진행 중 업무로 적어 두고,
    # 기다리는 것이 없으면(끝났으면) 지웁니다. 예약 이체처럼 data.json 에 남겨 켤 때 확인합니다.
    kind = common_pending_check(bank_graph, config)
    saved = functions.get_pending()
    if kind:
        snapshot = bank_graph.get_state(config)
        # 업무 이름은 멈출 때 보여준 처리안 제목에서 꺼냅니다. 예) "[이체 처리안]" → 이체
        # (처리안은 3단 그래프 안에 있어서 바깥 State 에는 아직 없습니다. 처리안 전 질문이면 분야 이름을 씁니다)
        title = re.search(r"\[(.+?) 처리안\]", snapshot.interrupts[0].value["text"])
        record = {
            "request_text": snapshot.values.get("request_text"),
            "task": title.group(1) if title else snapshot.values.get("domain"),
            "kind": "승인 대기" if kind == APPROVAL else "질문 대기",
        }
        if not saved or {k: saved.get(k) for k in record} != record:     # 같은 업무면 다시 쓰지 않습니다
            record["created_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            functions.set_pending(record)
    elif saved:
        functions.clear_pending()


def handle_turn(user_input, log):
    # 입력 한 번을 처리하고 답을 화면에 보여줍니다. 복구로 다시 돌릴 때도 이 함수를 씁니다.
    # 본인 확인 답(비밀번호 등)은 로그 파일에 그대로 남기지 않습니다.
    secret = common_pending_check(bank_graph, config) == SECRET
    log.turn_start("****" if secret else user_input, thread_id)
    # 예약 이체 : 요청을 처리하기 전에, 켜져 있는 동안 시각이 된 예약을 처리합니다.
    run_schedules(log)
    try:
        with console.status("[bold green]에이전트가 작업 중입니다...[/bold green]", spinner="dots"):
            answer = respond(user_input, log)
        try:
            remember_pending()
        except data_store.DataStoreError:
            pass    # 진행 중 기록을 못 남겨도 이번 답은 그대로 보여줍니다. (사유는 data_store 가 로그에 남깁니다)
        log.turn_end(turn_result())
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

    when = functions.parse_time(record["created_at"]).strftime("%m월 %d일 %H:%M")
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

    while True:
        user_input = read_input()

        if user_input == "":
            continue

        if user_input in ["exit", "종료"]:
            print("시스템을 종료합니다.")
            break

        handle_turn(user_input, log)


if __name__ == "__main__":
    main()
