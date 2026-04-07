# Studio Priority Map

Purpose: define which studio tasks should move first when time, attention, or worker capacity is limited.

This file is the decision layer for urgency.

## Priority Levels

- `P0` - interrupt now
  Use for security problems, production outages, payment failures, blocked launches, or work that risks customer trust today.
- `P1` - same day
  Use for high-value product work, time-sensitive bug fixes, or tasks blocking a named target repo.
- `P2` - next planned slot
  Use for useful but non-urgent improvements, internal tooling, and cleanup work.
- `P3` - batch or defer
  Use for vague ideas, nice-to-have docs, and tasks that need more shaping before action.

## Routing Rules

1. If a task touches money, authentication, customer data, or production reliability, raise its urgency by one level.
2. If a task names a target repo that is not in `ALLOWED_REPOS`, stop instead of guessing.
3. If a task is broad enough to create multiple plausible implementation paths, treat it as shaping work first.
4. If a task can be completed without touching a target repo, prefer handling it in the studio control plane.
5. If a task is blocked on missing requirements, request the smallest possible clarification instead of inventing scope.

## Output Bias

- Prefer small, testable next steps over large speculative plans.
- Prefer explicit repo-safe actions over general advice.
- Prefer one useful recommendation over a long menu of options.
