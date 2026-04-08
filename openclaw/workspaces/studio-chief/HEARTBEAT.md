# Chief Heartbeat

Run this loop repeatedly:

1. Fetch current attention items.
2. Fetch current pending approvals.
3. Post any new `notify` or `approval_required` items.
4. Suppress duplicates that were already posted into the same task thread.
5. Be quiet if nothing important changed.
