# Security and data boundaries

Provider credentials and authoritative state belong only on the backend. The
Unity/WebGL client contains a public API origin and its private guest resume
credential, never provider keys. The backend reads explicit process environment;
it does not automatically load `.env`. Defaults disable provider calls. Keep
real secrets, databases, model weights, captures and logs out of source control.
Use [.env.example](../.env.example) only as a placeholder reference.

## State and ownership

- Guest access uses a random32-byte bearer token; SQL stores its hash, not the token.
- Ownership, expiry, revocation, expected revisions and transactional idempotency
  protect save reads/writes. Clearing browser storage loses guest recovery;
  cross-device/account recovery is not implemented.
- Movement, proximity, quest prerequisites and endings are validated by the engine.
  Model tools cannot execute code/SQL/shell commands or directly mutate game state.
- Safe errors and correlation IDs avoid echoing request bodies or provider headers.
  Do not add request-body, authorization-header or raw provider-response logging.
- Keep the last confirmed snapshot after failures. Retry uncertain requests with
  their original IDs; do not create uncontrolled duplicate operations.

## Local models and public service

Ollama must remain private on `127.0.0.1:11434`, with cloud inference disabled.
The authenticated backend is its client. A local model is not a public hosting
solution. There is no paid fallback when it is unavailable; expose a safe error
and preserve progress. Host capacity/concurrency require separate measurement.

Production configuration requires PostgreSQL and exact HTTPS client origins.
Use TLS, restricted database roles, safe proxy trust, isolated game origins,
appropriate CSP and private backups. Same-origin XSS can steal browser guest
tokens. Do not render untrusted HTML or expose a model listener to the Internet.
The in-memory IP/bearer limiter is per process; multiple instances need a shared
limiter or gateway. Model/daily provider budgets use shared SQL reservations.

## Cultural data and retention

Treat recommendations as aggregate affinities, not verified personal attributes
or proof of collaboration. Keep provider-supplied evidence distinct from original
fiction. Verify account allocation, billing, caching, transfer and redistribution
terms before enabling live calls or distributing captured data. Application
flags and limits do not establish permission or vendor quota.

SQL saves, receipts, model output and backups contain private progress/context.
SQLite files use restrictive permissions. Session expiry defaults to30 days;
access stops at expiry/revocation, but physical cleanup and backup retention are
operator responsibilities. Finalize retention and recovery procedures before a
public release. Snapshot hashes detect corruption, not a database administrator
who can change both data and hashes.

Pinned dependencies and automated tests are safeguards, not an independent
security audit. Review dependency advisories and the actual deployment before
publication. Do not commit credentials in a vulnerability report; redact tokens
and private payloads when reporting an issue to the repository maintainer.
