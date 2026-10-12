import random
from itertools import combinations

import pytest

from app.domain.split import max_load, split_corridors


def best_possible(sizes: list[int], people: int) -> int:
    """Brute force: try every way to cut the corridors into contiguous blocks."""
    n = len(sizes)
    people = min(people, n)
    best = None
    for cuts in combinations(range(1, n), people - 1):
        bounds = [0, *cuts, n]
        load = max(sum(sizes[bounds[i] : bounds[i + 1]]) for i in range(people))
        best = load if best is None else min(best, load)
    return best


def test_two_people_get_balanced_blocks():
    assert split_corridors([3, 1, 1, 3], 2) == [0, 0, 1, 1]


def test_one_person_takes_everything():
    assert split_corridors([4, 2, 7], 1) == [0, 0, 0]


def test_more_people_than_corridors():
    assignment = split_corridors([5, 5], 4)

    assert assignment == [0, 1]  # nobody walks an empty route


def test_a_big_corridor_is_never_split():
    # 12 items in the first corridor: the best split leaves it alone with one person.
    assignment = split_corridors([12, 3, 3, 3], 2)

    assert assignment == [0, 1, 1, 1]
    assert max_load([12, 3, 3, 3], assignment) == 12


def test_no_corridors():
    assert split_corridors([], 3) == []


def test_rejects_zero_people():
    with pytest.raises(ValueError):
        split_corridors([1, 2], 0)


def test_matches_brute_force_on_random_stores():
    rng = random.Random(7)
    for _ in range(500):
        sizes = [rng.randint(1, 12) for _ in range(rng.randint(1, 9))]
        people = rng.randint(1, 5)

        assignment = split_corridors(sizes, people)

        assert assignment == sorted(assignment)  # contiguous blocks, in walking order
        assert len(set(assignment)) == min(people, len(sizes))  # everyone gets a block
        assert max_load(sizes, assignment) == best_possible(sizes, people)  # optimal
