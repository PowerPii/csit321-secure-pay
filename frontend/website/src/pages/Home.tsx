import { Box, Button, Container, Stack, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import { Link as RouterLink } from "react-router-dom";
import { CodeBlock } from "../components/CodeBlock";
import { CtaBand } from "../components/CtaBand";
import { Screenshot } from "../components/Screenshot";
import { Section, SectionHeading } from "../components/Section";
import { StatusChip } from "../components/StatusChip";
import { usePageTitle } from "../components/usePageTitle";
import { MEASURED, RULES, SCREENS, SHOP_URL, TEAM } from "../content/site";
import { CREATE_PAYMENT } from "../content/snippets";
import { brand, fonts, shadows } from "../theme";

const PILLARS = [
  {
    title: "Hosted checkout",
    text: "The store sends the customer to our payment page. The amount is set by the store's server when it creates the payment, so it can't be edited in the browser.",
    to: "/product#checkout",
  },
  {
    title: "Card vault",
    text: "Card details are encrypted with AES-256-GCM in a separate vault database and deleted once the payment is submitted. The store only gets a token.",
    to: "/product#vault",
  },
  {
    title: "Fraud screening",
    text: "Each payment goes through rules, a gradient-boosted model and a policy before the bank is asked. The result is allow, verify or block.",
    to: "/product#fraud",
  },
  {
    title: "Signed webhooks",
    text: "Each status change and its event are saved in one database transaction. Events are signed with HMAC-SHA256 and retried for 72 hours.",
    to: "/product#webhooks",
  },
  {
    title: "Safe retries",
    text: "Every POST takes an idempotency key, and every bank call has an operation ID saved before it is sent. A lost reply is checked again, not charged twice.",
    to: "/product#reliability",
  },
  {
    title: "Staff dashboard",
    text: "Operators capture, cancel and refund. Analysts work a review queue that shows why each payment was flagged.",
    to: "/product#dashboard",
  },
];

const STATS = [
  { value: MEASURED.screeningP95, label: `95th-percentile screening time over ${MEASURED.screeningRuns} payments at ${MEASURED.screeningRate}. Our target is ${RULES.screeningP95}.` },
  { value: MEASURED.modelRocAuc, label: "ROC-AUC of the fraud model on days of data it never saw in training. Modest, so rules and email codes back it up." },
  { value: "0", label: "card numbers kept after a payment is submitted. The vault row is deleted." },
  { value: MEASURED.automatedTests, label: "automated tests, run in CI on every pull request." },
];

const STEPS = [
  { n: "01", title: "Create a payment", text: "Your server calls POST /v1/payments with the amount and order. You get back a checkout link." },
  { n: "02", title: "Customer pays", text: "They enter a card on the hosted page. It is tokenised in the vault before anything else happens." },
  { n: "03", title: "Screening", text: `Rules, model and policy decide in about ${MEASURED.screeningP50} at median. Risky attempts get a one-time code by email.` },
  { n: "04", title: "Bank decides", text: "The simulated bank authorises or declines. Lost replies are reconciled with the original operation ID." },
  { n: "05", title: "Store is notified", text: "A signed webhook reaches the store. It checks the signature, ships the order and captures the funds." },
];

export default function Home() {
  usePageTitle("");
  return (
    <>
      {/* Hero */}
      <Box sx={{ pt: { xs: 6, md: 10 }, pb: { xs: 9, md: 12 } }}>
        <Container maxWidth="lg">
          <Grid container spacing={{ xs: 8, md: 8 }} alignItems="center">
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography sx={{ color: "text.secondary", fontWeight: 500, fontSize: 15, mb: 2.5 }}>
                Final-year project, simulated payments only
              </Typography>
              <Typography variant="h1" sx={{ fontSize: { xs: 40, sm: 50, md: 58 }, mb: 3, color: brand.navy, maxWidth: "14ch" }}>
                Every payment gets a reason before it gets a yes.
              </Typography>
              <Typography sx={{ fontSize: { xs: 18, md: 19 }, color: "text.secondary", lineHeight: 1.6, maxWidth: 540, mb: 4 }}>
                SecurePay is our CSIT321 final-year project. It takes Singapore dollar card payments through a hosted checkout, screens each one
                with rules, a model and a policy, and only then asks a bank simulator we wrote ourselves. It is running now, with a demo store you can
                buy from using test cards.
              </Typography>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                <Button href={SHOP_URL} target="_blank" rel="noopener" variant="contained" size="large" endIcon={<ArrowForwardRoundedIcon />}>
                  Try the demo store
                </Button>
                <Button component={RouterLink} to="/developers" variant="contained" color="secondary" size="large">
                  Read the API docs
                </Button>
              </Stack>
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <HeroCheckout />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Parts */}
      <Section tone="white">
        <Grid container spacing={{ xs: 5, md: 8 }}>
          <Grid size={{ xs: 12, md: 4 }}>
            <SectionHeading
              overline="What it does"
              title="Six parts, all built and running"
              lead="Screening runs before the bank is asked, so a blocked attempt never reaches the bank."
            />
          </Grid>
          <Grid size={{ xs: 12, md: 8 }}>
            <Box component="ul" sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, columnGap: 5 }}>
              {PILLARS.map((p) => (
                <Box component="li" key={p.title} sx={{ borderTop: `1px solid ${brand.line}`, py: 3 }}>
                  <Box
                    component={RouterLink}
                    to={p.to}
                    sx={{
                      color: brand.navy,
                      textDecoration: "none",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 0.75,
                      mb: 1,
                      "& svg": { transition: "transform .2s" },
                      "&:hover svg": { transform: "translateX(3px)" },
                      "&:hover": { textDecoration: "underline", textUnderlineOffset: 4 },
                    }}
                  >
                    <Typography component="span" variant="h5" sx={{ fontSize: 19 }}>
                      {p.title}
                    </Typography>
                    <ArrowForwardRoundedIcon sx={{ fontSize: 18 }} />
                  </Box>
                  <Typography sx={{ color: "text.secondary", lineHeight: 1.6 }}>{p.text}</Typography>
                </Box>
              ))}
            </Box>
          </Grid>
        </Grid>
      </Section>

      {/* Fraud pipeline */}
      <Section tone="dark">
        <Grid container spacing={{ xs: 6, md: 8 }} alignItems="center">
          <Grid size={{ xs: 12, md: 5 }}>
            <SectionHeading
              dark
              overline="Fraud screening"
              title="Rules, then a model, then a policy"
              lead={`Rules check the block list, bursts of attempts and amount limits. A HistGradientBoosting model, trained on the public IEEE-CIS fraud dataset, scores the payment and the card's recent history. The policy turns that score into one action, and the reasons are saved for the analyst.`}
            />
            <Button component={RouterLink} to="/product#fraud" sx={{ color: "#fff", px: 0 }} endIcon={<ArrowForwardRoundedIcon />}>
              How screening works
            </Button>
          </Grid>
          <Grid size={{ xs: 12, md: 7 }}>
            <PipelineDiagram />
          </Grid>
        </Grid>
      </Section>

      {/* Developer */}
      <Section tone="white">
        <Grid container spacing={{ xs: 6, md: 8 }} alignItems="center">
          <Grid size={{ xs: 12, md: 5 }}>
            <SectionHeading
              overline="For developers"
              title="Create a payment with one API call"
              lead="A REST API with seven endpoints. Amounts are whole numbers in cents and the currency is SGD. Every POST takes an idempotency key, and every reply is signed."
            />
            <Stack spacing={1.5} sx={{ mb: 4 }}>
              {[
                "Idempotency-Key on every POST, kept for 24 hours",
                "Each reply signed with your secret (SecurePay-Signature)",
                "30 documented error codes, each with a fixed name",
                "OpenAPI 3.1 contract and JSON Schemas in the repo",
              ].map((t) => (
                <Box key={t} sx={{ display: "flex", gap: 1.5, alignItems: "flex-start" }}>
                  <Box sx={{ mt: "9px", width: 6, height: 6, borderRadius: "50%", bgcolor: brand.brass, flexShrink: 0 }} />
                  <Typography sx={{ color: "text.secondary" }}>{t}</Typography>
                </Box>
              ))}
            </Stack>
            <Button component={RouterLink} to="/developers" variant="contained" endIcon={<ArrowForwardRoundedIcon />}>
              Developer overview
            </Button>
          </Grid>
          <Grid size={{ xs: 12, md: 7 }} sx={{ minWidth: 0 }}>
            <CodeBlock snippets={CREATE_PAYMENT} />
          </Grid>
        </Grid>
      </Section>

      {/* Stats */}
      <Section>
        <SectionHeading overline="Measured" title="Results from our own tests" align="center" />
        <Grid container spacing={2.5}>
          {STATS.map((s) => (
            <Grid key={s.label} size={{ xs: 6, md: 3 }}>
              <Box sx={{ borderTop: `1px solid ${brand.navy}`, pt: 2.5 }}>
                <Typography sx={{ fontFamily: fonts.heading, fontWeight: 600, fontSize: { xs: 34, md: 48 }, letterSpacing: "-0.035em", lineHeight: 1, color: brand.navy }}>
                  {s.value}
                </Typography>
                <Typography sx={{ color: "text.secondary", mt: 1.25, fontSize: 15, lineHeight: 1.5 }}>{s.label}</Typography>
              </Box>
            </Grid>
          ))}
        </Grid>
        <Typography sx={{ color: "text.secondary", fontSize: 13, mt: 4, textAlign: "center" }}>
          Latency measured on a 4 vCPU cloud VM running the full Docker stack. Model score from held-out data. These are test results, not production figures.
        </Typography>
      </Section>

      {/* Steps */}
      <Section tone="white">
        <SectionHeading overline="How it works" title="What happens when a customer pays" />
        <Grid container spacing={2}>
          {STEPS.map((s) => (
            <Grid key={s.n} size={{ xs: 12, sm: 6, md: 12 / 5 }}>
              <Box sx={{ height: "100%", p: 3, borderRadius: "14px", bgcolor: brand.mist }}>
                <Typography sx={{ fontFamily: fonts.heading, fontWeight: 600, color: brand.navy, fontSize: 15, mb: 2, fontVariantNumeric: "tabular-nums" }}>{s.n}</Typography>
                <Typography variant="h6" sx={{ mb: 1, fontSize: 18 }}>
                  {s.title}
                </Typography>
                <Typography sx={{ color: "text.secondary", fontSize: 15, lineHeight: 1.6 }}>{s.text}</Typography>
              </Box>
            </Grid>
          ))}
        </Grid>
      </Section>

      {/* Screens */}
      <Section>
        <SectionHeading
          overline="Screens"
          title="Taken from the running system"
          lead="These are screenshots of the gateway and the Volt & Co. demo store, not mock-ups. Volt & Co. is a fictional shop we built to test the gateway."
        />
        <Grid container spacing={4}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Screenshot shot={SCREENS.verify} caption="A payment flagged as risky. The customer must enter a 6-digit code sent by email, with 3 tries and 10 minutes." />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Screenshot shot={SCREENS.shop} caption="Volt & Co., the demo store. It calls the SecurePay API like any other merchant would." />
          </Grid>
          <Grid size={{ xs: 12 }}>
            <Screenshot
              shot={SCREENS.paymentDetail}
              caption="The merchant's view of one payment: capture or cancel, plus the fraud decision and the rule that fired."
            />
          </Grid>
        </Grid>
      </Section>

      {/* Team */}
      <Section tone="white">
        <Grid container spacing={{ xs: 4, md: 8 }} alignItems="center">
          <Grid size={{ xs: 12, md: 5 }}>
            <SectionHeading
              overline="Who we are"
              title="Five students at UOW, through SIM"
              lead="We are the CSIT321 project team, building SecurePay over 26 weeks from October 2026."
            />
            <Button component={RouterLink} to="/about#team" sx={{ px: 0 }} endIcon={<ArrowForwardRoundedIcon />}>
              Meet the team
            </Button>
          </Grid>
          <Grid size={{ xs: 12, md: 7 }}>
            {TEAM.map((m, i) => (
              <Box key={m.name} sx={{ display: "flex", justifyContent: "space-between", gap: 2, flexWrap: "wrap", py: 1.75, borderTop: i ? `1px solid ${brand.line}` : "none" }}>
                <Typography sx={{ fontWeight: 600 }}>{m.name}</Typography>
                <Typography sx={{ color: "text.secondary" }}>{m.role}</Typography>
              </Box>
            ))}
          </Grid>
        </Grid>
      </Section>

      <CtaBand />
    </>
  );
}

function PipelineDiagram() {
  const stage = (title: string, sub: string, extra?: React.ReactNode) => (
    <Box sx={{ flex: 1, p: 2.5, borderRadius: 3, bgcolor: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.10)", minWidth: 0 }}>
      <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.62)", mb: 0.75 }}>{sub}</Typography>
      <Typography sx={{ fontWeight: 600, mb: extra ? 1.5 : 0 }}>{title}</Typography>
      {extra}
    </Box>
  );
  const arrow = (
    <Box sx={{ display: "grid", placeItems: "center", color: "rgba(255,255,255,0.35)", fontSize: 22, px: { md: 0.5 }, transform: { xs: "rotate(90deg)", md: "none" } }}>
      →
    </Box>
  );
  return (
    <Box>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems="stretch">
        {stage(
          "Rules",
          "Step 1, fixed checks",
          <Typography sx={{ fontSize: 13.5, color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>Blocklisted card, bursts of attempts, amount limits</Typography>,
        )}
        {arrow}
        {stage(
          "Model",
          "Step 2, gradient boosting",
          <Typography sx={{ fontSize: 13.5, color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>Scores the payment and its card&apos;s recent activity</Typography>,
        )}
        {arrow}
        {stage(
          "Policy",
          "Step 3, versioned",
          <Typography sx={{ fontSize: 13.5, color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>Turns the score into one action, with reasons</Typography>,
        )}
      </Stack>
      <Box sx={{ mt: 2, display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" }, gap: 1.5 }}>
        {[
          { tone: "allow" as const, label: "allow", text: "Sent straight to the bank" },
          { tone: "verify" as const, label: "verify", text: `${RULES.verificationCodeDigits}-digit email code, ${RULES.verificationAttempts} tries` },
          { tone: "block" as const, label: "block", text: "Stopped. The bank is never asked" },
        ].map((d) => (
          <Box key={d.label} sx={{ p: 2, borderRadius: 3, bgcolor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.10)" }}>
            <StatusChip tone={d.tone} dark>
              {d.label}
            </StatusChip>
            <Typography sx={{ fontSize: 14, color: "rgba(255,255,255,0.7)", mt: 1.25 }}>{d.text}</Typography>
          </Box>
        ))}
      </Box>
      <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.62)", mt: 2 }}>
        If screening has no answer within {RULES.screeningTimeout}, the payment is blocked with the reason <code>screening_unavailable</code> rather than let through.
      </Typography>
    </Box>
  );
}

/** A small, built-in picture of the checkout, with the screening result chip. Not a screenshot, so it never goes stale. */
function HeroCheckout() {
  const field = { height: 44, border: "1px solid #7D8898", borderRadius: "8px", display: "flex", alignItems: "center", px: 1.5, fontSize: 15 } as const;
  return (
    <Box sx={{ position: "relative", maxWidth: 440, mx: { xs: "auto", md: 0 }, ml: { md: "auto" } }}>
      <Box
        role="img"
        aria-label="SecurePay checkout for the demo store Volt & Co.: S$34.80, test card 4242 4242 4242 4242, and a Pay button"
        sx={{ bgcolor: "#fff", borderRadius: "16px", boxShadow: shadows.float, p: { xs: 2.5, sm: 3.5 }, display: "grid", gap: 2 }}
      >
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, fontWeight: 600 }}>
            <Box sx={{ width: 30, height: 30, borderRadius: "8px", bgcolor: brand.navy, color: "#fff", display: "grid", placeItems: "center", fontSize: 12 }}>VC</Box>
            Volt &amp; Co.
          </Box>
          <Box sx={{ fontSize: 11.5, fontWeight: 600, letterSpacing: "0.04em", border: `1px solid ${brand.brass}`, color: brand.navy, borderRadius: 999, px: 1, py: 0.25 }}>
            Test mode
          </Box>
        </Box>
        <Box>
          <Typography sx={{ color: "text.secondary", fontSize: 14 }}>Total to pay</Typography>
          <Typography sx={{ fontFamily: fonts.heading, fontWeight: 600, fontSize: 38, letterSpacing: "-0.03em", lineHeight: 1.1, color: brand.navy }}>
            S$34.80
          </Typography>
        </Box>
        <Box sx={{ display: "grid", gap: 0.75, fontSize: 14, color: "text.secondary", borderTop: `1px solid ${brand.line}`, pt: 1.5 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between" }}>
            <span>Wireless mouse</span>
            <span>29.90</span>
          </Box>
          <Box sx={{ display: "flex", justifyContent: "space-between" }}>
            <span>Standard delivery</span>
            <span>4.90</span>
          </Box>
        </Box>
        <Box sx={{ ...field, borderColor: brand.brass, boxShadow: "0 0 0 3px rgba(176,138,62,0.3)", fontVariantNumeric: "tabular-nums" }}>4242 4242 4242 4242</Box>
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1.5 }}>
          <Box sx={field}>12 / 29</Box>
          <Box sx={field}>123</Box>
        </Box>
        <Box sx={{ height: 48, borderRadius: "9px", bgcolor: brand.navy, color: "#fff", display: "grid", placeItems: "center", fontWeight: 600 }}>Pay S$34.80</Box>
        <Typography sx={{ fontSize: 13, color: "text.secondary", textAlign: "center" }}>The shop never sees your card number.</Typography>
      </Box>
      <Box
        aria-hidden
        sx={{
          position: "absolute",
          left: { xs: 12, sm: -20 },
          bottom: -18,
          display: "flex",
          alignItems: "center",
          gap: 1,
          bgcolor: "#fff",
          borderRadius: 999,
          pl: 1,
          pr: 1.75,
          py: 0.9,
          boxShadow: shadows.float,
          fontWeight: 600,
          fontSize: 14,
          color: brand.ink,
          whiteSpace: "nowrap",
        }}
      >
        <Box sx={{ width: 20, height: 20, borderRadius: "50%", bgcolor: brand.brass, display: "grid", placeItems: "center" }}>
          <Box sx={{ width: 8, height: 4.5, borderLeft: "2px solid #fff", borderBottom: "2px solid #fff", transform: "rotate(-45deg) translate(1px,-1px)" }} />
        </Box>
        Allowed
        <Box component="span" sx={{ fontWeight: 500, color: "text.secondary", fontVariantNumeric: "tabular-nums" }}>
          screened in 21 ms
        </Box>
      </Box>
    </Box>
  );
}
