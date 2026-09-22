# 0-2 로그 동작 확인용입니다.
#
# 실행 :  uv run python 테스트/0-2_로그_확인.py
#         uv run python 테스트/0-2_로그_확인.py --debug
#
# 기본 실행하면 logs/ 에 오늘 날짜 파일이 생깁니다. 아래를 확인하세요.
#
#   1) 잘 끝난 턴은 한 줄 요약만 남는다
#   2) 실패하거나 예외가 난 턴만 전부 펼쳐진다
#   3) interrupt 재개 시 (재실행) 표시가 붙는다
#   4) 비밀번호 PIN 주민번호는 가려지고 카드번호 계좌번호는 남는다
#   5) 한글이 섞여도 칸이 맞는다
#   6) 파일이 1MB 를 넘으면 번호를 붙여 새 파일로 넘어간다
#
# --debug 를 붙이면 콘솔에도 뜨고 모든 턴이 펼쳐집니다.

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import logger as L

debug = "--debug" in sys.argv
log = L.setup(debug=debug)

print("로그 파일 :", log.path)
print("모드      :", "--debug (콘솔 출력 + 모든 턴 펼침)" if debug
      else "기본 (파일에만, 성공한 턴은 한 줄 요약)")
print()


# ============================================================ 1) 성공 - 승인 대기
# 요약 한 줄로만 남아야 합니다.
log.turn_start("생활비에서 저축으로 10만원 옮겨줘", thread_id="session-1")
log.branch(0, "승인 대기 없음 → 새 요청")

with log.node("supervisor"):
    time.sleep(0.12)                       # LLM 호출 흉내
    log.route(1, "계좌", "옮겨줘 / 계좌명")

with log.node("account_agent"):
    time.sleep(0.08)
    log.route(2, "이체")

with log.node("transfer_router"):
    time.sleep(0.10)
    log.route(3, "즉시")

with log.node("resolve_target"):
    log.resolve("생활비", 1, "acc-001")
    log.resolve("저축", 1, "acc-002")

with log.node("validate"):
    log.detail("OK  이체액 100,000 / 잔액 1,431,800")

with log.node("authenticate"):
    log.detail("세션 인증 있음 → 건너뜀")

with log.node("propose"):
    log.state_diff(
        {"from_account": "acc-001", "amount": 100000},
        {"from_account": "acc-001", "amount": 100000,
         "proposal": {"출금": "생활비", "입금": "저축", "금액": 100000}},
    )

with log.node("approve"):
    log.interrupt_pause("승인 대기")

log.turn_end("승인 대기")


# ============================================================ 2) 저장 실패 - 전부 펼쳐짐
# approve 가 다시 도는데 (재실행) 표시가 붙어야 합니다.
# 재실행된 노드에서 저장이나 기록이 일어나면 그건 버그입니다.
log.turn_start("응 진행해")
log.interrupt_resume("req-0003")

with log.node("approve"):
    log.detail("응답 해석 = 승인")

with log.node("revalidate"):
    log.detail("잔액 1,431,800 변동 없음 OK")

with log.node("transfer_execute"):
    log.balance("acc-001", 1431800, 1331800)
    log.balance("acc-002", 2280000, 2380000)
    log.detail("transactions +2 (tx-021 출금 / tx-022 입금)")

with log.node("save"):
    log.io("저장", "data/data.json", ok=False,
           error="PermissionError: 다른 프로그램이 사용 중")
    log.detail("롤백 → 변경 전 상태 유지")

with log.node("error_report"):
    log.detail('안내 "저장에 실패해 이체를 완료하지 못했습니다"')

log.turn_end("실패")


# ============================================================ 3) 마스킹 - 성공이라 요약
# 요약만 남으므로 마스킹을 눈으로 보려면 --debug 로 돌리세요.
log.turn_start("주민번호 뒷자리 1234567 이고 비밀번호는 1234야")
log.branch(0, "질문 대기 있음 → 인증 응답으로 해석")

with log.node("authenticate"):
    log.state_diff({}, {
        "user": {"name": "김도윤", "phone": "010-1234-5678",
                 "ssn_tail": "1234567", "pin": "1234"},
        "account_password": "1234",
        "card_password": "5555",
        "card_number": "0000-0000-0000-0005",
        "account_number": "110-001-100001",
        "authenticated": True,
    })

log.turn_end("완료")


# ============================================================ 4) 정상 저장
log.turn_start("여행 자금 계좌 이름을 휴가비로 바꿔줘")
log.branch(0, "승인 대기 없음 → 새 요청")

with log.node("supervisor"):
    log.route(1, "계좌")
with log.node("account_agent"):
    log.route(2, "설정")
with log.node("setting_router"):
    log.route(3, "이름")
with log.node("resolve_target"):
    log.resolve("여행 자금", 1, "acc-003")
with log.node("setting_execute"):
    log.state_diff({"nickname": "여행 자금"}, {"nickname": "휴가비"})
with log.node("save"):
    log.io("저장", "data/data.json", ok=True)

log.turn_end("완료")


# ============================================================ 5) 후보 여러 개
log.turn_start("생활비 카드 잠가줘")
log.branch(0, "승인 대기 없음 → 새 요청")

with log.node("supervisor"):
    log.route(1, "카드")
with log.node("card_agent"):
    log.route(2, "설정")
with log.node("resolve_target"):
    log.resolve("생활비 카드", 3)          # 소유자 필터를 안 걸면 3장이 걸립니다
with log.node("confirm_target"):
    log.detail("목록 제시 후 사용자 선택 대기")

log.turn_end("질문 대기")


# ============================================================ 6) 예외 - 전부 펼쳐짐
log.turn_start("카드 목록 보여줘")
with log.node("supervisor"):
    log.route(1, "카드")
try:
    with log.node("card_query"):
        log.detail("cards 읽는 중")
        raise KeyError("card_status")      # 없는 필드를 읽었다고 가정
except KeyError:
    pass
log.turn_end("실패")


# ============================================================ 7) 파일 회전
# 실제 1MB 를 채우면 오래 걸리므로 한도를 4KB 로 낮춰 따로 확인합니다.
rot_dir = ROOT / "logs" / "_회전확인"
if rot_dir.exists():
    for old in rot_dir.glob("*.log"):
        old.unlink()

rot = L.Logger(debug=False, log_dir=rot_dir, max_bytes=4096)
for i in range(1, 61):
    rot.turn_start("반복 요청 %d 번" % i)
    with rot.node("supervisor"):
        rot.route(1, "계좌")
    with rot.node("account_query"):
        rot.detail("계좌 목록 조회 결과를 길게 적어 파일을 채웁니다 " * 2)
    rot.turn_end("완료")

files = sorted(p.name for p in rot_dir.glob("*.log"))

print("확인할 것")
print("  1) 성공한 턴은 한 줄, 실패한 턴만 펼쳐졌는지")
print("  2) TURN 2 의 approve 에 (재실행) 이 붙었는지")
print("  3) 한글이 섞인 칸이 맞는지")
print()
print("로그 파일 :", log.path)
print()
print("파일 회전 (한도 4KB 로 낮춰 확인) :", rot_dir)
for name in files:
    print("   ", name, "%5d bytes" % (rot_dir / name).stat().st_size)
print("  → 파일이 2개 이상이면 회전 동작합니다.")
print()
if not debug:
    print("전체 내용을 보려면 : uv run python 테스트/0-2_로그_확인.py --debug")
