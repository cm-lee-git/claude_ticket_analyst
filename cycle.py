from datetime import date, timedelta

ANCHOR = date(2026, 6, 8)  # 1회차 시작일 (월요일)


def get_cycle_bounds(n: int) -> tuple[date, date]:
    """n회차 시작일(월)과 종료일(금)을 반환. n은 1부터 시작."""
    start = ANCHOR + timedelta(days=(n - 1) * 14)
    end = start + timedelta(days=11)  # 월~금 = 5일, 다음 주 월~금 = 5일, 사이 주말 2일 → +11일
    return start, end


def get_cycle_number(target: date) -> int:
    """target 날짜가 속한 회차 번호를 반환. 앵커 이전이면 0."""
    if target < ANCHOR:
        return 0
    n = 1
    while True:
        start, end = get_cycle_bounds(n)
        if start <= target <= end:
            return n
        if target < start:
            return n - 1
        n += 1


def get_current_cycle() -> int:
    return get_cycle_number(date.today())


def get_active_cycle() -> int:
    """마감일의 24시가 지나지 않은 첫 번째 회차를 반환 (현재 진행 중 회차).
    회차 마감일 당일 자정이 지나면 다음 회차가 활성화됨.
    """
    today = date.today()
    n = 1
    while True:
        _, end = get_cycle_bounds(n)
        if end >= today:
            return n
        n += 1


def cycle_label(n: int) -> str:
    """회차 번호를 표시용 문자열로 변환. 0 → Pre-BRD."""
    return "Pre-BRD" if n == 0 else f"{n}회차"
