import { Box, Button, Card, CardContent, Container, Stack, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import ArrowForwardRoundedIcon from "@mui/icons-material/ArrowForwardRounded";
import ShoppingCartCheckoutRoundedIcon from "@mui/icons-material/ShoppingCartCheckoutRounded";
import LockPersonRoundedIcon from "@mui/icons-material/LockPersonRounded";
import RadarRoundedIcon from "@mui/icons-material/RadarRounded";
import WebhookRoundedIcon from "@mui/icons-material/WebhookRounded";
import ReplayRoundedIcon from "@mui/icons-material/ReplayRounded";
import DashboardRoundedIcon from "@mui/icons-material/DashboardRounded";
import { Link as RouterLink } from "react-router-dom";
import { CodeBlock } from "../components/CodeBlock";
import { CtaBand } from "../components/CtaBand";
import { HeroVisual } from "../components/HeroVisual";
import { Section, SectionHeading } from "../components/Section";
import { StatusChip } from "../components/StatusChip";
import { usePageTitle } from "../components/usePageTitle";
import { RULES } from "../content/site";
import { CREATE_PAYMENT } from "../content/snippets";
import { brand, fonts } from "../theme";

const PILLARS = [
  {
    icon: <ShoppingCartCheckoutRoundedIcon />,
    title: "Hosted checkout",
    text: "A payment page you link to, not build. The amount is fixed on our side, so nobody can change the price in the browser.",
    to: "/product#checkout",
  },
  {
    icon: <LockPersonRoundedIcon />,
    title: "Card vault",
    text: "Card details go straight into an encrypted vault and are deleted once the payment is submitted. Your servers only see a token.",
    to: "/product#vault",
  },
  {
    icon: <RadarRoundedIcon />,
    title: "Fraud screening",
    text: "Every payment passes rules, a machine-learning model and a policy before the bank is asked. Allow, verify or block.",
    to: "/product#fraud",
  },
  {
    icon: <WebhookRoundedIcon />,
    title: "Signed webhooks",
    text: "Each status change is written with its event in one transaction, signed with HMAC-SHA256 and retried for 72 hours.",
    to: "/product#webhooks",
  },
  {
    icon: <ReplayRoundedIcon />,
    title: "Safe retries",
    text: "Idempotency keys and stored operation IDs mean a timeout never turns into a double charge.",
    to: "/product#reliability",
  },
  {
    icon: <DashboardRoundedIcon />,
    title: "Staff dashboard",
    text: "Find any payment, see why it was screened the way it was, then capture, cancel or refund it.",
    to: "/product#dashboard",
  },
];

const STATS = [
  { value: "≤ 200 ms", label: "screening time target at the 95th percentile" },
  { value: "0", label: "card numbers kept after the payment is submitted" },
  { value: "72 h", label: "of signed webhook retries, 14 attempts in all" },
  { value: "24 h", label: "idempotency window on every POST" },
];

const STEPS = [
  { n: "01", title: "Create a payment", text: "Your server calls POST /v1/payments with the amount and order. You get back a checkout link." },
  { n: "02", title: "Customer pays", text: "They enter a card on the hosted page. It is tokenised in the vault before anything else happens." },
  { n: "03", title: "We screen it", text: "Rules, model and policy decide in milliseconds. Risky attempts get a one-time code by email." },
  { n: "04", title: "Bank decides", text: "The simulated bank authorises or declines. Lost replies are reconciled with the original operation ID." },
  { n: "05", title: "You get told", text: "A signed webhook reaches your store. Confirm it, ship the order, capture the funds." },
];

export default function Home() {
  usePageTitle("");
  return (
    <>
      {/* Hero */}
      <Box
        sx={{
          position: "relative",
          overflow: "hidden",
          bgcolor: brand.inkDeep,
          color: "#fff",
          pt: { xs: 7, md: 11 },
          pb: { xs: 9, md: 13 },
          backgroundImage: `radial-gradient(900px 500px at 90% 10%, rgba(245,165,36,0.20), transparent 60%), radial-gradient(700px 500px at 0% 100%, rgba(127,179,255,0.16), transparent 60%), linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)`,
          backgroundSize: "auto, auto, 44px 44px, 44px 44px",
        }}
      >
        <Container maxWidth="lg">
          <Grid container spacing={{ xs: 7, md: 6 }} alignItems="center">
            <Grid size={{ xs: 12, md: 6 }}>
              <Box
                sx={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 1,
                  px: 1.5,
                  py: 0.5,
                  mb: 3,
                  borderRadius: 999,
                  border: "1px solid rgba(255,255,255,0.18)",
                  bgcolor: "rgba(255,255,255,0.05)",
                  fontSize: 13.5,
                  color: "rgba(255,255,255,0.85)",
                }}
              >
                <Box component="span" sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: brand.saffron }} />
                Final-year project · simulated payments only
              </Box>
              <Typography variant="h1" sx={{ fontSize: { xs: 44, sm: 56, md: 68 }, mb: 3 }}>
                Payments that check{" "}
                <Box component="span" sx={{ color: brand.saffron }}>
                  before
                </Box>{" "}
                they charge.
              </Typography>
              <Typography sx={{ fontSize: { xs: 18, md: 20 }, color: "rgba(255,255,255,0.75)", lineHeight: 1.6, maxWidth: 540, mb: 4 }}>
                SecurePay is a payment gateway with fraud screening inside the payment itself. One API gives a merchant a hosted checkout, a card vault,
                risk decisions and signed webhooks, built for Singapore dollar payments.
              </Typography>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                <Button component={RouterLink} to="/contact" variant="contained" color="secondary" size="large" endIcon={<ArrowForwardRoundedIcon />}>
                  Book a demo
                </Button>
                <Button component={RouterLink} to="/developers" size="large" sx={{ color: "#fff", border: "1px solid rgba(255,255,255,0.3)" }}>
                  Explore the API
                </Button>
              </Stack>
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <HeroVisual />
            </Grid>
          </Grid>
        </Container>
      </Box>

      {/* Built with */}
      <Box sx={{ borderBottom: `1px solid ${brand.line}`, bgcolor: "#fff", py: 3.5 }}>
        <Container maxWidth="lg">
          <Stack direction={{ xs: "column", md: "row" }} spacing={{ xs: 2, md: 5 }} alignItems={{ md: "center" }}>
            <Typography sx={{ color: "text.secondary", fontSize: 14, fontWeight: 500, flexShrink: 0 }}>Built on open tools</Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", columnGap: { xs: 3, md: 5 }, rowGap: 1.5 }}>
              {["Django", "PostgreSQL", "React", "TypeScript", "scikit-learn", "Docker"].map((t) => (
                <Typography key={t} sx={{ fontFamily: fonts.heading, fontWeight: 600, fontSize: { xs: 17, md: 20 }, color: "#8A8F99" }}>
                  {t}
                </Typography>
              ))}
            </Box>
          </Stack>
        </Container>
      </Box>

      {/* Pillars */}
      <Section>
        <SectionHeading
          overline="One gateway"
          title="Everything between “Pay” and “Paid”"
          lead="Most fraud tools are bolted on after the fact. SecurePay makes the risk decision part of the payment, so a blocked attempt never reaches the bank."
        />
        <Grid container spacing={2.5}>
          {PILLARS.map((p) => (
            <Grid key={p.title} size={{ xs: 12, sm: 6, md: 4 }}>
              <Card
                component={RouterLink}
                to={p.to}
                sx={{
                  height: "100%",
                  textDecoration: "none",
                  display: "block",
                  transition: "transform .2s, box-shadow .2s, border-color .2s",
                  "&:hover": { transform: "translateY(-3px)", boxShadow: "0 20px 40px -24px rgba(15,34,64,0.35)", borderColor: "#CFC7B8" },
                }}
              >
                <CardContent sx={{ p: 3.5 }}>
                  <Box sx={{ width: 44, height: 44, borderRadius: 2.5, display: "grid", placeItems: "center", bgcolor: brand.ink, color: brand.saffron, mb: 2.5 }}>
                    {p.icon}
                  </Box>
                  <Typography variant="h5" sx={{ fontSize: 20, mb: 1 }}>
                    {p.title}
                  </Typography>
                  <Typography sx={{ color: "text.secondary", lineHeight: 1.6 }}>{p.text}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Section>

      {/* Fraud pipeline */}
      <Section tone="dark">
        <Grid container spacing={{ xs: 6, md: 8 }} alignItems="center">
          <Grid size={{ xs: 12, md: 5 }}>
            <SectionHeading
              dark
              overline="Fraud screening"
              title="Three answers, decided in the payment path"
              lead={`Deterministic rules catch the obvious cases. A gradient-boosted model scores the rest. A versioned policy turns the score into an action, and every decision keeps its reasons for the analyst.`}
            />
            <Button component={RouterLink} to="/product#fraud" sx={{ color: brand.saffron, px: 0 }} endIcon={<ArrowForwardRoundedIcon />}>
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
              title="One request to start taking payments"
              lead="A small REST API with predictable errors, idempotency on every POST and signed replies. Amounts are integers in cents; currency is SGD."
            />
            <Stack spacing={1.5} sx={{ mb: 4 }}>
              {[
                "Idempotency-Key on every POST, kept for 24 hours",
                "Each reply signed with your secret (SecurePay-Signature)",
                "Errors you can branch on by code, not by message",
                "OpenAPI 3.1 contract and JSON Schemas in the repo",
              ].map((t) => (
                <Box key={t} sx={{ display: "flex", gap: 1.5, alignItems: "flex-start" }}>
                  <Box sx={{ mt: "9px", width: 6, height: 6, borderRadius: "50%", bgcolor: brand.saffron, flexShrink: 0 }} />
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
        <SectionHeading overline="Built to be checked" title="Numbers we design and test against" align="center" />
        <Grid container spacing={2.5}>
          {STATS.map((s) => (
            <Grid key={s.label} size={{ xs: 6, md: 3 }}>
              <Box sx={{ borderTop: `2px solid ${brand.ink}`, pt: 2.5 }}>
                <Typography sx={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: { xs: 34, md: 48 }, letterSpacing: "-0.03em", lineHeight: 1 }}>
                  {s.value}
                </Typography>
                <Typography sx={{ color: "text.secondary", mt: 1.25, fontSize: 15, lineHeight: 1.5 }}>{s.label}</Typography>
              </Box>
            </Grid>
          ))}
        </Grid>
        <Typography sx={{ color: "text.secondary", fontSize: 13, mt: 4, textAlign: "center" }}>
          Targets from the project requirements, measured at {RULES.throughputTarget} on the test server. Not production figures.
        </Typography>
      </Section>

      {/* Steps */}
      <Section tone="white">
        <SectionHeading overline="How it works" title="From cart to captured in five steps" />
        <Grid container spacing={2}>
          {STEPS.map((s) => (
            <Grid key={s.n} size={{ xs: 12, sm: 6, md: 12 / 5 }}>
              <Box sx={{ height: "100%", p: 3, borderRadius: 4, bgcolor: brand.paper, border: `1px solid ${brand.line}` }}>
                <Typography sx={{ fontFamily: fonts.mono, color: "#B26F00", fontSize: 14, mb: 2 }}>{s.n}</Typography>
                <Typography variant="h6" sx={{ mb: 1, fontSize: 18 }}>
                  {s.title}
                </Typography>
                <Typography sx={{ color: "text.secondary", fontSize: 15, lineHeight: 1.6 }}>{s.text}</Typography>
              </Box>
            </Grid>
          ))}
        </Grid>
      </Section>

      <CtaBand />
    </>
  );
}

function PipelineDiagram() {
  const stage = (title: string, sub: string, extra?: React.ReactNode) => (
    <Box sx={{ flex: 1, p: 2.5, borderRadius: 3, bgcolor: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.12)", minWidth: 0 }}>
      <Typography sx={{ fontFamily: fonts.mono, fontSize: 12, color: brand.saffron, mb: 0.75 }}>{sub}</Typography>
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
          "01 · deterministic",
          <Typography sx={{ fontSize: 13.5, color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>Blocklisted card, bursts of attempts, amount limits</Typography>,
        )}
        {arrow}
        {stage(
          "Model",
          "02 · gradient boosting",
          <Typography sx={{ fontSize: 13.5, color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>Scores the payment and its card&apos;s recent activity</Typography>,
        )}
        {arrow}
        {stage(
          "Policy",
          "03 · versioned",
          <Typography sx={{ fontSize: 13.5, color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>Turns the score into one action, with reasons</Typography>,
        )}
      </Stack>
      <Box sx={{ mt: 2, display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(3, 1fr)" }, gap: 1.5 }}>
        {[
          { tone: "allow" as const, label: "allow", text: "Sent straight to the bank" },
          { tone: "verify" as const, label: "verify", text: `${RULES.verificationCodeDigits}-digit email code, ${RULES.verificationAttempts} tries` },
          { tone: "block" as const, label: "block", text: "Stopped. The bank is never asked" },
        ].map((d) => (
          <Box key={d.label} sx={{ p: 2, borderRadius: 3, bgcolor: "rgba(255,255,255,0.03)", border: "1px dashed rgba(255,255,255,0.16)" }}>
            <StatusChip tone={d.tone} dark>
              {d.label}
            </StatusChip>
            <Typography sx={{ fontSize: 14, color: "rgba(255,255,255,0.7)", mt: 1.25 }}>{d.text}</Typography>
          </Box>
        ))}
      </Box>
      <Typography sx={{ fontSize: 13, color: "rgba(255,255,255,0.5)", mt: 2 }}>
        If screening cannot answer within {RULES.screeningTimeout}, the payment is blocked as <code>screening_unavailable</code>. We fail closed.
      </Typography>
    </Box>
  );
}
