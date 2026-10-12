"""Split a shopping route between people (the linear partition problem).

Corridors are walked in order. Each person gets one block of neighboring corridors,
a corridor is never split between two people, and the busiest person should have as
few items as possible.
"""


def split_corridors(sizes: list[int], people: int) -> list[int]:
    """Assign each corridor (in walking order) to a person, in contiguous blocks.

    `sizes[i]` is the number of items in corridor i. Returns, for each corridor, the index
    of the person who takes it (0 for the first block, 1 for the second...). Minimizes the
    largest number of items any one person gets; with ties, earlier people take less.

    Dynamic programming over (corridors, people): O(n^2 * k), tiny for a grocery store
    (n <= 60 corridors, k <= 10 people).

    >>> split_corridors([3, 1, 1, 3], 2)
    [0, 0, 1, 1]
    """
    if people < 1:
        raise ValueError("people must be at least 1")
    n = len(sizes)
    if n == 0:
        return []
    people = min(people, n)  # more people than corridors: some get nothing

    prefix = [0]
    for size in sizes:
        prefix.append(prefix[-1] + size)

    def load(start: int, end: int) -> int:
        return prefix[end] - prefix[start]

    inf = float("inf")
    # best[k][i]: smallest possible max load splitting the first i corridors among k people
    best = [[inf] * (n + 1) for _ in range(people + 1)]
    cut = [[0] * (n + 1) for _ in range(people + 1)]
    best[0][0] = 0
    for k in range(1, people + 1):
        for i in range(1, n + 1):
            # The k-th person takes corridors j..i-1 (at least one corridor each).
            for j in range(k - 1, i):
                candidate = max(best[k - 1][j], load(j, i))
                # "<=" prefers the latest cut: the last person takes fewer corridors,
                # so with ties the earlier people get more.
                if candidate <= best[k][i]:
                    best[k][i] = candidate
                    cut[k][i] = j

    assignment = [0] * n
    end = n
    for k in range(people, 0, -1):
        start = cut[k][end]
        for corridor in range(start, end):
            assignment[corridor] = k - 1
        end = start
    return assignment


def max_load(sizes: list[int], assignment: list[int]) -> int:
    """Largest number of items any one person gets (used by tests and diagnostics)."""
    loads: dict[int, int] = {}
    for size, person in zip(sizes, assignment, strict=True):
        loads[person] = loads.get(person, 0) + size
    return max(loads.values(), default=0)
