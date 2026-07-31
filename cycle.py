from datetime import date, timedelta

ANCHOR = date(2025, 6, 8)  # 1회차 시작일 (월요일)


def _business_days_between(start: date, n: int, holidays: list[date]) -> date:
    """start 이후 n 영업일째 날짜를 반환 (start 당일 미포함)."""
    count = 0
    current = start
    while count < n:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in holidays:
            count += 1
    return current


def get_cycle_bounds(n: int, holidays: list[date] | None = None) -> tuple[date, date]:
    """n회차 시작일과 종료일을 반환. n은 1부터 시작."""
    if holidays is None:
        holidays = []
    start = ANCHOR + timedelta(days=(n - 1) * 14)
    end = _business_days_between(start, 10, holidays)
    return start, end


def get_cycle_number(target: date, holidays: list[date] | None = None) -> int:
    """target 날짜가 속한 회차 번호를 반환."""
    if holidays is None:
        holidays = []
    if target < ANCHOR:
        return 0
    n = 1
    while True:
        start, end = get_cycle_bounds(n, holidays)
        if start <= target <= end:
            return n
        if target < start:
            return n - 1
        n += 1


def get_current_cycle(holidays: list[date] | None = None) -> int:
    return get_cycle_number(date.today(), holidays)


def cycle_label(n: int) -> str:
    """회차 번호를 표시용 문자열로 변환. 0 → Pre-BRD."""
    return "Pre-BRD" if n == 0 else f"{n}회차"
