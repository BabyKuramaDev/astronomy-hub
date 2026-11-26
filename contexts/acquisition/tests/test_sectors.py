import pytest

from contexts.acquisition.domain.sectors import consecutive_runs, select_sectors


def test_consecutive_runs() -> None:
    assert consecutive_runs([30, 2, 3, 29, 69]) == [[2, 3], [29, 30], [69]]


@pytest.mark.parametrize(
    ("available", "max_sectors", "expected"),
    [
        ([], 4, []),
        ([5], 4, [5]),
        ([1, 2, 3, 10], 4, [1, 2, 3]),
        ([2, 3, 29, 30], 4, [29, 30]),  # tie on length: the most recent run
        ([1, 2, 3, 4, 5, 6], 4, [3, 4, 5, 6]),  # longer than max: its most recent sectors
        ([5, 32, 59], 4, [59]),  # no consecutive sectors: the most recent one
        ([3, 1, 2, 2], 2, [2, 3]),  # unsorted and repeated input
        ([2, 3, 4, 29, 30, 31, 32], 3, [30, 31, 32]),
    ],
)
def test_select_sectors(available: list[int], max_sectors: int, expected: list[int]) -> None:
    assert select_sectors(available, max_sectors) == expected


def test_select_sectors_is_order_independent() -> None:
    assert select_sectors([30, 29, 3, 2], 4) == select_sectors([2, 3, 29, 30], 4)


def test_max_sectors_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        select_sectors([1], 0)


def test_single_sector_obs_ids() -> None:
    from contexts.acquisition.infrastructure.mast import single_sector_rows

    rows = [
        {"obs_id": "tess2018234235059-s0002-0000000100100827-0121-s", "sequence_number": 2},
        {"obs_id": "tess2018206190142-s0001-s0036-0000000100100827", "sequence_number": 36},
        {"obs_id": "tess2020238165205-s0029-0000000100100827-0193-a_fast", "sequence_number": 29},
        {"obs_id": "tess2018234235059-s0002-0000000100100827-0121-s", "sequence_number": 3},
    ]
    assert [r["sequence_number"] for r in single_sector_rows(rows)] == [2]
