import { Alert, Box, Button, Card, CardContent, Link, MenuItem, Stack, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import CheckCircleRoundedIcon from "@mui/icons-material/CheckCircleRounded";
import GitHubIcon from "@mui/icons-material/GitHub";
import { useState, type FormEvent } from "react";
import { PageHero, Section } from "../components/Section";
import { usePageTitle } from "../components/usePageTitle";
import { CONTACT_EMAIL, REPO_URL } from "../content/site";
import { brand } from "../theme";

const TOPICS = ["Ask for a live demo", "Question about the project", "Developer or API question", "Report a security issue", "Privacy or personal data request", "Something else"];

const DEMO_COVERS = [
  "A purchase in the demo shop, paid on the hosted checkout",
  "A risky payment that needs the one-time code",
  "A blocked attempt and the analyst’s view of why",
  "A lost bank reply reconciled without a double charge",
  "Signed webhooks, capture and partial refunds",
];

export default function Contact() {
  usePageTitle("Contact");
  const [form, setForm] = useState({ name: "", email: "", org: "", topic: TOPICS[0], message: "" });
  const [sent, setSent] = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (CONTACT_EMAIL) {
      const body = `${form.message}\n\n${form.name}${form.org ? `, ${form.org}` : ""}\n${form.email}`;
      window.location.href = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(`[SecurePay] ${form.topic}`)}&body=${encodeURIComponent(body)}`;
    }
    setSent(true);
  };

  return (
    <>
      <PageHero overline="Contact" title="Contact the team" lead="Ask for a live demo, a walkthrough of the code, or anything about the project." />
      <Section>
        <Grid container spacing={{ xs: 5, md: 8 }}>
          <Grid size={{ xs: 12, md: 7 }}>
            <Card>
              <CardContent sx={{ p: { xs: 3, md: 4.5 } }}>
                {sent ? (
                  <Box sx={{ textAlign: "center", py: 4 }}>
                    <CheckCircleRoundedIcon sx={{ fontSize: 48, color: brand.allow, mb: 2 }} />
                    <Typography variant="h5" sx={{ mb: 1 }}>
                      {CONTACT_EMAIL ? "Your email app should open now" : "Thanks for your interest"}
                    </Typography>
                    <Typography sx={{ color: "text.secondary", mb: 3, maxWidth: 440, mx: "auto" }}>
                      {CONTACT_EMAIL ? (
                        <>
                          If it didn’t, write to <Link href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</Link>.
                        </>
                      ) : (
                        "This form doesn’t send messages yet. The quickest way to reach the team is an issue on our GitHub repository."
                      )}
                    </Typography>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} justifyContent="center">
                      {!CONTACT_EMAIL && (
                        <Button href={`${REPO_URL}/issues/new`} target="_blank" rel="noopener" variant="contained" startIcon={<GitHubIcon />}>
                          Open a GitHub issue
                        </Button>
                      )}
                      <Button onClick={() => setSent(false)}>Back to the form</Button>
                    </Stack>
                  </Box>
                ) : (
                  <Box component="form" onSubmit={submit}>
                    <Typography variant="h5" component="h2" sx={{ mb: 3 }}>
                      Send us a message
                    </Typography>
                    <Grid container spacing={2}>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField label="Name" value={form.name} onChange={set("name")} required fullWidth autoComplete="name" />
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField label="Email" type="email" value={form.email} onChange={set("email")} required fullWidth autoComplete="email" />
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField label="Organisation (optional)" value={form.org} onChange={set("org")} fullWidth autoComplete="organization" />
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField select label="Topic" value={form.topic} onChange={set("topic")} fullWidth>
                          {TOPICS.map((t) => (
                            <MenuItem key={t} value={t}>
                              {t}
                            </MenuItem>
                          ))}
                        </TextField>
                      </Grid>
                      <Grid size={12}>
                        <TextField label="Message" value={form.message} onChange={set("message")} required fullWidth multiline minRows={5} />
                      </Grid>
                    </Grid>
                    <Alert severity="info" sx={{ mt: 2.5, borderRadius: 2 }}>
                      Please don’t include card numbers or other sensitive details.
                    </Alert>
                    <Button type="submit" variant="contained" size="large" sx={{ mt: 3 }}>
                      Send message
                    </Button>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
          <Grid size={{ xs: 12, md: 5 }}>
            <Typography variant="h5" sx={{ mb: 2 }}>
              What a demo covers
            </Typography>
            <Stack spacing={1.75} sx={{ mb: 5 }}>
              {DEMO_COVERS.map((d, i) => (
                <Box key={d} sx={{ display: "flex", gap: 1.75 }}>
                  <Box
                    sx={{
                      width: 28,
                      height: 28,
                      flexShrink: 0,
                      borderRadius: "50%",
                      bgcolor: brand.navy,
                      color: brand.brassLight,
                      display: "grid",
                      placeItems: "center",
                      fontWeight: 700,
                      fontSize: 13,
                    }}
                  >
                    {i + 1}
                  </Box>
                  <Typography sx={{ color: "text.secondary", lineHeight: 1.6, pt: "2px" }}>{d}</Typography>
                </Box>
              ))}
            </Stack>
            <Box sx={{ p: 3, borderRadius: 4, bgcolor: "#fff", border: `1px solid ${brand.line}` }}>
              <Typography sx={{ fontWeight: 600, mb: 1 }}>Found a security problem?</Typography>
              <Typography sx={{ color: "text.secondary", fontSize: 15, lineHeight: 1.6 }}>
                Choose “Report a security issue” above, and please keep exploit details out of public GitHub issues.
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </Section>
    </>
  );
}
