import { Alert, Box, Button, Card, CardContent, Divider, Slider, Stack, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import { useMemo, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { CtaBand } from "../components/CtaBand";
import { PageHero, Section, SectionHeading } from "../components/Section";
import { usePageTitle } from "../components/usePageTitle";
import { brand, fonts } from "../theme";

/** Illustrative only. SecurePay charges nobody; these numbers show how a gateway might price. */
const RATE = 0.029;
const FIXED = 0.3;

const PLANS = [
  {
    name: "Sandbox",
    price: "S$0",
    unit: "always",
    blurb: "Everything in the demo, against the simulated bank.",
    features: ["Hosted checkout and card vault", "Fraud screening on every payment", "Signed webhooks and test cards", "Staff dashboard with TOTP"],
    cta: "Ask for a demo",
    highlight: true,
  },
  {
    name: "Standard",
    price: "2.9% + S$0.30",
    unit: "per successful card payment",
    blurb: "How a launched version might charge. No setup or monthly fee.",
    features: ["Everything in Sandbox", "No charge for blocked or declined attempts", "Refunds at no extra fee", "Email support"],
    cta: "Talk to us",
    highlight: false,
  },
  {
    name: "Custom",
    price: "Let’s talk",
    unit: "volume pricing",
    blurb: "For high volumes or special fraud needs, in a launched version.",
    features: ["Everything in Standard", "Custom fraud rules and policy", "Dedicated review queue", "Volume-based rates"],
    cta: "Contact us",
    highlight: false,
  },
];

const FAQ = [
  {
    q: "Can I pay or get paid with SecurePay today?",
    a: "No. SecurePay is a university project. It runs against a simulated bank, accepts only test card numbers and moves no real money.",
  },
  {
    q: "Why show prices at all?",
    a: "A gateway’s pricing shapes its design: for example, not charging for blocked attempts means fraud screening must be cheap to run. The figures illustrate that; they aren’t an offer.",
  },
  { q: "Which currencies are supported?", a: "Singapore dollars only, from S$0.50 to S$10,000 per payment." },
  { q: "Are refunds charged?", a: "In this illustration, no. Full and partial refunds are free, up to the amount captured." },
];

const fmt = (n: number) => `S$${n.toLocaleString("en-SG", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function Pricing() {
  usePageTitle("Pricing");
  const [avg, setAvg] = useState(45);
  const [count, setCount] = useState(800);
  const fees = useMemo(() => count * (avg * RATE + FIXED), [avg, count]);

  return (
    <>
      <PageHero
        overline="Pricing"
        title="Example pricing"
        lead="SecurePay is a student project and charges nobody. The plans below show how a gateway like it could be priced if it were launched."
      />
      <Section>
        <Alert severity="warning" sx={{ mb: 5, borderRadius: 3, alignItems: "center" }}>
          <strong>Illustrative only.</strong> SecurePay is not a licensed payment provider. Nothing on this page is an offer of service.
        </Alert>
        <Grid container spacing={2.5}>
          {PLANS.map((p) => (
            <Grid key={p.name} size={{ xs: 12, md: 4 }}>
              <Card
                sx={{
                  height: "100%",
                  display: "flex",
                  flexDirection: "column",
                  ...(p.highlight ? { bgcolor: brand.ink, color: "#fff", borderColor: brand.ink } : {}),
                }}
              >
                <CardContent sx={{ p: 4, display: "flex", flexDirection: "column", flex: 1 }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                    <Typography variant="h5">{p.name}</Typography>
                    {p.highlight && (
                      <Box sx={{ bgcolor: brand.saffron, color: brand.inkDeep, px: 1.25, py: 0.25, borderRadius: 999, fontSize: 12.5, fontWeight: 700 }}>
                        Available now
                      </Box>
                    )}
                  </Stack>
                  <Typography sx={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: 34, letterSpacing: "-0.02em", lineHeight: 1.1 }}>{p.price}</Typography>
                  <Typography sx={{ fontSize: 14, opacity: 0.7, mb: 2 }}>{p.unit}</Typography>
                  <Typography sx={{ opacity: 0.8, mb: 3, lineHeight: 1.6 }}>{p.blurb}</Typography>
                  <Divider sx={{ borderColor: p.highlight ? "rgba(255,255,255,0.15)" : undefined, mb: 2.5 }} />
                  <Stack spacing={1.25} sx={{ mb: 4, flex: 1 }}>
                    {p.features.map((f) => (
                      <Box key={f} sx={{ display: "flex", gap: 1.25 }}>
                        <CheckRoundedIcon sx={{ fontSize: 20, color: p.highlight ? brand.saffron : brand.allow }} />
                        <Typography sx={{ fontSize: 15 }}>{f}</Typography>
                      </Box>
                    ))}
                  </Stack>
                  <Button
                    component={RouterLink}
                    to="/contact"
                    variant={p.highlight ? "contained" : "outlined"}
                    color={p.highlight ? "secondary" : "primary"}
                    size="large"
                    fullWidth
                  >
                    {p.cta}
                  </Button>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Section>

      <Section tone="white">
        <Grid container spacing={{ xs: 4, md: 8 }} alignItems="center">
          <Grid size={{ xs: 12, md: 5 }}>
            <SectionHeading
              overline="Fee calculator"
              title="What would a month cost?"
              lead="Move the sliders to see the illustrative Standard fee. Blocked and declined attempts are not counted."
            />
          </Grid>
          <Grid size={{ xs: 12, md: 7 }}>
            <Card>
              <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                <Typography sx={{ fontWeight: 600, mb: 0.5 }}>Average payment: {fmt(avg)}</Typography>
                <Slider value={avg} min={1} max={500} onChange={(_, v) => setAvg(v as number)} aria-label="Average payment" sx={{ mb: 3 }} />
                <Typography sx={{ fontWeight: 600, mb: 0.5 }}>Successful payments a month: {count.toLocaleString("en-SG")}</Typography>
                <Slider value={count} min={10} max={10000} step={10} onChange={(_, v) => setCount(v as number)} aria-label="Payments a month" sx={{ mb: 3 }} />
                <Box
                  sx={{ p: 3, borderRadius: 3, bgcolor: brand.paper, display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 1 }}
                >
                  <Typography sx={{ color: "text.secondary" }}>Illustrative monthly fees</Typography>
                  <Typography sx={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: 32 }}>{fmt(fees)}</Typography>
                </Box>
                <Typography sx={{ color: "text.secondary", fontSize: 13, mt: 1.5 }}>On {fmt(avg * count)} of sales. Example figures, not a quote.</Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Section>

      <Section>
        <SectionHeading overline="FAQ" title="Questions about pricing" />
        <Grid container spacing={4}>
          {FAQ.map((f) => (
            <Grid key={f.q} size={{ xs: 12, md: 6 }}>
              <Typography sx={{ fontWeight: 600, fontSize: 18, mb: 1 }}>{f.q}</Typography>
              <Typography sx={{ color: "text.secondary", lineHeight: 1.7 }}>{f.a}</Typography>
            </Grid>
          ))}
        </Grid>
      </Section>
      <CtaBand />
    </>
  );
}
