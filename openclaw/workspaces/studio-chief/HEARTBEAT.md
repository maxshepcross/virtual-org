# Chief Heartbeat

Run this loop repeatedly:

1. Fetch current attention items.
2. Fetch current pending approvals.
3. Run `studio_run_worker_once` to start one safe unit of queued work in the background.
4. Post any new `notify` or `approval_required` items.
5. Suppress duplicates that were already posted into the same task thread.
6. Be quiet if nothing important changed.
