# 실행 로그를 남깁니다. 기획서 7장을 따릅니다.
# 턴, 라우팅, 노드, state 변경, 이름 해소, 파일 입출력, interrupt, 예외를 기록합니다.
#
# 턴 단위로 모았다가 끝날 때 한꺼번에 씁니다.
#   잘 끝난 턴  : 한 줄 요약만 남깁니다.
#   터진 턴     : 전부 펼칩니다. 그래서 문제가 생긴 턴만 눈에 띕니다.
#   --debug     : 콘솔에도 띄우고, 모든 턴을 펼칩니다.
#
# 줄 앞 기호
#   >  노드가 정상으로 지나감
#   X  실패하거나 예외가 남
#   #  interrupt 로 멈춤
# 기호는 ASCII 만 씁니다. 유니코드 기호는 폰트에 따라 두 칸으로 그려져
# 이어지는 줄과 칸이 어긋납니다. 같은 이유로 한글이 섞인 칸은 폭을 직접 셉니다.
#
# 파일은 날짜별로 만들고 1MB 를 넘으면 번호를 붙여 새 파일로 넘어갑니다.
#   logs/2026-09-22.log  →  logs/2026-09-22.2.log  →  ...
# 한 턴은 쪼개지 않고 통째로 한 파일에 들어갑니다.

from __future__ import annotations

import time
import traceback
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
MAX_BYTES = 1024 * 1024        # 파일 하나의 최대 크기
MAX_BUFFER = 3000              # 한 턴이 이보다 길어지면 뒤를 잘라냅니다

# 로그에 값을 그대로 남기지 않을 필드
MASK_FULL = {"account_password", "card_password", "pin", "password"}
MASK_TAIL = {"ssn_tail"}
MASK_PHONE = {"phone"}

# 이 결과로 끝난 턴은 요약하지 않고 전부 펼칩니다
FAIL_RESULTS = {"실패", "불가", "오류", "예외", "중단"}

# 줄 맞춤. 머리말은 "  " + 기호 + " " + 이름 + " " + 소요시간 + "   " 이다.
_NAME_W = 22
_TIME_W = 5
_DETAIL_COL = 2 + 1 + 1 + _NAME_W + 1 + _TIME_W + 3


# ---------------------------------------------------------------- 글자 폭
def _width(text) -> int:
    """한글은 두 칸을 차지하므로 실제 폭을 셉니다."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1
               for ch in str(text))


def _pad(text, columns: int) -> str:
    """오른쪽을 채워 지정한 폭으로 만듭니다."""
    return str(text) + " " * max(0, columns - _width(text))


def _short(text, columns: int) -> str:
    """요약 줄에 넣을 만큼만 자릅니다."""
    text = str(text).replace("\n", " ")
    if _width(text) <= columns:
        return text
    out = ""
    for ch in text:
        if _width(out) + _width(ch) > columns - 3:
            break
        out += ch
    return out + "..."


# ---------------------------------------------------------------- 마스킹
def _mask_value(key: str, value):
    """필드 이름을 보고 가릴지 판단합니다."""
    if value is None:
        return None
    if key in MASK_FULL:
        return "****"
    if key in MASK_TAIL:
        return "*" * len(str(value))
    if key in MASK_PHONE:
        parts = str(value).split("-")
        if len(parts) == 3:
            return "%s-****-%s" % (parts[0], parts[2])
        return "****"
    return mask(value)


def mask(value):
    """dict 와 list 안을 돌며 가려야 할 값을 바꿉니다.

    카드 번호와 계좌번호는 가리지 않습니다.
    어느 대상을 잡았는지 추적하는 데 필요하고, 가상 데이터이기 때문입니다.
    문자열을 직접 만들어 넘기면 가려지지 않으므로, 값은 dict 로 넘기는 편이 안전합니다.
    """
    if isinstance(value, dict):
        return {k: _mask_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v) for v in value]
    return value


def _fmt(value) -> str:
    """로그 한 줄에 넣을 값을 짧게 만듭니다."""
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, int):
        return "{:,}".format(value)
    if value is None:
        return "없음"
    if isinstance(value, (dict, list)):
        text = str(mask(value))
        return text if len(text) <= 100 else text[:97] + "..."
    return str(value)


# ---------------------------------------------------------------- 노드 버퍼
class _Node:
    """노드 하나의 출력 버퍼입니다.

    소요 시간은 노드가 끝나야 알 수 있으므로, 첫 줄을 바로 쓰지 않고
    모아 두었다가 빠져나갈 때 한꺼번에 넘깁니다.
    """

    def __init__(self, logger: "Logger", name: str, rerun: bool):
        self.logger = logger
        self.name = name
        self.rerun = rerun
        self.details: list[str] = []
        self.mark = ""
        self.started = time.perf_counter()

    def detail(self, text: str) -> None:
        self.details.append(text)

    def flush(self) -> None:
        elapsed = time.perf_counter() - self.started
        label = self.name + ("  (재실행)" if self.rerun else "")
        shown = "%.2fs" % elapsed if elapsed >= 0.01 else ""
        head = "  %s %s %s   " % (
            self.mark or ">", _pad(label, _NAME_W), shown.rjust(_TIME_W))
        if not self.details:
            self.logger._line(head.rstrip())
            return
        self.logger._line(head + self.details[0])
        for line in self.details[1:]:
            self.logger._line(" " * _DETAIL_COL + line)


# ---------------------------------------------------------------- 본체
class Logger:
    def __init__(self, debug: bool = False, log_dir: Path = LOG_DIR,
                 max_bytes: int = MAX_BYTES):
        self.debug = debug
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

        self._turn = 0
        self._turn_started = None
        self._stack: list[_Node] = []

        # 턴 단위 버퍼
        self._buffer: list[str] = []
        self._in_turn = False
        self._force_full = False
        self._route: list[str] = []
        self._input = ""
        self._stamp = ""
        self._thread = ""
        self._cut = False

        # 재실행 판정용. 지금 처리 중인 업무에서 이미 지나간 노드들
        self._ran: set[str] = set()
        self._before_interrupt: set[str] = set()

        # 파일 회전
        self._date = ""
        self._index = 1
        self._file: Path | None = None
        self._size = 0

    # ------------------------------------------------------------ 파일
    def _name(self, date: str, index: int) -> Path:
        tail = "" if index == 1 else ".%d" % index
        return self.log_dir / ("%s%s.log" % (date, tail))

    def _pick_file(self, need: int) -> None:
        """이번에 쓸 파일을 고릅니다. 꽉 찼으면 다음 번호로 넘어갑니다."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._date:
            # 날짜가 바뀌었으면 오늘의 마지막 파일을 찾아 이어 씁니다.
            self._date = today
            self._index = 1
            while self._name(today, self._index + 1).exists():
                self._index += 1
            self._file = self._name(today, self._index)
            self._size = self._file.stat().st_size if self._file.exists() else 0
        # 이번에 쓸 양을 더해 한도를 넘으면 새 파일로 넘어갑니다.
        # 빈 파일이면 한 덩어리가 아무리 커도 그냥 씁니다. 턴은 쪼개지 않습니다.
        if self._size > 0 and self._size + need > self.max_bytes:
            self._index += 1
            self._file = self._name(self._date, self._index)
            self._size = 0

    def _emit(self, lines: list[str]) -> None:
        """한 덩어리를 파일에 씁니다. 덩어리는 쪼개지 않습니다."""
        if not lines:
            return
        blob = "\n".join(lines) + "\n"
        data = blob.encode("utf-8")
        self._pick_file(len(data))
        with open(self._file, "ab") as f:
            f.write(data)
        self._size += len(data)
        if self.debug:
            print(blob, end="")

    def _line(self, text: str) -> None:
        """턴 안이면 모아 두고, 턴 밖이면 바로 씁니다."""
        if not self._in_turn:
            self._emit([text])
            return
        if len(self._buffer) < MAX_BUFFER:
            self._buffer.append(text)
        elif not self._cut:
            self._buffer.append("  ... 너무 길어 이후 줄은 생략합니다")
            self._cut = True

    @property
    def path(self) -> Path:
        """지금 쓰고 있는 로그 파일입니다."""
        self._pick_file(0)
        return self._file

    # ------------------------------------------------------------ 턴
    def turn_start(self, text: str, thread_id: str = "") -> None:
        self._turn += 1
        self._turn_started = time.perf_counter()
        self._stamp = datetime.now().strftime("%H:%M:%S")
        self._input = text
        self._thread = thread_id
        self._buffer = []
        self._in_turn = True
        self._force_full = False
        self._route = []
        self._cut = False

    def turn_end(self, result: str) -> None:
        elapsed = time.perf_counter() - self._turn_started if self._turn_started else 0
        self._in_turn = False
        full = self.debug or self._force_full or result in FAIL_RESULTS

        if full:
            head = "━━━ TURN %d   %s" % (self._turn, self._stamp)
            if self._thread:
                head += "   thread=%s" % self._thread
            lines = ["", head + " ━━━", '입력  "%s"' % self._input, ""]
            lines += self._buffer
            lines.append("━━━ 턴 종료 (%s)  %.2fs" % (result, elapsed))
            self._emit(lines)
        else:
            path = ">".join(self._route) if self._route else "-"
            self._emit(["TURN %3d  %s  %7s  %s %s  \"%s\"" % (
                self._turn, self._stamp, "%.2fs" % elapsed,
                _pad(result, 10), _pad(_short(path, 24), 24),
                _short(self._input, 46))])

        self._buffer = []
        # 업무가 끝났으면 재실행 판정 기준을 비웁니다.
        if result not in ("승인 대기", "질문 대기"):
            self._ran.clear()
            self._before_interrupt.clear()

    # ------------------------------------------------------------ 분기
    def branch(self, number: int, text: str) -> None:
        self._line("  [분기%d] %s" % (number, text))

    # ------------------------------------------------------------ 노드
    @contextmanager
    def node(self, name: str):
        """노드 하나를 감쌉니다. 소요 시간을 재고 예외를 기록합니다."""
        item = _Node(self, name, rerun=name in self._before_interrupt)
        self._stack.append(item)
        self._ran.add(name)
        try:
            yield item
        except Exception as exc:
            item.mark = "X"
            item.detail("예외 %s: %s" % (type(exc).__name__, exc))
            item.flush()
            self._stack.pop()
            self.error(exc)
            raise
        else:
            item.flush()
            self._stack.pop()

    def detail(self, text: str) -> None:
        """현재 노드에 한 줄 덧붙입니다. 노드 밖이면 그냥 씁니다."""
        if self._stack:
            self._stack[-1].detail(text)
        else:
            self._line(" " * _DETAIL_COL + text)

    # ------------------------------------------------------------ 기록 종류
    def route(self, level: int, chosen: str, reason: str = "") -> None:
        self._route.append(chosen)
        text = "%d단 = %s" % (level, chosen)
        if reason:
            text += "   (근거: %s)" % reason
        self.detail(text)

    def resolve(self, word: str, count: int, result=None) -> None:
        if count == 1:
            self.detail('"%s" 후보 1 → %s' % (word, result))
        elif count == 0:
            self.detail('"%s" 후보 없음 → 불가' % word)
        else:
            self.detail('"%s" 후보 %d → 사용자 확인 필요' % (word, count))

    def state_diff(self, before: dict, after: dict) -> None:
        """바뀐 필드만 남깁니다."""
        changed = []
        for key in after:
            old, new = before.get(key), after[key]
            if old == new:
                continue
            if key not in before or old is None:
                changed.append("state +%s = %s" % (key, _fmt(_mask_value(key, new))))
            else:
                changed.append("state %s: %s → %s" % (
                    key, _fmt(_mask_value(key, old)), _fmt(_mask_value(key, new))))
        for key in before:
            if key not in after:
                changed.append("state -%s" % key)
        for line in changed:
            self.detail(line)
        if not changed:
            self.detail("state 변경 없음")

    def balance(self, account_id: str, before: int, after: int) -> None:
        self.detail("%s  %s → %s" % (account_id, _fmt(before), _fmt(after)))

    def io(self, action: str, path, ok: bool = True, error: str = "") -> None:
        name = Path(path).name
        if ok:
            self.detail("%s %s" % (action, name))
        else:
            self._force_full = True          # 저장이 실패한 턴은 전부 펼칩니다
            if self._stack:
                self._stack[-1].mark = "X"
            self.detail("%s 실패  %s: %s" % (action, name, error))

    def interrupt_pause(self, reason: str = "승인 대기") -> None:
        if self._stack:
            self._stack[-1].mark = "#"
            self._stack[-1].detail("INTERRUPT  " + reason)
        else:
            self._line("  # INTERRUPT  " + reason)
        # 지금까지 지나온 노드를 기억해 둡니다. 재개하면 이들이 다시 돕니다.
        self._before_interrupt = set(self._ran)

    def interrupt_resume(self, request_id: str = "") -> None:
        self._route.append("재개")
        tag = " (%s)" % request_id if request_id else ""
        self.branch(0, "승인 대기 있음%s → 재개" % tag)

    def error(self, exc: BaseException, state: dict | None = None) -> None:
        self._force_full = True              # 예외가 난 턴은 전부 펼칩니다
        self._line("  X 예외  %s: %s" % (type(exc).__name__, exc))
        if state is not None:
            self._line(" " * _DETAIL_COL + "state %s" % _fmt(mask(state)))
        for line in traceback.format_exc().rstrip().splitlines():
            self._line("      " + line)

    def note(self, text: str) -> None:
        """노드에 속하지 않는 한 줄 메모입니다."""
        self._line("  " + text)

    def expand(self) -> None:
        """이 턴은 요약하지 말고 전부 펼치라고 표시합니다."""
        self._force_full = True


# ---------------------------------------------------------------- 전역 하나
_logger: Logger | None = None


def setup(debug: bool = False, log_dir: Path = LOG_DIR,
          max_bytes: int = MAX_BYTES) -> Logger:
    """프로그램 시작 시 한 번 부릅니다."""
    global _logger
    _logger = Logger(debug=debug, log_dir=log_dir, max_bytes=max_bytes)
    return _logger


def get_logger() -> Logger:
    """setup 을 안 했으면 콘솔 출력 없이 기본값으로 만듭니다."""
    global _logger
    if _logger is None:
        _logger = Logger()
    return _logger
