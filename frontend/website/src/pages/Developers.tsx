import { Box, Button, Container, Link, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import OpenInNewRoundedIcon from "@mui/icons-material/OpenInNewRounded";
import type { ReactNode } from "react";
import { CodeBlock } from "../components/CodeBlock";
import { PageHero } from "../components/Section";
import { StatusChip } from "../components/StatusChip";
import { usePageTitle } from "../components/usePageTitle";
import { LIFECYCLE, REPO_URL, RULES, TEST_CARDS, WEBHOOK_EVENTS } from "../content/site";
import { CAPTURE, CREATE_PAYMENT, EVENT_EXAMPLE, PAYMENT_RESPONSE, VERIFY_WEBHOOK } from "../content/snippets";
import { brand, fonts } from "../theme";

const TOC = [
  { id: "quickstart", label: "Quickstart" },
  { id: "auth", label: "Authentication" },
  { id: "lifecycle", label: "Payment lifecycle" },
  { id: "capture", label: "Capture and refunds" },
  { id: "idempotency", label: "Idempotency" },
  { id: "webhooks", label: "Webhooks" },
  { id: "errors", label: "Errors" },
  { id: "test-cards", label: "Test cards" },
  { id: "resources", label: "Contracts and specs" },
];

const ERRORS = [
  ["400", "amount_too_small · amount_too_large", `Outside ${RULES.minAmount} to ${RULES.maxAmount}`],
  ["400", "card_data_not_allowed", "The body contains what looks like a card number"],
  ["400", "line_items_total_mismatch", "Line items don’t add up to the amount"],
  ["401", "api_key_invalid", "Missing, unknown or revoked key"],
  ["404", "resource_not_found", "No such record for this merchant"],
  ["409", "idempotency_key_reused", "Same key, different request"],
  ["409", "payment_already_captured", "Capture or cancel from the wrong status"],
  ["422", "refund_exceeds_refundable", "Refund larger than what is left"],
  ["429", "rate_limited", "Over 100 requests a minute; see Retry-After"],
  ["503", "service_unavailable", "Retry with the same Idempotency-Key"],
];

function DocSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Box component="section" id={id} sx={{ scrollMarginTop: 96, py: { xs: 5, md: 6 }, borderTop: `1px solid ${brand.line}`, "&:first-of-type": { borderTop: 0, pt: 0 } }}>
      <Typography variant="h3" sx={{ fontSize: { xs: 26, md: 32 }, mb: 2 }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

const P = ({ children }: { children: ReactNode }) => <Typography sx={{ color: "text.secondary", lineHeight: 1.7, mb: 2.5, maxWidth: 720 }}>{children}</Typography>;

export default function Developers() {
  usePageTitle("Developers");
  return (
    <>
      <PageHero
        overline="Developers"
        title="Build against a small, strict API"
        lead="REST over HTTPS, JSON in snake_case, amounts in cents and a written contract for every edge case. Here is the overview; the full OpenAPI files are in the repository."
      >
        <Box sx={{ mt: 4, display: "flex", gap: 1.5, flexWrap: "wrap" }}>
          <Button href="#quickstart" variant="contained" color="secondary" size="large">
            Quickstart
          </Button>
          <Button href={`${REPO_URL}/tree/main/contracts`} target="_blank" rel="noopener" size="large" endIcon={<OpenInNewRoundedIcon />} sx={{ color: "#fff", border: "1px solid rgba(255,255,255,0.3)" }}>
            API contract
          </Button>
        </Box>
      </PageHero>

      <Container maxWidth="lg" sx={{ py: { xs: 6, md: 10 } }}>
        <Grid container spacing={{ xs: 0, md: 6 }}>
          <Grid size={{ md: 3 }} sx={{ display: { xs: "none", md: "block" } }}>
            <Box component="nav" aria-label="On this page" sx={{ position: "sticky", top: 100 }}>
              <Typography sx={{ fontSize: 12.5, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "text.secondary", mb: 1.5 }}>On this page</Typography>
              {TOC.map((t) => (
                <Link key={t.id} href={`#${t.id}`} sx={{ display: "block", py: 0.75, color: "text.secondary", fontSize: 15, "&:hover": { color: "text.primary" } }}>
                  {t.label}
                </Link>
              ))}
            </Box>
          </Grid>

          <Grid size={{ xs: 12, md: 9 }} sx={{ minWidth: 0 }}>
            <DocSection id="quickstart" title="Quickstart">
              <P>
                Create a payment from your server, send the customer to the <code>checkout_url</code> you get back, and wait for the signed{" "}
                <code>payment.authorised</code> webhook before you ship. The customer’s return to your <code>return_url</code> is navigation only; never fulfil on it.
              </P>
              <CodeBlock snippets={CREATE_PAYMENT} />
              <Box sx={{ mt: 2 }}>
                <CodeBlock snippets={PAYMENT_RESPONSE} />
              </Box>
            </DocSection>

            <DocSection id="auth" title="Authentication">
              <P>
                Send your secret key as <code>Authorization: Bearer sp_test_…</code>. Keys are shown once and stored only as a digest. The merchant always comes from the key, never
                from the body, and another merchant’s records answer <code>404</code> exactly like records that don’t exist.
              </P>
              <P>
                Each merchant also gets a signing secret (<code>whsec_…</code>). It signs both webhooks and every API reply in a <code>SecurePay-Signature</code> header, so you
                can prove a reply came from SecurePay. Each key is limited to {RULES.rateLimit}.
              </P>
            </DocSection>

            <DocSection id="lifecycle" title="Payment lifecycle">
              <P>A payment moves through these statuses. Final statuses are declined, blocked, cancelled and expired.</P>
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
              <Box sx={{ mt: 2, p: 2.5, borderRadius: 3, bgcolor: "#FFF6E5", border: "1px solid #F3D9A4" }}>
                <Typography sx={{ fontSize: 15, lineHeight: 1.6 }}>
                  <strong>unresolved</strong> means the bank didn’t answer. Don’t ship and don’t retry with a new key: a worker checks the payment with its original operation ID
                  and sends the final event.
                </Typography>
              </Box>
            </DocSection>

            <DocSection id="capture" title="Capture and refunds">
              <P>
                An authorised payment holds the funds for {RULES.authHold}. Capture all of it with <code>{"{}"}</code> or less with <code>{'{"amount": n}'}</code>; the rest is
                released. Captured payments can be refunded in full or in parts, as long as the total stays within what was captured.
              </P>
              <CodeBlock snippets={CAPTURE} />
            </DocSection>

            <DocSection id="idempotency" title="Idempotency">
              <P>
                Every <code>POST</code> needs an <code>Idempotency-Key</code> header (8 to 255 characters; a UUID v4 works). Keys are kept for {RULES.idempotencyWindow}.
              </P>
              <Box component="ul" sx={{ color: "text.secondary", lineHeight: 1.8, pl: 2.5, mt: 0, maxWidth: 720 }}>
                <li>Same key and same body after the first request finished: you get the stored reply, marked <code>Idempotent-Replayed: true</code>.</li>
                <li>Same key while the first request is still running: <code>409 idempotency_request_in_progress</code> with <code>Retry-After: 1</code>.</li>
                <li>Same key with a different body: <code>409 idempotency_key_reused</code>, and nothing runs.</li>
                <li>A <code>5xx</code> reply is not stored, so retrying with the same key is safe and won’t charge twice.</li>
              </Box>
            </DocSection>

            <DocSection id="webhooks" title="Webhooks">
              <P>
                Events are POSTed to your approved HTTPS endpoint. Reply with any <code>2xx</code> within 10 seconds. Failed deliveries are retried for{" "}
                {RULES.webhookRetryWindow} with growing delays (1 min, 5 min, 15 min … up to 12 h). Events can arrive out of order, so keep the highest <code>sequence</code> per
                payment and ignore older ones.
              </P>
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mb: 3 }}>
                {WEBHOOK_EVENTS.map((e) => (
                  <Box key={e} component="code" sx={{ px: 1.25, py: 0.5, borderRadius: 1.5, bgcolor: "#fff", border: `1px solid ${brand.line}`, fontSize: 13 }}>
                    {e}
                  </Box>
                ))}
              </Box>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, lg: 6 }} sx={{ minWidth: 0 }}>
                  <CodeBlock snippets={EVENT_EXAMPLE} />
                </Grid>
                <Grid size={{ xs: 12, lg: 6 }} sx={{ minWidth: 0 }}>
                  <CodeBlock snippets={VERIFY_WEBHOOK} />
                </Grid>
              </Grid>
              <P>
                <Box component="span" sx={{ display: "block", mt: 2.5 }}>
                  Verify the signature over the raw bytes before parsing, reject timestamps more than {RULES.webhookTolerance} old, remember event IDs for at least 7 days, and
                  confirm with <code>GET /v1/payments/{"{id}"}</code> before shipping.
                </Box>
              </P>
            </DocSection>

            <DocSection id="errors" title="Errors">
              <P>
                Every error has the same shape: <code>{"{ error: { type, code, message, param, request_id } }"}</code>. Branch on <code>code</code>, never on{" "}
                <code>message</code>. Some common ones:
              </P>
              <TableContainer sx={{ bgcolor: "#fff", border: `1px solid ${brand.line}`, borderRadius: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 600 }}>HTTP</TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>code</TableCell>
                      <TableCell sx={{ fontWeight: 600 }}>When</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {ERRORS.map(([h, c, w]) => (
                      <TableRow key={c}>
                        <TableCell sx={{ fontFamily: fonts.mono }}>{h}</TableCell>
                        <TableCell sx={{ fontFamily: fonts.mono, fontSize: 13 }}>{c}</TableCell>
                        <TableCell sx={{ color: "text.secondary" }}>{w}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </DocSection>

            <DocSection id="test-cards" title="Test cards">
              <P>
                SecurePay only accepts synthetic card numbers. The number decides what the simulated bank does. Any other number is
                declined.
              </P>
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
                  { t: "OpenAPI 3.1", d: "Every /v1 endpoint and the webhook request.", p: "contracts/openapi" },
                  { t: "JSON Schemas", d: "Payment, Refund, Event and Error objects.", p: "contracts/schemas" },
                  { t: "Simulator contract", d: "How the simulated bank behaves and fails.", p: "contracts/SIMULATOR-CONTRACT.md" },
                ].map((r) => (
                  <Grid key={r.t} size={{ xs: 12, sm: 6 }}>
                    <Link
                      href={`${REPO_URL}/${r.p.endsWith(".md") ? "blob" : "tree"}/main/${r.p}`}
                      target="_blank"
                      rel="noopener"
                      underline="none"
                      sx={{ display: "block", height: "100%", p: 2.5, borderRadius: 3, bgcolor: "#fff", border: `1px solid ${brand.line}`, color: "inherit", "&:hover": { borderColor: brand.ink } }}
                    >
                      <Typography sx={{ fontWeight: 600, mb: 0.5, display: "flex", alignItems: "center", gap: 0.75 }}>
                        {r.t} <OpenInNewRoundedIcon sx={{ fontSize: 15, color: "text.secondary" }} />
                      </Typography>
                      <Typography sx={{ color: "text.secondary", fontSize: 14.5, mb: 1 }}>{r.d}</Typography>
                      <Typography sx={{ fontFamily: fonts.mono, fontSize: 12.5, color: "#B26F00" }}>{r.p}</Typography>
                    </Link>
                  </Grid>
                ))}
              </Grid>
            </DocSection>
          </Grid>
        </Grid>
      </Container>
    </>
  );
}
