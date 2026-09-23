# 사용자 입력을 반복해서 받고 응답을 출력합니다.
# 같은 대화 세션(thread_id)을 유지하고, 종료 명령을 처리합니다.
#
# 실행 : uv run python src/main.py
#        uv run python src/main.py --debug   (로그를 화면에도 띄웁니다)

import sys
from datetime import datetime

import data_store
import logger
from agents.supervisor.graph import bank_graph

# 프로그램을 켤 때 세션 아이디를 하나 만들고, 끝날 때까지 이것만 씁니다.
thread_id = "session-" + datetime.now().strftime("%Y%m%d-%H%M%S")
config = {"configurable": {"thread_id": thread_id}}


def respond(user_input):
    result = bank_graph.invoke({"query": user_input}, config=config)
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
            answer = respond(user_input)
            log.turn_end("완료")
        except Exception as e:
            log.error(e)
            log.turn_end("오류")
            answer = "처리 중 오류가 발생했습니다."

        print(answer)
        print()


if __name__ == "__main__":
    main()
