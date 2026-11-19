import { Box, Button, Card, CardContent, Stack, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import { Link as RouterLink } from "react-router-dom";
import type { ReactNode } from "react";
import { CtaBand } from "../components/CtaBand";
import { PageHero, Section, SectionHeading } from "../components/Section";
import { StatusChip } from "../components/StatusChip";
import { usePageTitle } from "../components/usePageTitle";
import { MEASURED, RULES, SCREENS } from "../content/site";
import { Screenshot } from "../components/Screenshot";
import { brand, fonts } from "../theme";

type Feature = {
  id: string;
  overline: string;
  title: string;
  lead: string;
  points: string[];
  facts: { k: string; v: string }[];
  visual?: ReactNode;
  shot?: { shot: (typeof SCREENS)[keyof typeof SCREENS]; caption: string };
};

const FEATURES: Feature[] = [
  {
    id: "checkout",
    overline: "Hosted checkout",
    title: "A hosted payment page",
    lead: "The store sends the customer to a SecurePay link. The page shows the order, takes the card, runs screening and sends the customer back to the store with the result.",
    points: [
      "Amount, currency and merchant are fixed when you create the payment. Checkout cannot change them.",
      "Optional line items appear on the page as the order summary, and must add up to the amount.",
      "Separate result pages for approved, declined, blocked and “we’re still checking”.",
      "Each payment gets a short reference such as SP-RTZG-FKQE, shown on the emailed receipt and the PDF receipt.",
      "Guests can check a payment later with the reference, their email and a one-time code.",
      "Strict Content Security Policy and no third-party scripts on the payment page.",
    ],
    facts: [
      { k: "Currency", v: RULES.currency },
      { k: "Amount range", v: `${RULES.minAmount} – ${RULES.maxAmount}` },
      { k: "Checkout link lifetime", v: RULES.checkoutTtl },
    ],
    shot: { shot: SCREENS.checkout, caption: "The checkout page for an order from the Volt & Co. demo store." },
  },
  {
    id: "vault",
    overline: "Card vault",
    title: "Card numbers are deleted after the payment is submitted",
    lead: "Card details are swapped for a token as soon as they are entered, encrypted with AES-256-GCM in a separate vault database, and deleted once the payment is sent to the bank.",
    points: [
      "The store only ever sees a token, the card brand and the last four digits.",
      "The vault has its own database and encryption key, apart from the payments database.",
      "A keyed fingerprint lets screening recognise a card it has seen before without storing the number.",
      "The API rejects any request that looks like it contains a card number (card_data_not_allowed), and does not log it.",
    ],
    facts: [
      { k: "Stored after submit", v: "Nothing" },
      { k: "Visible to merchant", v: "Token, brand, last 4" },
      { k: "Card numbers in logs", v: "Never" },
    ],
  },
  {
    id: "fraud",
    overline: "Fraud screening",
    title: "Rules, then a model, then a policy, on every payment",
    lead: "Screening runs after the card is tokenised and before the bank is asked. Each decision is saved with the rules that fired, the model score and the policy version, so an analyst can see why it was made.",
    points: [
      "Deterministic rules for blocklisted cards, bursts of attempts and amount limits.",
      `A HistGradientBoosting model, trained on the public IEEE-CIS dataset, scores the payment and the card’s recent activity. It reached ROC-AUC ${MEASURED.modelRocAuc} on held-out data.`,
      "A versioned policy maps the score to allow, verify or block.",
      "Verify sends a 6-digit code by email, valid for 10 minutes. Three wrong codes block the payment.",
      "If screening is unavailable, the payment is blocked rather than waved through.",
      "Blocked and verified payments go to a review queue, where an analyst records a finding.",
    ],
    facts: [
      { k: "Screening, measured", v: `p95 ${MEASURED.screeningP95}` },
      { k: "Screening target", v: `p95 ≤ ${RULES.screeningP95}` },
      { k: "Timeout", v: `${RULES.screeningTimeout}, then block` },
      { k: "Verification code", v: `${RULES.verificationCodeDigits} digits, ${RULES.verificationCodeTtl}` },
    ],
    shot: { shot: SCREENS.verify, caption: "A payment the policy marked as verify: the customer is asked for the emailed code." },
    visual: (
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <StatusChip tone="allow">allow</StatusChip>
        <StatusChip tone="verify">verify</StatusChip>
        <StatusChip tone="block">block</StatusChip>
      </Stack>
    ),
  },
  {
    id: "webhooks",
    overline: "Webhooks",
    title: "Signed webhooks, retried for 72 hours",
    lead: "A status change and its webhook event are saved in the same database transaction. If one is saved, so is the other, and no event goes out for a change that was rolled back.",
    points: [
      "Signed with HMAC-SHA256 over the timestamp and raw body: SecurePay-Signature: t=…,v1=….",
      "Delivered only to HTTPS addresses an administrator approved, checked against private networks before every attempt.",
      "Retried with growing delays for 72 hours: 14 attempts in all, then kept as undelivered on the dashboard.",
      "A sequence number on every event, so you can ignore stale ones and spot gaps.",
      "Twelve event types, from payment.verification_required to refund.unresolved.",
    ],
    facts: [
      { k: "Retry window", v: RULES.webhookRetryWindow },
      { k: "Attempts", v: String(RULES.webhookAttempts) },
      { k: "Replay tolerance", v: RULES.webhookTolerance },
    ],
  },
  {
    id: "reliability",
    overline: "Safe retries",
    title: "No double charge when a bank reply is lost",
    lead: "Each bank operation gets an ID that is saved before the request is sent. If no reply comes back, a worker asks the bank about that same ID later instead of sending the payment again.",
    points: [
      "Idempotency-Key on every POST: the same request returns the stored reply, a different request with the same key is refused.",
      "Payments the bank didn’t answer are marked unresolved, not failed, and a worker checks them with the original operation ID.",
      "Refunds reserve their amount under a row lock, so two refunds at once can never exceed what was captured.",
      "Uncaptured authorisations are cancelled automatically after 7 days.",
    ],
    facts: [
      { k: "Idempotency window", v: RULES.idempotencyWindow },
      { k: "Authorisation hold", v: RULES.authHold },
      { k: "Rate limit", v: "100 / min per key" },
    ],
  },
  {
    id: "dashboard",
    overline: "Staff dashboard",
    title: "One dashboard for operators, analysts and administrators",
    lead: "All three roles sign in to the same dashboard. Each role sees only its own pages, and a merchant operator sees only that merchant's payments.",
    points: [
      "Payments list with filters, and a detail view with the full timeline and the fraud decision.",
      "Capture, cancel and full or partial refunds, with every action written to the audit log.",
      "For analysts: a review queue, alerts, reports, history search, a block list and editable fraud rules.",
      "For administrators: merchant approval, staff accounts, gateway limits and integrity checks.",
      "Password plus TOTP for every staff account, and a 15-minute lockout after 5 failed sign-ins.",
    ],
    facts: [
      { k: "Sign-in", v: "Password + TOTP" },
      { k: "Lockout", v: "5 tries, 15 min" },
      { k: "Audit", v: "Every state change" },
    ],
    shot: { shot: SCREENS.fraudReview, caption: "An analyst’s review queue with one case open." },
  },
];

const ALSO = [
  { title: "Customer accounts", text: "Customers can sign up to see their payment history, reset a password and view the personal data held about them." },
  { title: "Guest status check", text: "Guests look up a payment with its reference, their email and a one-time code, and can download a PDF receipt." },
  { title: "Fraud rules and reports", text: "Analysts edit rules without a deploy, with each version kept. Reports export to CSV, and new alerts show on the dashboard within seconds." },
  { title: "Integrity checks", text: "A worker re-checks payment hashes and seals the audit log in a chain, so an edited row shows up." },
  { title: "Merchant self-registration", text: "A business registers with its UEN, verifies its email and waits for an administrator to approve it before any API key exists." },
  { title: "Webhook delivery log", text: "Merchants see every webhook attempt with its status code and timing, and can resend an event that was not delivered." },
  { title: "“Why was this blocked?”", text: "Analysts see the rules that fired and the features that pushed the model score up or down for each decision." },
  { title: "Real email delivery", text: "Receipts, verification codes and password resets go to real inboxes through Resend, which reports back when a message is delivered or bounces." },
  { title: "Public status page", text: "Each part of the system is checked every 5 minutes, and the page shows the result with simple payment measures." },
  { title: "Node.js SDK", text: "The securepaysg package on npm wraps the API with types, safe retries and webhook signature checks." },
  { title: "Fraud insights", text: "Charts of screening decisions over time and of model scores, for analysts and administrators." },
  { title: "Backups and recovery", text: "Daily backups hold no card data, a weekly check restores the newest one, and a rollback script returns to the last good version." },
];

export default function Product() {
  usePageTitle("Product");
  return (
    <>
      <PageHero
        overline="Product"
        title="What SecurePay does"
        lead="Six parts: a hosted checkout, a card vault, fraud screening, webhooks, safe retries and a staff dashboard. Each section lists the actual rules and limits we built."
      >
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 4 }}>
          {FEATURES.map((f) => (
            <Button key={f.id} href={`#${f.id}`} size="small" sx={{ color: brand.navy, bgcolor: "#fff", border: `1px solid ${brand.line}`, px: 2 }}>
              {f.overline}
            </Button>
          ))}
        </Stack>
      </PageHero>

      {FEATURES.map((f, i) => (
        <Section key={f.id} id={f.id} tone={i % 2 ? "white" : "paper"}>
          <Grid container spacing={{ xs: 5, md: 8 }}>
            <Grid size={{ xs: 12, md: 7 }}>
              <SectionHeading overline={f.overline} title={f.title} lead={f.lead} />
              <Stack spacing={1.75}>
                {f.points.map((p) => (
                  <Box key={p} sx={{ display: "flex", gap: 1.5 }}>
                    <CheckCircleRoundedIcon sx={{ color: brand.allow, fontSize: 20, mt: "3px" }} />
                    <Typography sx={{ color: "text.secondary", lineHeight: 1.6 }}>{p}</Typography>
                  </Box>
                ))}
              </Stack>
            </Grid>
            <Grid size={{ xs: 12, md: 5 }}>
              <Box sx={{ position: { md: "sticky" }, top: 100 }}>
                <Card sx={{ bgcolor: i % 2 ? brand.slate : "#fff" }}>
                  <CardContent sx={{ p: 3.5 }}>
                    <Typography sx={{ fontWeight: 600, fontSize: 14, color: "text.secondary", mb: 2 }}>At a glance</Typography>
                    {f.facts.map((x, k) => (
                      <Box key={x.k} sx={{ display: "flex", justifyContent: "space-between", gap: 2, py: 1.5, borderTop: k ? `1px solid ${brand.line}` : "none" }}>
                        <Typography sx={{ color: "text.secondary" }}>{x.k}</Typography>
                        <Typography sx={{ fontWeight: 600, textAlign: "right" }}>{x.v}</Typography>
                      </Box>
                    ))}
                    {f.visual && <Box sx={{ mt: 2 }}>{f.visual}</Box>}
                  </CardContent>
                </Card>
                {f.shot && (
                  <Box sx={{ mt: 3 }}>
                    <Screenshot shot={f.shot.shot} caption={f.shot.caption} />
                  </Box>
                )}
              </Box>
            </Grid>
          </Grid>
        </Section>
      ))}

      <Section tone="dark">
        <SectionHeading dark overline="Also built" title="Beyond the core payment path" lead="These came after the six core parts above, and are all running on the demo server." />
        <Grid container spacing={2}>
          {ALSO.map((l) => (
            <Grid key={l.title} size={{ xs: 12, sm: 6, md: 3 }}>
              <Box sx={{ height: "100%", p: 3, borderRadius: 4, border: "1px solid rgba(255,255,255,0.14)", bgcolor: "rgba(255,255,255,0.04)" }}>
                <Typography variant="h6" sx={{ mb: 1 }}>
                  {l.title}
                </Typography>
                <Typography sx={{ color: "rgba(255,255,255,0.65)", fontSize: 15, lineHeight: 1.6 }}>{l.text}</Typography>
              </Box>
            </Grid>
          ))}
        </Grid>
        <Button component={RouterLink} to="/about" sx={{ color: "#fff", mt: 4, px: 0 }}>
          About the project and its timeline →
        </Button>
      </Section>

      <CtaBand />
    </>
  );
}
