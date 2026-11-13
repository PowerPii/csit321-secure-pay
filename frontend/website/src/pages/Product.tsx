import { Box, Button, Card, CardContent, Stack, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import { Link as RouterLink } from "react-router-dom";
import type { ReactNode } from "react";
import { CtaBand } from "../components/CtaBand";
import { PageHero, Section, SectionHeading } from "../components/Section";
import { StatusChip } from "../components/StatusChip";
import { usePageTitle } from "../components/usePageTitle";
import { RULES } from "../content/site";
import { brand, fonts } from "../theme";

type Feature = {
  id: string;
  overline: string;
  title: string;
  lead: string;
  points: string[];
  facts: { k: string; v: string }[];
  visual?: ReactNode;
};

const FEATURES: Feature[] = [
  {
    id: "checkout",
    overline: "Hosted checkout",
    title: "A payment page you don’t have to build or secure",
    lead: "Send the customer to a SecurePay link. We show your order, take the card, run screening and send them back to your store with the result.",
    points: [
      "Amount, currency and merchant are fixed when you create the payment. Checkout cannot change them.",
      "Optional line items appear on the page as the order summary, and must add up to the amount.",
      "Clear result pages for approved, declined, blocked and “we’re still checking”.",
      "Each payment gets a customer-friendly reference such as SP-7KQ4-M2XD, printed on the emailed receipt.",
      "Guests can check a payment later with the reference, their email and a one-time code.",
      "Strict Content Security Policy and no third-party scripts on the payment page.",
    ],
    facts: [
      { k: "Currency", v: RULES.currency },
      { k: "Amount range", v: `${RULES.minAmount} – ${RULES.maxAmount}` },
      { k: "Checkout link lifetime", v: RULES.checkoutTtl },
    ],
  },
  {
    id: "vault",
    overline: "Card vault",
    title: "Card data that disappears when it is no longer needed",
    lead: "Card details are tokenised the moment they are entered, held encrypted in a separate vault database, and deleted once the payment is submitted to the bank.",
    points: [
      "Your systems only ever handle a token, the card brand and the last four digits.",
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
    lead: "Screening happens after the card is tokenised and before the bank is asked. Every decision is recorded with the rules that fired, the model score and the policy version, so an analyst can see exactly why.",
    points: [
      "Deterministic rules for blocklisted cards, bursts of attempts and amount limits.",
      "A HistGradientBoosting model scores the payment using the current attempt and the card’s recent activity.",
      "A versioned policy maps the score to allow, verify or block.",
      "Verify sends a 6-digit code by email, valid for 10 minutes. Three wrong codes block the payment.",
      "If screening is unavailable, the payment is blocked rather than waved through.",
      "Blocked payments land in a review queue with their reasons.",
    ],
    facts: [
      { k: "Screening target", v: `p95 ≤ ${RULES.screeningP95}` },
      { k: "Timeout", v: `${RULES.screeningTimeout}, then block` },
      { k: "Verification code", v: `${RULES.verificationCodeDigits} digits, ${RULES.verificationCodeTtl}` },
    ],
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
    title: "Events you can trust, delivered until you hear them",
    lead: "Every status change and its webhook event are written in the same database transaction, so an event is never lost and never sent for a change that didn’t happen.",
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
    title: "Timeouts happen. Double charges shouldn’t.",
    lead: "Networks drop replies. SecurePay is designed around that: every bank operation gets an ID before it is sent, and anything left unanswered is reconciled with that same ID.",
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
    title: "One place to find, explain and act on a payment",
    lead: "Merchant operators, analysts and administrators sign in to the same dashboard and see only what their role allows.",
    points: [
      "Payments list with filters, and a detail view with the full timeline and the fraud decision.",
      "Capture, cancel and full or partial refunds, with every action written to the audit log.",
      "A fraud review queue for blocked and verified payments.",
      "Password plus TOTP for every staff account, and a 15-minute lockout after 5 failed sign-ins.",
    ],
    facts: [
      { k: "Sign-in", v: "Password + TOTP" },
      { k: "Lockout", v: "5 tries, 15 min" },
      { k: "Audit", v: "Every state change" },
    ],
  },
];

const LATER = [
  { title: "PayNow QR", text: "Singapore's account-to-account QR payments, as a second payment method." },
  { title: "Customer accounts", text: "Saved payment history, password reset and a personal data view." },
  { title: "Editable fraud rules", text: "Administrators tune rules and the screening fallback without a deploy." },
  { title: "Fraud reports", text: "Reports, CSV export and real-time alerts for analysts." },
];

export default function Product() {
  usePageTitle("Product");
  return (
    <>
      <PageHero
        overline="Product"
        title="A complete payment path, with the risk check inside it"
        lead="Six pieces that work together: hosted checkout, card vault, fraud screening, webhooks, safe retries and a staff dashboard."
      >
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 4 }}>
          {FEATURES.map((f) => (
            <Button key={f.id} href={`#${f.id}`} size="small" sx={{ color: "#fff", border: "1px solid rgba(255,255,255,0.25)", px: 2 }}>
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
                <Card sx={{ bgcolor: i % 2 ? brand.paper : "#fff" }}>
                  <CardContent sx={{ p: 3.5 }}>
                    <Typography sx={{ fontFamily: fonts.mono, fontSize: 12.5, color: "text.secondary", mb: 2 }}>at a glance</Typography>
                    {f.facts.map((x, k) => (
                      <Box key={x.k} sx={{ display: "flex", justifyContent: "space-between", gap: 2, py: 1.5, borderTop: k ? `1px solid ${brand.line}` : "none" }}>
                        <Typography sx={{ color: "text.secondary" }}>{x.k}</Typography>
                        <Typography sx={{ fontWeight: 600, textAlign: "right" }}>{x.v}</Typography>
                      </Box>
                    ))}
                    {f.visual && <Box sx={{ mt: 2 }}>{f.visual}</Box>}
                  </CardContent>
                </Card>
              </Box>
            </Grid>
          </Grid>
        </Section>
      ))}

      <Section tone="dark">
        <SectionHeading dark overline="Roadmap" title="Planned after the first release" lead="These are in the project requirements but come after the core payment path is finished." />
        <Grid container spacing={2}>
          {LATER.map((l) => (
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
        <Button component={RouterLink} to="/about" sx={{ color: brand.saffron, mt: 4, px: 0 }}>
          About the project and its timeline →
        </Button>
      </Section>

      <CtaBand />
    </>
  );
}
