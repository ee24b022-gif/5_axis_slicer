
# F-074: Cancellation Endpoint

We have formalized cooperative job termination by exposing `POST /jobs/{job_id}/cancel`. 5-axis computations can be extremely long-running; this HTTP interface gives users immediate control to gracefully halt slicing sequences, releasing heavy machine resources without tearing down the existing partial history.

## Completed Changes
- **`backend/routers/jobs.py`**:
  - Bound the `POST /{job_id}/cancel` route.
  - Implemented the dual-action halt: 
    1. **Eager state mutation**: Reaches straight into the database via `JobLifecycle.cancel_job`, pushing the job into `CANCELLED`. If the DAG determines this job is already effectively terminating (`COMPLETE`, `FAILED`), an `InvalidTransitionError` effortlessly bubbles up to a `400 Bad Request` informing the user the job was already finalized.
    2. **Worker Interprocess Communication (IPC)**: Hooks directly onto our `LocalJobExecutor` to invoke `.cancel_job()`. This trips the thread-safe internal event loop, prompting the backend geometry application worker to halt instantly at its next safety checkpoint boundary (satisfying F-066 constraints).
- **`backend/tests/test_job_cancellation.py`**:
  - Orchestrated full API surface validation.
  - Confirmed the API safely ignores idempotent sequential triggers.
  - Asserted our robust lifecycle exceptions (400) automatically firewall users attempting to cancel successfully `COMPLETE` exports.
