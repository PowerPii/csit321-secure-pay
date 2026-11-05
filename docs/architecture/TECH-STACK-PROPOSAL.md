# Secure Online Payment Gateway — proposed technology stack

Prepared 20 October 2026. Status: architecture recommendation for team review, not an approved requirement or an implemented system.

## 1. Recommendation and assumptions

Use **React + TypeScript for the interfaces; Django + Django REST Framework for the application backends; PostgreSQL for durable records; Python/scikit-learn for fraud experiments; and Docker Compose + Caddy for deployment and HTTPS**.

Build the gateway as one modular application with a separate worker process. Deploy the merchant and processing simulator as separate applications with their own databases and credentials. They may use the same backend framework to reduce the number of technologies the team must learn.

This recommendation assumes a small student team, a browser-based demonstration, limited hosting budget and no strong existing preference for a different backend. Team experience and assessment hosting requirements have not been established. If most backend developers already know another mature framework well, revisit Django before implementation; preserve the ownership boundaries and correctness rules.

The baseline is the current Chapters 1–3 and the October 11 handover decisions. The project uses fictional funds and synthetic payment credentials. It includes registered and guest checkout, hosted checkout, merchant and internal interfaces, fraud screening, full and multiple partial refunds, and recovery from ambiguous outcomes. Existing report and research files have not been edited.

## 2. Complete stack

| Layer | Proposed choice | Responsibility and rationale |
|---|---|---|
| Frontend language | TypeScript | Typed API contracts and payment-state handling |
| Frontend application | React with Vite | Gateway interfaces and a small separate merchant storefront; no identified need for server-side rendering |
| Routing and server state | React Router and TanStack Query | Role-specific navigation, API caching and status polling; backend remains authoritative |
| UI components | Material UI | Reusable forms, tables, dialogs and accessible interaction foundations; still test keyboard use and error handling |
| Backend language | Python | One language for payment application logic, experiments and model inference |
| Gateway framework | Django 5.2 LTS with Django REST Framework | Account lifecycle, sessions, permissions, ORM, migrations and HTTP APIs |
| Backend serving | Gunicorn behind Caddy | Run the Django application in deployment; use a separate worker process for durable asynchronous work |
| Merchant backend | Separate Django/DRF application | Own products, authoritative prices, orders, notification receipt and fulfilment |
| Processing simulator | Separate Django/DRF application | Own fictional authorisation, capture, cancellation and refund effects, stable operation identities and controlled faults |
| Database | PostgreSQL | Transactions, uniqueness constraints and locking for payment operations and refund reservations |
| Data access | Django ORM and migrations | Explicit transactional services; inspect generated queries for locking-sensitive paths |
| Background processing | PostgreSQL outbox/job tables and a Django management-command worker | Durable notifications, reconciliation and bounded retry scheduling without adding a broker initially |
| Human authentication | Django server-side sessions and password-reset facilities; Argon2 password hashing | Customer and staff account lifecycle with HttpOnly, Secure, host-only cookies and CSRF protection |
| Service authentication | Scoped high-entropy API keys over HTTPS | Merchant-to-gateway and gateway-to-simulator authentication; store inbound verification digests, support revocation |
| Notification integrity | HMAC-SHA256 signatures | Sign exact body bytes plus timestamp/event identity; verify authenticity, time tolerance and durable deduplication |
| API specification | OpenAPI with drf-spectacular | Document requests, responses, errors, state semantics and retry contracts; generate TypeScript types |
| Research and preparation | JupyterLab, pandas, NumPy and PyArrow/Parquet | Inspect IEEE-CIS, build chronological datasets and retain reproducible derived data |
| Fraud modelling | scikit-learn; logistic regression and HistGradientBoostingClassifier as initial candidates | A simple baseline and a tree-based candidate; final selection depends on feature feasibility and experiments |
| Experiment records | Versioned configurations, dependency locks, data hashes and saved results | Reproduce splits, feature recipes, seeds, metrics and model artifacts without requiring an experiment server |
| Research charts | Matplotlib | Precision–recall curves, threshold comparisons and latency/results figures |
| Backend tests | pytest, pytest-django and Hypothesis | API, access-control, state-transition, invariant and concurrency tests against PostgreSQL |
| Frontend tests | Vitest, React Testing Library and Playwright | Component behaviour and complete registered, guest and operator workflows |
| Performance tests | Locust | Measure screening and request percentiles, workload behaviour and recovery under declared conditions |
| Security checks | OWASP ZAP, pip-audit, npm audit and secret scanning | Supplement explicit ownership and permission tests; scans alone do not establish security |
| Diagnostics | Structured JSON logs and database-backed audit events | Correlate requests, operations, decisions and notifications; keep secrets out of evidence |
| Runtime and packaging | Docker Engine/compatible runtime and Docker Compose | Repeatable local stack and an initial single-server demonstration |
| HTTPS | Caddy with public certificates remotely and a trusted local CA in development | HTTPS across browser and service trust boundaries |
| Local email | Mailpit through Django's SMTP backend | Exercise registration/recovery emails using test accounts without needing a live email provider |
| Collaboration and CI | Git/GitHub and GitHub Actions | Review changes; run formatting, tests, migrations checks, builds and dependency checks |
| Code quality | Ruff for Python; ESLint/Prettier and TypeScript checks for frontend | Consistent code and early detection of common errors |

Pin exact compatible package and container versions when bootstrapping, commit lockfiles and record image identifiers for assessed runs. Django 5.2 is deliberately an LTS baseline; its documented extended-support window reaches April 2028. Do not interpret the table as a tested dependency matrix. [Django support information](https://www.djangoproject.com/download/)

React documents Vite as an option for constructing an application from scratch, while explaining the need to choose routing and data-fetching tools. That tradeoff is acceptable here because Django owns the backend. [React application guidance](https://react.dev/learn/build-a-react-app-from-scratch)

## 3. Application boundaries and deployment

| Application | Interfaces | Owned records |
|---|---|---|
| Merchant | Storefront and order backend | Products, order amounts, payment references, received events and fulfilment |
| Gateway | Hosted checkout, customer area, merchant dashboard, shared administrator/analyst interface, integration API | Accounts, merchant memberships, guest entitlements, payment/refund state, risk decisions, outgoing events and audit trail |
| Simulator | Private processing/status API and test-only fault controls | Stable operation records and authoritative fictional effects |
| Training environment | Notebooks and repeatable batch scripts | Dataset audit, chronological partitions, fitted preprocessing, model versions and evaluation outputs |

The browser goes from merchant checkout to gateway-hosted checkout. The merchant backend creates a payment with its server-side credential and authoritative amount. The gateway screens it, contacts the simulator and persists the resulting evidence. The merchant confirms an outcome through a verified notification or authenticated status enquiry before fulfilment. Browser redirects are navigation only.

Gateway modules should cover accounts/access, merchant integration, payments, refunds, risk, notifications, reconciliation and audit. UI role separation does not require separate backend deployments. The fraud analyst sees assigned cases and records findings; that action does not rewrite processing results or retrain the model.

Use three logical databases with separate least-privilege database users. One PostgreSQL server can host them for the demonstration, but this does not provide infrastructure-level fault isolation. No application reads another application's database during normal operation. A restricted test harness can inspect durable records for evaluation.

Use separate merchant, gateway and simulator hostnames and isolated application networks. Each trust domain's ingress terminates HTTPS. Service calls must use those HTTPS endpoints, including inside Compose; an encrypted public page with plaintext cross-domain backend calls does not meet the baseline. Install the local CA certificate into browsers and calling containers; do not disable certificate verification. [Caddy HTTPS documentation](https://caddyserver.com/docs/automatic-https)

For initial deployment, use one university-provided Linux VM if available, otherwise an approved small VM with persistent storage and backups. Select capacity after measuring the prototype; train models separately from the demonstration runtime. Compose supports a single-server deployment workflow. This proposal does not establish availability, hosting price or high availability. [Docker deployment guidance](https://docs.docker.com/compose/how-tos/production/)

## 4. Payment correctness is application work

PostgreSQL is necessary but does not automatically make a gateway correct. Implement these contracts explicitly:

**Stable operation identity.** Store a unique scoped idempotency key, canonical request fingerprint, operation identifier and durable result. A repeated key with a changed payload conflicts. Distinguish business order identity, logical payment/refund identity, processing operations and delivery attempts. Define retention and expired-key behaviour before exposing the API.

**Local atomicity.** Use transactions for gateway state plus outgoing event intent. At the simulator, atomically commit each unique operation with its fictional effect and recorded result. A gateway transaction cannot include a remote simulator transaction.

**Concurrent refunds.** Lock the parent captured-payment row, check completed plus reserved refund totals, and create the reservation in one transaction. Every refund writer must follow this lock discipline. Keep `completed + reserved <= refundable base`, including while a submission is unresolved. Convert a reservation to a completed refund atomically; do not count both. Use integer minor units and explicit currency codes.

**Uncertainty and recovery.** Timeout after submission means Unresolved. Query the simulator under the original identity. Do not manufacture failure, release uncertain reservations or create a fresh operation merely because a response is missing.

**Durable delivery.** The worker claims due outbox rows with short transactions, records leases and attempts, sends outside the transaction and acknowledges afterward. Expired leases allow crash recovery. Retry with bounded backoff and expose aged/exhausted work for intervention. Delivery is at least once; the merchant durably records and deduplicates events before acknowledging.

**Valid state changes.** Validate transitions and authoritative evidence. Preserve separate payment, refund and delivery states. Old notifications cannot overwrite newer confirmed outcomes. Failed or abandoned simulated verification ends the attempt as Blocked.

PostgreSQL documents locking and `SKIP LOCKED` for queue-like consumers. Use skipping for worker claims, not to skip a locked payment during a refund-capacity decision. [PostgreSQL SELECT documentation](https://www.postgresql.org/docs/current/sql-select.html)

## 5. Identity, permissions and data protection

Serve the gateway frontend and API under the same origin. Use Django's CSRF-protected login flow and CSRF protection on state-changing browser requests. DRF session authentication does not by itself make an anonymous login endpoint safe. [DRF authentication guidance](https://www.django-rest-framework.org/api-guide/authentication/)

Implement merchant membership and customer ownership in database queries and action-level checks. List APIs must filter records before returning them. Object checks alone are insufficient for lists and creation; explicitly validate who may create records and for which merchant. Analysts require assignment checks. Keep framework administration limited to technical maintenance instead of exposing unrestricted model editing as the product's administrator interface. [DRF permission limitations](https://www.django-rest-framework.org/api-guide/permissions/)

Guests receive a high-entropy, narrowly scoped checkout/status entitlement with expiry, exchanged into a protected session where feasible. An order reference or matching email is not payment access. Do not automatically link guest payments to an account.

Keep merchant API credentials out of browser bundles. Separate API credentials from notification-signing secrets. Allow only pre-registered callback destinations and restrict outbound destinations to prevent server-side request forgery. Any private-address exception for the local merchant must be an explicit demo allowlist.

Use synthetic payment identifiers and minimise retained input. Redact passwords, tokens, reset links and guest capabilities from logs. Mount deployment secrets outside Git and restrict access. Define audit retention, backups, restore testing and a deliberate demo-reset procedure.

## 6. Fraud research and runtime integration

Start with a Python risk module inside the gateway, loading a versioned trusted model artifact at startup. Keep feature building, prediction and policy mapping behind a defined interface so a separate scoring service can be added later if measured resource use justifies it. A separate ML service is not required merely because ML is present.

Return a score when available, an action (Allow, Simulated verification or Block), model/policy/feature-schema versions and safe reasons. Record unavailable scoring explicitly. Recommended unavailable policy: stop before simulator submission and display a recoverable technical error, without labelling the user fraudulent. Agree the exact state/retry behaviour before implementation.

Use a fixed policy stub to develop payment workflows before model selection. Scripted scenarios demonstrate action routing and failure handling; they do not measure predictive accuracy.

For the empirical study, compare the same model family using current-transaction features versus current plus prior-activity features. Keep chronological partitions, tuning budget and threshold-selection rules consistent. Logistic regression is a sanity baseline; the tree-based candidate is provisional. Avoid expanding this into a large model competition.

Audit IEEE-CIS permission, labels, time fields, grouping assumptions and screening-time feature availability before accepting it. Reconstructed identifiers are proxies, not established customer identities. Publish an explicit mapping from dataset features to gateway-observable features. Do not fill unavailable benchmark fields with arbitrary values and claim the deployed score has the benchmark's accuracy.

Fit preprocessing only on training data; keep validation and final testing chronological. Prior-activity features must use preceding events only, with deterministic ordering. Retries must not increment distinct-attempt history. Ensure offline and online definitions agree, including history windows and missing values. Late fraud labels cannot be treated as already known.

Report average precision, precision–recall curves, precision, recall, false-positive rate and confusion counts at validation-selected operating points. Separately report action proportions, performance for returning/unseen identifiers where feasible, period variability and end-to-end screening latency including history retrieval. Agree the false-positive constraint and timing budget before evaluating the final test set.

Retain source data hashes, split boundaries, code revision, dependency versions, feature definitions, seeds and result files for every accepted run. Only load trusted model artifacts; keep training and serving dependency versions aligned. [scikit-learn model persistence guidance](https://scikit-learn.org/stable/model_persistence.html)

## 7. Verification and delivery sequence

| Stage | Deliverable | Evidence required before expansion |
|---|---|---|
| 1. Foundations | Development environment, separate service/database identities, HTTPS, account/role model and API draft | Certificate verification succeeds; cross-merchant access fails; dataset feasibility audit completed or limitation documented |
| 2. Complete payment path | Merchant order → hosted checkout → screening stub → simulator → merchant confirmation | Authoritative amount preserved; guest and registered access correct; redirect alone never fulfils |
| 3. Failure recovery | Stable operation IDs, outbox delivery, status enquiry and reconciliation | Lost response after commit, duplicate callers, worker restart and reordered notifications preserve intended effects |
| 4. Lifecycle and operations | Capture/cancellation policy, full/partial refunds and dashboards | Concurrent refund reservations satisfy the invariant; uncertain refunds retain capacity; staff permissions verified |
| 5. Fraud experiment | Eligible feature sets, frozen protocol, baseline comparison and runtime integration | Reproducible metrics, no future-data preprocessing, honest feature mapping and measured screening latency |
| 6. Assessment evidence | Integrated regression suite, load/security results and user task evaluation | Saved test records, known limitations, reproducible demo and restored backup |

Test against real PostgreSQL rather than substituting SQLite for locking tests. Include independently specified expected effects, not just agreement between two implementations that might share a bug. Fault controls should be inaccessible in ordinary use and enabled only in isolated test/demo environments.

Use a single repository with separate application folders, a training/experiments area, infrastructure configuration, API contracts and integration tests. Share schemas and generated client types where useful; avoid sharing the simulator's state-transition implementation with the gateway because that weakens independent verification.

## 8. Choices to defer and decisions still needed

Redis/Celery, Kafka, Kubernetes, a feature store, a model registry server, deep learning, additional cloud services and multiple gateway microservices are not baseline dependencies. Add them only for a demonstrated need. The PostgreSQL worker has real implementation obligations—leases, retry limits, inspection and crash tests—and should be reconsidered if asynchronous workload becomes substantial.

The architecture can be drafted now. Before implementation, settle team language experience, available hosting, one-successful-payment-per-order policy, capture initiation, supported currency, unavailable-screening behaviour, credential/idempotency retention, and workload/latency targets. Existing full/partial refund and guest/account scope is already confirmed.

Strengthen research through four concrete outputs: a dataset feasibility sheet; a targeted recent-literature update on chronological fraud evaluation and prior-activity features; a small set of stakeholder task checks; and architecture decision records connecting requirements to choices and tests. Framework documentation supports capability claims; it does not establish fraud effectiveness, production readiness or implemented security.

## 9. Local evidence used

- `01-report/current/fyp-report-ch1-3.md`: current report baseline, including component boundaries and lifecycle.
- `04-handover/PROJECT-CONTEXT.md`: research interpretation, product scope and collaboration preferences.
- `04-handover/DECISIONS-AND-NEXT-STEPS.md`: confirmed scope, uncertainty handling and refund invariant.
- `02-research/dossier/03-traceability-and-decisions.md`: candidate requirements and failure-experiment catalogue; older unresolved items are superseded where the handover records a later decision.

Official documentation linked above was consulted for this proposal. No implementation, dependency installation, dataset audit, benchmark or security test was performed in preparing it.
