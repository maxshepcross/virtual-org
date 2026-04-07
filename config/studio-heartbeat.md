# Studio Heartbeat

Purpose: define the recurring control-plane checks that keep studio work moving.

This file is the recurring operations layer.

## Heartbeat Order

1. Read the studio priority map.
2. Read the auto-resolution policy.
3. Check for stale leased tasks and fail them if needed.
4. Check for queued tasks that can move into research safely.
5. Check active implementations for timeouts, blocked tests, or repo mismatches.
6. Refresh PR status when work has already been pushed.
7. Send one short update only if there is new information, a blocker, or a decision needed.

## Rules

- Keep this file short. It should describe order, not duplicate detailed procedures.
- Prefer quiet, useful progress over noisy status chatter.
- If there is no action worth taking, do nothing.
- Update the real source of truth in the same pass when you act.
