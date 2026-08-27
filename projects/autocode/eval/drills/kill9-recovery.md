# Kill-9 recovery drill

1. Create a session and append a user event.
2. Stop the process after the journal flush but before projection.
3. Restart and replay the journal into the SQLite projection.
4. Compare the acknowledged event ids before and after restart.

The invariant is zero acknowledged event loss. A duplicate projection is
recoverable only when the event's idempotency key makes replay harmless.
