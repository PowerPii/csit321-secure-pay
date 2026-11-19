import { Box, Button, Link, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import OpenInNewRoundedIcon from "@mui/icons-material/OpenInNewRounded";
import { Link as RouterLink } from "react-router-dom";
import { CodeBlock } from "../components/CodeBlock";
import { Callout, DocSection, DOCS_NAV, DocsShell, Inline, P, SimpleTable } from "../components/Docs";
import { PageHero } from "../components/Section";
import { StatusChip } from "../components/StatusChip";
import { usePageTitle } from "../components/usePageTitle";
import { ERRORS, RETRY_SCHEDULE, WEBHOOK_HEADERS } from "../content/apiReference";
import { API_BASE, DASHBOARD_URL, LIFECYCLE, OPENAPI_YAML, REGISTER_URL, REPO_URL, RULES, SDK_NPM_URL, SDK_PACKAGE, TEST_CARDS, WEBHOOK_EVENTS } from "../content/site";
import { CAPTURE, CREATE_PAYMENT, EVENT_EXAMPLE, PAYMENT_RESPONSE, SDK_INSTALL, SDK_USAGE, VERIFY_WEBHOOK } from "../content/snippets";
import { brand, fonts } from "../theme";

const STEPS: { title: string; text: string }[] = [
  { title: "Register your business", text: "Fill in the registration form on the gateway: business name, UEN, website and a contact." },
  { title: "Verify your email", text: "Open the link we email you. It is valid for 24 hours." },
  { title: "Wait for approval", text: "A SecurePay administrator reviews the registration. No API key is issued before approval, and a suspended account gets `403 merchant_not_active`." },
  { title: "Generate your keys", text: "Sign in to the dashboard and open API keys. You get a secret API key (`sp_test_…`) and a webhook signing secret (`whsec_…`). Both are shown once, so store them in your server's configuration straight away." },
  { title: "Add your webhook address", text: "Submit an HTTPS address on the same page. An administrator approves it before any event is sent there." },
  { title: "Take a test payment", text: "Create a payment with the Quickstart below and pay on the hosted checkout with test card `4242 4242 4242 4242`." },
];

export default function Developers() {
  usePageTitle("Developers");
  return (
    <>
      <PageHero
        overline="Developers"
        title="Build against a small, strict API"
        lead="REST over HTTPS, JSON in snake_case, amounts in cents and a written contract for every edge case. Guides on this page, every endpoint in the API reference."
      >
        <Box sx={{ mt: 4, display: "flex", gap: 1.5, flexWrap: "wrap" }}>
          <Button href="#get-started" variant="contained" color="secondary" size="large">
            Get started
          </Button>
          <Button component={RouterLink} to="/developers/api" size="large" endIcon={<ArrowForwardRoundedIcon />} sx={{ color: brand.navy }}>
            API reference
          </Button>
        </Box>
      </PageHero>

      <DocsShell nav={DOCS_NAV}>
        <DocSection id="get-started" title="Get started">
          <P>
            The SecurePay gateway runs as a live demo. Every payment on it is simulated: test card numbers, a simulated bank and no real money. Here is how to go from nothing to
            a first test payment.
          </P>
          <Box component="ol" sx={{ listStyle: "none", p: 0, m: 0, mb: 3, display: "grid", gap: 1.25, maxWidth: 760 }}>
            {STEPS.map((step, i) => (
              <Box component="li" key={step.title} sx={{ display: "grid", gridTemplateColumns: "36px 1fr", gap: 1.5, p: 2, borderRadius: 3, bgcolor: "#fff", border: `1px solid ${brand.line}` }}>
                <Box sx={{ width: 32, height: 32, borderRadius: "50%", display: "grid", placeItems: "center", bgcolor: brand.ink, color: "#fff", fontWeight: 700, fontSize: 14 }}>{i + 1}</Box>
                <Box>
                  <Typography sx={{ fontWeight: 600, mb: 0.25 }}>{step.title}</Typography>
                  <Typography component="div" sx={{ color: "text.secondary", lineHeight: 1.6, fontSize: 15 }}>
                    <Inline text={step.text} />
                  </Typography>
                </Box>
              </Box>
            ))}
          </Box>
          <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap", mb: 3 }}>
            <Button href={REGISTER_URL} target="_blank" rel="noopener" variant="contained" endIcon={<OpenInNewRoundedIcon />}>
              Register a merchant account
            </Button>
            <Button href={DASHBOARD_URL} target="_blank" rel="noopener" variant="outlined" endIcon={<OpenInNewRoundedIcon />}>
              Sign in to the dashboard
            </Button>
          </Box>
          <Box sx={{ p: 2, borderRadius: 3, bgcolor: "#fff", border: `1px solid ${brand.line}`, maxWidth: 760 }}>
            <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: "text.secondary", mb: 0.5 }}>Base URL</Typography>
            <Typography sx={{ fontFamily: fonts.mono, fontSize: 14.5, wordBreak: "break-all" }}>{API_BASE}</Typography>
          </Box>
        </DocSection>

        <DocSection id="quickstart" title="Quickstart">
          <P>
            Create a payment from your server, send the customer to the `checkout_url` you get back, and wait for the signed `payment.authorised` webhook before you ship. The
            customer’s return to your `return_url` is navigation only; never fulfil on it.
          </P>
          <P>
            `line_items` is optional. When you send it, the checkout page shows the items as the order summary, and they must add up to `amount` exactly.
          </P>
          <CodeBlock snippets={CREATE_PAYMENT} />
          <Box sx={{ mt: 2 }}>
            <CodeBlock snippets={PAYMENT_RESPONSE} />
          </Box>
        </DocSection>

        <DocSection id="sdk" title="Node.js SDK">
          <P>
            {`The \`${SDK_PACKAGE}\` package is a small, typed client for Node.js 20.19 or later, with no dependencies. It sends an \`Idempotency-Key\` on every \`POST\` (pass the one you saved with the order or refund), retries timeouts, \`429\` and \`5xx\` with that same key, keeps the key on any error whose outcome is unknown, checks the signature on every reply and webhook, and turns error replies into a \`SecurePayAPIError\` with the stable \`code\`. Its types are generated from the OpenAPI file.`}
          </P>
          <Box sx={{ mb: 2, maxWidth: 640 }}>
            <CodeBlock snippets={SDK_INSTALL} />
          </Box>
          <CodeBlock snippets={SDK_USAGE} />
          <Callout tone="info">
            The API key is a secret, so the SDK runs on your server only and refuses to start in a browser. Webhook handling with the SDK is under Webhooks below.
          </Callout>
          <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap" }}>
            <Button href={SDK_NPM_URL} target="_blank" rel="noopener" variant="outlined" endIcon={<OpenInNewRoundedIcon />}>
              {SDK_PACKAGE} on npm
            </Button>
          </Box>
        </DocSection>

        <DocSection id="auth" title="Authentication">
          <P>
            Send your secret key as `Authorization: Bearer sp_test_…`. Keys are shown once and stored only as a digest. The merchant always comes from the key, never from the
            body, and another merchant’s records answer `404` exactly like records that don’t exist.
          </P>
          <P>{`Each key is limited to ${RULES.rateLimit}. Above that you get \`429 rate_limited\` with a \`Retry-After\` header, and your other keys are not affected. Every reply carries a \`SecurePay-Request-Id\` header; quote it when you ask for help.`}</P>
          <DocSection id="signed-replies" title="Signed replies" level={3}>
            <P>
              {'Your signing secret (`whsec_…`) signs both webhooks and every API reply to a request with a valid key, errors included, in a `SecurePay-Signature` header. So a signed `GET /v1/payments/{id}` is proof of status you can act on. The header is `t=<unix seconds>,v1=<hex HMAC-SHA256>`, computed over the bytes `<t>.<raw body>`. Check it the same way as a webhook (code under Webhooks). Only `401` replies are unsigned, because the merchant is unknown.'}
            </P>
          </DocSection>
        </DocSection>

        <DocSection id="lifecycle" title="Payment lifecycle">
          <P>A payment moves through these statuses. Final statuses are declined, blocked, cancelled and expired, and then `outcome.reason` says why.</P>
          <Box sx={{ display: "grid", gap: 1 }}>
            {LIFECYCLE.map((s, i) => (
              <Box key={s.status} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "220px 1fr" }, gap: { xs: 0.75, sm: 2 }, alignItems: "center", p: 2, borderRadius: 3, bgcolor: "#fff", border: `1px solid ${brand.line}` }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
                  <Typography sx={{ fontFamily: fonts.mono, fontSize: 12, color: "text.secondary", width: 18 }}>{i + 1}</Typography>
                  <StatusChip tone={s.status === "captured" || s.status === "authorised" ? "allow" : s.status === "verification_required" ? "verify" : "neutral"}>{s.status}</StatusChip>
                </Box>
                <Typography sx={{ color: "text.secondary", fontSize: 15 }}>{s.text}</Typography>
              </Box>
            ))}
          </Box>
          <Callout>
            `unresolved` means the bank didn’t answer. Don’t ship and don’t retry with a new key: a worker checks the payment with its original operation ID and sends the final
            event.
          </Callout>
        </DocSection>

        <DocSection id="capture" title="Capture and refunds">
          <P>
            {`An authorised payment holds the funds for ${RULES.authHold}. Capture all of it with \`{}\` or less with \`{"amount": n}\`; the rest is released. Captured payments can be refunded in full or in parts, as long as the total stays within what was captured.`}
          </P>
          <P>
            If the bank doesn’t answer a capture or cancel, the reply is `202` and the payment stays `authorised` with a `pending_operation` until a worker settles it. Don’t send
            another capture meanwhile; it gets `409 operation_in_progress`.
          </P>
          <CodeBlock snippets={CAPTURE} />
        </DocSection>

        <DocSection id="idempotency" title="Idempotency">
          <P>{`Every \`POST\` needs an \`Idempotency-Key\` header (8 to 255 characters; a UUID v4 works). Use a new key for each operation and reuse it only to retry that operation. Keys are kept for ${RULES.idempotencyWindow}.`}</P>
          <Box component="ul" sx={{ color: "text.secondary", lineHeight: 1.8, pl: 2.5, mt: 0, maxWidth: 760 }}>
            <li>
              Same key and same body after the first request finished: you get the stored reply, marked <code>Idempotent-Replayed: true</code>.
            </li>
            <li>
              Same key while the first request is still running: <code>409 idempotency_request_in_progress</code> with <code>Retry-After: 1</code>.
            </li>
            <li>
              Same key with a different body: <code>409 idempotency_key_reused</code>, and nothing runs.
            </li>
            <li>
              A <code>5xx</code> reply is not stored, so retrying with the same key is safe and won’t charge twice.
            </li>
          </Box>
          <DocSection id="idempotency-keys" title="Save the key before you call" level={3}>
            <P>
              A key only helps if you still have it after a crash. Create it when you create the order, save it in the same database row, then call the API. If the reply is lost
              or your server restarts, read the saved key and send the same request again: you get the original payment back with `Idempotent-Replayed: true`. A key made
              inside the call disappears with the process, and a new key is a new payment.
            </P>
            <P>
              Each refund is its own operation. Save a refund record with its own key before calling, so two partial refunds use two keys and a retry of one never becomes a
              second refund. Capture and cancel work the same way.
            </P>
          </DocSection>
          <DocSection id="after-24-hours" title="Unresolved after 24 hours" level={3}>
            <P>
              {`A key is kept for ${RULES.idempotencyWindow} from its first use; after that the same key starts a new operation. So before sending anything for an older operation, find out what happened to the first one. A refund: \`GET /v1/payments/{id}/refunds\` lists every refund of the payment with the amount still refundable. A payment you never saw the ID of: search its order reference on the dashboard’s Payments page, and check your webhook log for its events. An unpaid payment expires when its checkout link does (${RULES.checkoutTtl}), so it can never be charged later. Only create a new payment or refund when the lookup shows the first one did not happen.`}
            </P>
          </DocSection>
        </DocSection>

        <DocSection id="webhooks" title="Webhooks">
          <P>{`Events are POSTed to your approved HTTPS address. Reply with any \`2xx\` within 10 seconds; do slow work afterwards. Failed deliveries are retried for ${RULES.webhookRetryWindow} (${RULES.webhookAttempts} attempts in all), then marked undelivered on your dashboard. Events can arrive out of order, so keep the highest \`sequence\` per payment and ignore older ones.`}</P>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mb: 3 }}>
            {WEBHOOK_EVENTS.map((e) => (
              <Box key={e} component="code" sx={{ px: 1.25, py: 0.5, borderRadius: 1.5, bgcolor: "#fff", border: `1px solid ${brand.line}`, fontSize: 13 }}>
                {e}
              </Box>
            ))}
          </Box>
          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid size={{ xs: 12, lg: 6 }} sx={{ minWidth: 0 }}>
              <CodeBlock snippets={EVENT_EXAMPLE} />
            </Grid>
            <Grid size={{ xs: 12, lg: 6 }} sx={{ minWidth: 0 }}>
              <CodeBlock snippets={VERIFY_WEBHOOK} />
            </Grid>
          </Grid>
          <P>
            <Inline
              text={`Verify the signature over the raw bytes before parsing, reject timestamps more than ${RULES.webhookTolerance} old, remember event IDs for at least 7 days, and confirm with \`GET /v1/payments/{id}\` before shipping. What each event means is in the `}
            />
            <Link component={RouterLink} to="/developers/api#events" underline="always">
              API reference
            </Link>
            .
          </P>
          <DocSection id="webhook-headers" title="Request headers" level={3}>
            <SimpleTable head={["Header", "Value"]} rows={WEBHOOK_HEADERS} />
          </DocSection>
          <DocSection id="webhook-retries" title="Retry schedule" level={3}>
            <P>Delays after each failed attempt, with ±10% jitter. A timeout, a TLS error, a redirect and any non-2xx status all count as failures. The signature is computed fresh for each attempt, so retries pass your replay check.</P>
            <SimpleTable head={["Retry", "Delay"]} rows={RETRY_SCHEDULE} />
          </DocSection>
        </DocSection>

        <DocSection id="errors" title="Errors">
          <P>
            {"Every error has the same shape: `{ error: { type, code, message, param, request_id } }`. Branch on `code`, never on `message`. The ones you are most likely to meet:"}
          </P>
          <SimpleTable
            head={["HTTP", "code", "When"]}
            monoCols={[0, 1]}
            rows={ERRORS.filter((e) => COMMON_ERRORS.includes(e.code)).map((e) => [e.http, e.code, e.when])}
          />
          <Button component={RouterLink} to="/developers/api#error-codes" endIcon={<ArrowForwardRoundedIcon />}>
            All {ERRORS.length} error codes
          </Button>
        </DocSection>

        <DocSection id="test-cards" title="Test cards">
          <P>SecurePay only accepts synthetic card numbers. The number decides what the simulated bank does. Any other valid number is declined. Use any expiry date that is not in the past and any 3-digit security code.</P>
          <TableContainer sx={{ bgcolor: "#fff", border: `1px solid ${brand.line}`, borderRadius: 3 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Card number</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Simulated result</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {TEST_CARDS.map((c) => (
                  <TableRow key={c.number}>
                    <TableCell sx={{ fontFamily: fonts.mono, whiteSpace: "nowrap" }}>{c.number}</TableCell>
                    <TableCell>
                      <StatusChip tone={c.tone}>{c.outcome}</StatusChip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </DocSection>

        <DocSection id="resources" title="Contracts and specs">
          <P>The API is designed contract-first. These files are the source of truth, and example payloads are checked against the schemas in CI.</P>
          <Grid container spacing={2}>
            {[
              { t: "API contract", d: "The rules a schema can’t express: lifecycle, errors, retries.", p: "contracts/API-CONTRACT.md" },
              { t: "OpenAPI 3.1", d: "Every /v1 endpoint and the webhook request, in one file.", p: "contracts/openapi", href: OPENAPI_YAML, label: "merchant-api.v1.yaml" },
              { t: "Interactive reference", d: "The OpenAPI file, browsable, with request and response samples.", p: "", to: "/developers/api/explorer", label: "/developers/api/explorer" },
              { t: "JSON Schemas", d: "Payment, Refund, Event and Error objects.", p: "contracts/schemas" },
              { t: "Simulator contract", d: "How the simulated bank behaves and fails.", p: "contracts/SIMULATOR-CONTRACT.md" },
            ].map((r) => (
              <Grid key={r.t} size={{ xs: 12, sm: 6 }}>
                <Link
                  {...("to" in r && r.to
                    ? { component: RouterLink, to: r.to }
                    : "href" in r && r.href
                      ? { href: r.href, download: true }
                      : { href: `${REPO_URL}/${r.p.endsWith(".md") ? "blob" : "tree"}/main/${r.p}`, target: "_blank", rel: "noopener" })}
                  underline="none"
                  sx={{ display: "block", height: "100%", p: 2.5, borderRadius: 3, bgcolor: "#fff", border: `1px solid ${brand.line}`, color: "inherit", "&:hover": { borderColor: brand.navy } }}
                >
                  <Typography sx={{ fontWeight: 600, mb: 0.5, display: "flex", alignItems: "center", gap: 0.75 }}>
                    {r.t} <OpenInNewRoundedIcon sx={{ fontSize: 15, color: "text.secondary" }} />
                  </Typography>
                  <Typography sx={{ color: "text.secondary", fontSize: 14.5, mb: 1 }}>{r.d}</Typography>
                  <Typography sx={{ fontFamily: fonts.mono, fontSize: 12.5, color: "text.secondary" }}>{"label" in r && r.label ? r.label : r.p}</Typography>
                </Link>
              </Grid>
            ))}
          </Grid>
        </DocSection>
      </DocsShell>
    </>
  );
}

const COMMON_ERRORS = [
  "amount_too_small",
  "card_data_not_allowed",
  "line_items_total_mismatch",
  "api_key_invalid",
  "merchant_not_active",
  "resource_not_found",
  "idempotency_key_reused",
  "payment_already_captured",
  "refund_exceeds_refundable",
  "rate_limited",
  "service_unavailable",
];
