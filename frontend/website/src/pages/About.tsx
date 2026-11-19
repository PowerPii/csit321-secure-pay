import { Box, Card, CardContent, Link, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import { CtaBand } from "../components/CtaBand";
import { PageHero, Section, SectionHeading } from "../components/Section";
import { usePageTitle } from "../components/usePageTitle";
import { REPO_URL, TEAM } from "../content/site";
import { brand, fonts } from "../theme";

const BELIEFS = [
  {
    title: "Screen before the bank is asked",
    text: "If fraud is found after the bank approves, the merchant has to refund it. So screening runs first, and a blocked payment never reaches the bank.",
  },
  {
    title: "Plan for lost replies",
    text: "Our bank simulator can be told to drop replies, answer late or forget a request. The gateway has to cope with each case, and the demo shows it.",
  },
  {
    title: "Back every number with a test",
    text: "Each requirement maps to a test. Performance figures state the load they were measured at. The fraud model is scored on later days it never trained on.",
  },
];

const PROJECT = [
  { k: "Subject", v: "CSIT321 Project" },
  { k: "University", v: "University of Wollongong, with the Singapore Institute of Management" },
  { k: "Duration", v: "20 weeks, from the week of 5 October 2026 to 20 February 2027" },
  { k: "Stack", v: "Django + DRF, PostgreSQL, React + TypeScript, scikit-learn" },
];

function initials(name: string) {
  const parts = name.split(" ");
  return (parts[0][0] + (parts[parts.length - 1][0] ?? "")).toUpperCase();
}

export default function About() {
  usePageTitle("About");
  return (
    <>
      <PageHero
        overline="About"
        title="Five students, one payment gateway"
        lead="SecurePay is our CSIT321 final-year project: a working payment gateway prototype that screens every payment for fraud before the bank is asked. It handles test cards only."
      />

      <Section>
        <SectionHeading overline="Design choices" title="Three rules we built to" />
        <Grid container spacing={2.5}>
          {BELIEFS.map((b, i) => (
            <Grid key={b.title} size={{ xs: 12, md: 4 }}>
              <Box sx={{ borderTop: `2px solid ${brand.navy}`, pt: 3 }}>
                <Typography sx={{ fontFamily: fonts.mono, color: "text.secondary", fontSize: 14, mb: 1.5 }}>0{i + 1}</Typography>
                <Typography variant="h5" sx={{ mb: 1.5 }}>
                  {b.title}
                </Typography>
                <Typography sx={{ color: "text.secondary", lineHeight: 1.7 }}>{b.text}</Typography>
              </Box>
            </Grid>
          ))}
        </Grid>
      </Section>

      <Section tone="white" id="team">
        <SectionHeading overline="The team" title="Who builds SecurePay" />
        <Grid container spacing={2.5}>
          {TEAM.map((m) => (
            <Grid key={m.name} size={{ xs: 12, sm: 6, md: 4 }}>
              <Card sx={{ height: "100%" }}>
                <CardContent sx={{ p: 3.5 }}>
                  <Box
                    sx={{
                      width: 56,
                      height: 56,
                      borderRadius: "50%",
                      display: "grid",
                      placeItems: "center",
                      bgcolor: brand.navy,
                      color: brand.brassLight,
                      fontFamily: fonts.heading,
                      fontWeight: 700,
                      fontSize: 20,
                      mb: 2.5,
                    }}
                    aria-hidden
                  >
                    {initials(m.name)}
                  </Box>
                  <Typography variant="h6" sx={{ fontSize: 19 }}>
                    {m.name}
                  </Typography>
                  <Typography sx={{ color: "text.secondary", fontWeight: 600, fontSize: 14.5, mb: 1.5 }}>{m.role}</Typography>
                  <Typography sx={{ color: "text.secondary", fontSize: 15, lineHeight: 1.6 }}>{m.text}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Section>

      <Section>
        <Grid container spacing={{ xs: 4, md: 8 }}>
          <Grid size={{ xs: 12, md: 5 }}>
            <SectionHeading
              overline="The project"
              title="Built in the open"
              lead={
                <>
                  The code, the API contracts and the requirements live in one repository, which assessors can see on request.{" "}
                  <Link href={REPO_URL} target="_blank" rel="noopener" underline="always">
                    See it on GitHub
                  </Link>
                  .
                </>
              }
            />
          </Grid>
          <Grid size={{ xs: 12, md: 7 }}>
            {PROJECT.map((p, i) => (
              <Box
                key={p.k}
                sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "160px 1fr" }, gap: 1, py: 2.25, borderTop: i ? `1px solid ${brand.line}` : "none" }}
              >
                <Typography sx={{ color: "text.secondary" }}>{p.k}</Typography>
                <Typography sx={{ fontWeight: 500 }}>{p.v}</Typography>
              </Box>
            ))}
          </Grid>
        </Grid>
      </Section>

      <Section tone="white" id="disclaimer">
        <Box sx={{ maxWidth: 820 }}>
          <Typography variant="overline" component="p" sx={{ color: "text.secondary", mb: 1.5 }}>
            Disclaimer
          </Typography>
          <Typography variant="h3" sx={{ fontSize: { xs: 26, md: 34 }, mb: 2.5 }}>
            SecurePay is a student project, not a payment company
          </Typography>
          <Box component="ul" sx={{ color: "text.secondary", lineHeight: 1.8, pl: 2.5, m: 0, fontSize: 17 }}>
            <li>SecurePay is not a licensed or registered payment service provider and is not regulated by the Monetary Authority of Singapore.</li>
            <li>It does not accept, hold or move real money, and is not connected to any card network, bank or acquirer.</li>
            <li>All payments go to a simulated bank, and only synthetic test card numbers work. Please never enter a real card.</li>
            <li>Pricing on this site is illustrative and is not an offer of service.</li>
            <li>Mentions of other payment companies or standards are for comparison and design reference only, and don’t imply any endorsement or certification.</li>
          </Box>
        </Box>
      </Section>

      <CtaBand title="Want to see it working?" lead="We can run the demo for supervisors, assessors or anyone who wants to see how a payment gateway works inside." />
    </>
  );
}
