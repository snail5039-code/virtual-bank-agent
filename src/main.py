# 사용자 입력을 반복해서 받고 응답을 출력합니다.
# 같은 대화 세션(thread_id)을 유지하고, 종료 명령을 처리합니다.
# 그래프가 질문하고 멈춰 있으면, 다음 입력을 그 질문의 답으로 넘깁니다.
#
# 실행 : uv run python src/main.py
#        uv run python src/main.py --debug   (로그를 화면에도 띄웁니다)

import sys
from datetime import datetime

from langgraph.types import Command
from rich.console import Console

import data_store
import logger
from agents.supervisor.graph import bank_graph
from state import new_request

# 프로그램을 켤 때 세션 아이디를 하나 만들고, 끝날 때까지 이것만 씁니다.
thread_id = "session-" + datetime.now().strftime("%Y%m%d-%H%M%S")
config = {"configurable": {"thread_id": thread_id}}
console = Console()


def is_waiting():
    # 그래프가 질문하고 멈춰 있으면 다음에 실행할 노드가 남아 있습니다.
    return bool(bank_graph.get_state(config).next)


def respond(user_input):
    if is_waiting():
        # 멈춘 자리에서 이어갑니다. 입력은 질문에 대한 답입니다.
        result = bank_graph.invoke(Command(resume=user_input), config=config)
    else:
        # 새 요청입니다.
        result = bank_graph.invoke(new_request(user_input), config=config)

    if "__interrupt__" in result:
        return result["__interrupt__"][0].value     # 그래프가 던진 질문
    return result["answer"]


def main():
    log = logger.setup(debug="--debug" in sys.argv)
    data_store.ensure()

    print("가상 금융 업무 에이전트")
    print("==== 종료하려면 exit 또는 종료를 입력하세요 ====")

    while True:
        user_input = input("요청을 입력하세요 : ").strip()

        if user_input == "":
            continue

        if user_input in ["exit", "종료"]:
            print("시스템을 종료합니다.")
            break

        log.turn_start(user_input, thread_id)
        try:
            with console.status("[bold green]에이전트가 작업 중입니다...[/bold green]", spinner="dots"):
                answer = respond(user_input)
            log.turn_end("질문 대기" if is_waiting() else "완료")
        except Exception as e:
            log.error(e)
            log.turn_end("오류")
            answer = "처리 중 오류가 발생했습니다."

        print(answer)
        print()


if __name__ == "__main__":
    main()
