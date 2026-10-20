import random

import pytest

from app.services.shares import ShareError, ShareSlot, rebalance, validate_total


def slots(*shares, pinned=(), removed=()):
    return [ShareSlot(s, active=i not in removed, pinned=i in pinned) for i, s in enumerate(shares)]


# Scenarios from the reference video (campaign 93212).


def test_three_offers_remainder_goes_to_last():
    assert rebalance(slots(0, 0, 0)) == [33, 33, 34]


def test_adding_fourth_offer_gives_quarters():
    assert rebalance(slots(33, 33, 34, 0)) == [25, 25, 25, 25]


def test_adding_fifth_offer_gives_twenty_each():
    assert rebalance(slots(25, 25, 25, 25, 0)) == [20, 20, 20, 20, 20]


def test_removing_one_of_four():
    # 3749, 3717, 11111, 11112; 3717 removed -> 11112 (the last one) gets the extra 1%.
    assert rebalance(slots(25, 25, 25, 25, removed={1})) == [33, 0, 33, 34]


def test_pinned_offer_keeps_share_when_another_comes_back():
    # 11112 at 25%, 3717 pinned at 25%, 3749 brought back last -> 37 / 25 / 38.
    assert rebalance(slots(25, 25, 0, pinned={1})) == [37, 25, 38]


# Other cases


def test_single_offer_gets_everything():
    assert rebalance(slots(40)) == [100]


def test_no_active_offers():
    assert rebalance(slots(50, 50, removed={0, 1})) == [0, 0]


def test_remainder_spreads_over_several_last_offers():
    assert rebalance(slots(*[0] * 6)) == [16, 16, 17, 17, 17, 17]


def test_removed_offers_get_zero_and_do_not_take_remainder():
    assert rebalance(slots(10, 10, 10, removed={2})) == [50, 50, 0]


def test_several_pins():
    assert rebalance(slots(10, 20, 0, 0, pinned={0, 1})) == [10, 20, 35, 35]


def test_pins_over_100_are_rejected():
    with pytest.raises(ShareError):
        rebalance(slots(60, 50, 0, pinned={0, 1}))


def test_only_pinned_left_are_split_evenly():
    assert rebalance(slots(25, 30, 45, pinned={0, 1}, removed={2})) == [50, 50, 0]


def test_pins_can_take_all_100():
    assert rebalance(slots(70, 30, 0, pinned={0, 1})) == [70, 30, 0]


def test_random_inputs_always_sum_to_100():
    rnd = random.Random(7)
    for _ in range(500):
        n = rnd.randint(1, 12)
        items = [
            ShareSlot(rnd.randint(0, 30), active=rnd.random() > 0.2, pinned=rnd.random() < 0.2)
            for _ in range(n)
        ]
        try:
            result = rebalance(items)
        except ShareError:
            continue
        active = [r for r, s in zip(result, items, strict=True) if s.active]
        if active:
            assert sum(active) == 100
        assert all(r == 0 for r, s in zip(result, items, strict=True) if not s.active)


@pytest.mark.parametrize(
    ("shares", "ok"),
    [([100], True), ([33, 33, 34], True), ([50, 49], False), ([], False), ([120, -20], False)],
)
def test_validate_total(shares, ok):
    if ok:
        validate_total(shares)
    else:
        with pytest.raises(ShareError):
            validate_total(shares)
