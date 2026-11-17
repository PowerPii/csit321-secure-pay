import { Box, Card, CardContent, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import HttpsRoundedIcon from "@mui/icons-material/HttpsRounded";
import KeyRoundedIcon from "@mui/icons-material/KeyRounded";
import FingerprintRoundedIcon from "@mui/icons-material/FingerprintRounded";
import VerifiedUserRoundedIcon from "@mui/icons-material/VerifiedUserRounded";
import HistoryEduRoundedIcon from "@mui/icons-material/HistoryEduRounded";
import ShieldRoundedIcon from "@mui/icons-material/ShieldRounded";
import PolicyRoundedIcon from "@mui/icons-material/PolicyRounded";
import BugReportRoundedIcon from "@mui/icons-material/BugReportRounded";
import { CtaBand } from "../components/CtaBand";
import { PageHero, Section, SectionHeading } from "../components/Section";
import { usePageTitle } from "../components/usePageTitle";
import { RULES } from "../content/site";
import { brand } from "../theme";

const CONTROLS = [
  { icon: <HttpsRoundedIcon />, title: "Encrypted in transit", text: "HTTPS only, TLS 1.2 or higher. Plain HTTP is refused, and webhooks go only to HTTPS endpoints." },
  { icon: <KeyRoundedIcon />, title: "Card vault", text: "Card data is encrypted with AES-256-GCM in its own database with its own key, and deleted once the payment is submitted." },
  { icon: <FingerprintRoundedIcon />, title: "Keyed fingerprints", text: "Screening recognises repeat cards through a keyed fingerprint, never the card number itself." },
  { icon: <VerifiedUserRoundedIcon />, title: "Staff MFA", text: `Every staff account signs in with a password and TOTP. ${RULES.staffLockout} lockout.` },
  { icon: <HistoryEduRoundedIcon />, title: "Audit trail", text: "Every sign-in and every payment state change is written to an audit log with a request ID." },
  { icon: <ShieldRoundedIcon />, title: "Signed messages", text: "API replies and webhooks are signed with HMAC-SHA256 and carry a timestamp to stop replays." },
  { icon: <PolicyRoundedIcon />, title: "Least privilege", text: "Operators, analysts and administrators see only what their role allows; merchants only their own data." },
  { icon: <BugReportRoundedIcon />, title: "Attack tests", text: "Automated tests try amount tampering, replayed webhooks, duplicate requests and reading another merchant’s data." },
];

const REFERENCES = [
  { name: "PCI DSS v4.0.1", text: "Used as a design reference for how card data is handled. SecurePay is not PCI certified." },
  { name: "MAS Technology Risk Management Guidelines (2021)", text: "Used to shape access control, logging and recovery. SecurePay is not regulated by MAS." },
  { name: "Singapore PDPA", text: "Personal data is limited to what payments need and kept for 12 months." },
  { name: "OWASP API Security Top 10 (2023)", text: "Used as a checklist for the test and attack suite." },
];

export default function Security() {
  usePageTitle("Security");
  return (
    <>
      <PageHero
        overline="Security"
        title="How SecurePay protects a payment"
        lead="We started from a threat model. Each trust boundary has a named control, a requirement in our specification, and a test that checks it."
      />
      <Section>
        <SectionHeading overline="Controls" title="What protects a payment" />
        <Grid container spacing={2.5}>
          {CONTROLS.map((c) => (
            <Grid key={c.title} size={{ xs: 12, sm: 6, md: 3 }}>
              <Card sx={{ height: "100%" }}>
                <CardContent sx={{ p: 3 }}>
                  <Box sx={{ color: brand.ink, mb: 1.5 }}>{c.icon}</Box>
                  <Typography variant="h6" sx={{ fontSize: 17, mb: 1 }}>
                    {c.title}
                  </Typography>
                  <Typography sx={{ color: "text.secondary", fontSize: 15, lineHeight: 1.6 }}>{c.text}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Section>
      <Section tone="white">
        <Grid container spacing={{ xs: 4, md: 8 }}>
          <Grid size={{ xs: 12, md: 5 }}>
            <SectionHeading
              overline="Standards"
              title="References, not certifications"
              lead="We used these standards to decide what to build and test. A university prototype can’t be certified against them, and we don’t claim it is."
            />
          </Grid>
          <Grid size={{ xs: 12, md: 7 }}>
            {REFERENCES.map((r, i) => (
              <Box key={r.name} sx={{ py: 2.5, borderTop: i ? `1px solid ${brand.line}` : "none" }}>
                <Typography sx={{ fontWeight: 600, mb: 0.5 }}>{r.name}</Typography>
                <Typography sx={{ color: "text.secondary", lineHeight: 1.6 }}>{r.text}</Typography>
              </Box>
            ))}
          </Grid>
        </Grid>
      </Section>
      <Section>
        <Box sx={{ p: { xs: 3, md: 5 }, borderRadius: 4, bgcolor: "#FFF6E5", border: "1px solid #F3D9A4", maxWidth: 860 }}>
          <Typography variant="h5" sx={{ mb: 1.5 }}>
            Never use real card details
          </Typography>
          <Typography sx={{ lineHeight: 1.7 }}>
            SecurePay runs against a simulated bank and accepts only published test card numbers. Please don’t enter a real card on any SecurePay page. If you find a security
            problem in the project code, open an issue on GitHub or contact the team, and leave out any exploit details from public posts.
          </Typography>
        </Box>
      </Section>
      <CtaBand title="Ask us to show a control working" lead="In the demo we can show a tampered amount refused, a replayed webhook rejected and a lost bank reply reconciled." />
    </>
  );
}
