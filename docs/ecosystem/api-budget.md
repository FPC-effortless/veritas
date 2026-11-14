# Bound model API requests

`trainlab.api_budget.ApiBudget` sends synchronous POSTs to one operator-chosen
HTTPS endpoint or loopback HTTP endpoint. It caps the number of attempts,
enforces minimum spacing between starts, and records redacted request
receipts. Use an endpoint that you control or are authorized to call.

```python
from trainlab.api_budget import ApiBudget

session = ApiBudget(
    endpoint="http://127.0.0.1:8080/infer",
    root="new-api-session",
    endpoint_sha256=deployment_digest,
    max_calls=20,
    min_interval=0.25,
    io_timeout=3,
    max_response_bytes=64 * 1024,
)
result = session.post(b"request payload")
```

Each POST consumes one attempt, including failures and explicit retries.
Only a prior observed failed response or a response size limit can be
linked via `retry_of`. The caller decides whether repeating the operation
is safe. There are no background retries, redirects, or refreshes.

The receipt keeps a caller-declared endpoint identity, request and response
byte counts, elapsed attempt times, status codes and retry links. It excludes
URLs, headers, credentials and payloads. Responses up to the configured
limit are returned to the caller as bytes. An oversized response returns
`RESPONSE_LIMIT` with the body withheld. A 2xx response indicates transport
success. Independently score the model output to establish correctness.

The meter saves intent before pacing or sending. A transport interruption,
truncation, timeout or an interim response exposed by the HTTP client leaves
the remote outcome unknown and seals the session. A receipt retained after
a crash preserves the attempt for inspection. Check the provider's records
before starting a replacement session.

Responses may use a single decimal content length or an end of stream.
Multiple length declarations and transfer encodings, including chunked
transfer, seal the session as unknown.

Call and pacing caps apply to this instance and one synchronous owner.
The I/O timeout is a socket timeout. DNS resolution, a slowly progressing
response, background server work and disk operations can outlast it. For hard
client elapsed limits, run the trusted client under the separate local command
supervisor, retaining the API receipt alongside that outer session's receipt.
Aggregate quotas, authenticated endpoint provenance, billing, token counts
and remote compute costs remain unmeasured.

Run the local endpoint controls with:

```bash
python -m unittest discover -s integrations/trainlab/tests -p test_api_budget.py
```
