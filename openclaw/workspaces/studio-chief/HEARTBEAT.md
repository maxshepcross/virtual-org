# Chief Heartbeat

Run this loop repeatedly:

1. Read `PRIORITY_MAP.md` and `AUTO_RESOLVER.md` as the decision lens for this pass.
2. Fetch current attention items.
3. Fetch current queued, blocked, and active tasks with `studio_tasks`.
4. Fetch current pending approvals.
5. Check recent briefings with `studio_recent_briefings` before composing a new brief so you do not repeat yourself.
6. Decide what is:
   - interrupt-worthy now
   - better for the next brief
   - safe to handle quietly
7. Run `studio_run_worker_once` to start one safe unit of queued work in the background when queued work can advance.
8. Use `studio_generate_briefing` when you need a fresh morning or evening summary rooted in current control-plane state.
9. Post any new approval or high-signal founder-facing item.
10. Suppress duplicates that were already posted into the same task thread or recent briefings.
11. Be quiet if nothing important changed.

Extra guidance:
- trends usually belong in the morning brief or evening wrap-up
- exceptions may justify interrupts
- prefer fewer, better messages
