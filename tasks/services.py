"""
Business logic for tasks — kept out of models.py so it stays independently
testable and the model itself stays a thin record of fields.

See docs/architecture.md for the full write-up.
"""


def would_create_cycle(task, depends_on):
    """
    Return the cycle path (list of Task instances, starting and ending at
    `task`) if adding `task -> depends_on` would create a cycle, else None.

    Before saving TaskDependency(task=X, depends_on=Y): is X already
    reachable from Y? If yes, adding the edge closes a loop.

    Iterative DFS, walking forward from `depends_on`. `seen` is what makes a
    diamond (A->B, A->C, B->D, C->D) legal: D is reached by two routes, and
    without `seen` the second visit would look like a revisit.
    """
    seen = set()
    # Each stack entry carries the path taken to reach it, so a hit can
    # report the actual route rather than just the fact of a cycle.
    stack = [(depends_on, [depends_on])]

    while stack:
        current, path = stack.pop()
        if current.pk == task.pk:
            return [task, *path]
        if current.pk in seen:
            continue
        seen.add(current.pk)

        for dependency in current.dependencies.select_related("depends_on"):
            nxt = dependency.depends_on
            stack.append((nxt, [*path, nxt]))

    return None
