"""Share distribution for offers in a stream, as the reference editor does it.

Pinned active offers keep their share. What is left of 100% is split evenly between the
other active offers; the rounding remainder goes one percent at a time to the last of them
in the order they were added (3 offers -> 33/33/34). Removed offers get 0.
"""

from dataclasses import dataclass

TOTAL = 100


class ShareError(ValueError):
    pass


@dataclass(frozen=True)
class ShareSlot:
    share: int
    active: bool = True
    pinned: bool = False


def rebalance(slots: list[ShareSlot]) -> list[int]:
    """Return new shares for the slots, in the same order (the order of adding)."""
    active = [i for i, s in enumerate(slots) if s.active]
    pinned = [i for i in active if slots[i].pinned]
    free = [i for i in active if not slots[i].pinned]

    result = [0] * len(slots)
    if not active:
        return result

    if not free:
        # Only pinned offers are left: the pins cannot all hold, so split evenly between them.
        free, pinned = active, []

    pinned_total = sum(slots[i].share for i in pinned)
    if pinned_total > TOTAL:
        raise ShareError(f"Закреплённые доли дают {pinned_total}%, больше {TOTAL}%")

    for i in pinned:
        result[i] = slots[i].share

    base, remainder = divmod(TOTAL - pinned_total, len(free))
    for n, i in enumerate(free):
        result[i] = base + (1 if n >= len(free) - remainder else 0)
    return result


def validate_total(shares: list[int]) -> None:
    if not shares:
        raise ShareError("В потоке должен остаться хотя бы один активный оффер")
    if any(s < 0 or s > TOTAL for s in shares):
        raise ShareError("Доля должна быть от 0 до 100")
    total = sum(shares)
    if total != TOTAL:
        raise ShareError(f"Сумма долей {total}%, а должна быть {TOTAL}%")
