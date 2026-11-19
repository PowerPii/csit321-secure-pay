import { Alert, Box, Button, Card, Link, Skeleton, Tooltip, Typography } from "@mui/material";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import { useCallback, useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import { Section } from "../components/Section";
import { StatusChip, type Tone } from "../components/StatusChip";
import { usePageTitle } from "../components/usePageTitle";
import { GATEWAY_URL } from "../content/site";
import { brand, fonts } from "../theme";

/* The public status page. Data: GET {gateway}/status.json (gateway/apps/status), which the
   server's worker builds from a check of every part every five minutes. If the server can't
   be reached at all, the page says so: that is the outage the server can't report itself. */

type State = "operational" | "outage" | "unknown";
type Overall = "operational" | "partial_outage" | "major_outage";
interface Day { date: string; uptime: number | null }
interface Component { id: string; name: string; description: string; status: State; uptime: number | null; days: Day[] }
interface Incident { component: string; title: string; started_at: string; ended_at: string | null; minutes: number }
interface StatusData {
  status: Overall;
  updated_at: string;
  notice: string;
  time_zone: string;
  check_every_minutes: number;
  history_days: number;
  incident_days: number;
  measured_since: string | null;
  components: Component[];
  incidents: Incident[];
}

const STATUS_URL = `${GATEWAY_URL}/status.json`;
const REFRESH_MS = 60_000;
const TZ = "Asia/Singapore";

const HEADLINE: Record<Overall | "unreachable", { text: string; tone: Tone }> = {
  operational: { text: "All systems operational", tone: "allow" },
  partial_outage: { text: "Some parts are down", tone: "verify" },
  major_outage: { text: "Payments are down", tone: "block" },
  unreachable: { text: "We can’t reach SecurePay", tone: "block" },
};
const CHIP: Record<State, { text: string; tone: Tone }> = {
  operational: { text: "Operational", tone: "allow" },
  outage: { text: "Down", tone: "block" },
  unknown: { text: "No recent check", tone: "neutral" },
};

const time = new Intl.DateTimeFormat("en-SG", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
const dayTime = new Intl.DateTimeFormat("en-SG", { timeZone: TZ, day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const dayOnly = new Intl.DateTimeFormat("en-SG", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" });

function barColour(uptime: number | null) {
  if (uptime === null) return brand.line;
  if (uptime >= 99.9) return brand.allow;
  if (uptime >= 99) return brand.verify;
  return brand.block;
}

function duration(minutes: number) {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

function Bars({ days, label }: { days: Day[]; label: string }) {
  // 90 days on wide screens, the last 30 on phones.
  return (
    <Box role="img" aria-label={label} sx={{ display: "flex", gap: { xs: "3px", md: "2px" }, height: 32, mt: 1.5 }}>
      {days.map((d, i) => (
        <Tooltip
          key={d.date}
          title={`${dayOnly.format(new Date(d.date))}: ${d.uptime === null ? "no data" : `${d.uptime}% up`}`}
          placement="top"
          arrow
        >
          <Box
            sx={{
              flex: 1,
              minWidth: 0,
              borderRadius: "2px",
              bgcolor: barColour(d.uptime),
              display: { xs: i < days.length - 30 ? "none" : "block", md: "block" },
            }}
          />
        </Tooltip>
      ))}
    </Box>
  );
}

function ComponentRow({ c, first, historyDays }: { c: Component; first: boolean; historyDays: number }) {
  const chip = CHIP[c.status];
  const measured = c.days.filter((d) => d.uptime !== null).length;
  return (
    <Box sx={{ px: { xs: 2.5, md: 3.5 }, py: 3, borderTop: first ? "none" : `1px solid ${brand.line}` }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography component="h3" sx={{ fontWeight: 600, fontSize: 17, color: brand.navy }}>
            {c.name}
          </Typography>
          <Typography sx={{ color: "text.secondary", fontSize: 14.5, lineHeight: 1.55, mt: 0.25 }}>{c.description}</Typography>
        </Box>
        <StatusChip tone={chip.tone}>{chip.text}</StatusChip>
      </Box>
      {c.days.length > 0 && (
        <>
          <Bars days={c.days} label={c.uptime === null ? "No uptime history yet." : `Uptime ${c.uptime}% over the measured days.`} />
          <Box sx={{ display: "flex", justifyContent: "space-between", mt: 0.75, fontSize: 12.5, color: "text.secondary", fontFamily: fonts.mono }}>
            <Box component="span" sx={{ display: { xs: "none", md: "inline" } }}>{historyDays} days ago</Box>
            <Box component="span" sx={{ display: { xs: "inline", md: "none" } }}>30 days ago</Box>
            <span>
              {c.uptime === null ? "not measured yet" : `${c.uptime}% up${measured < historyDays ? ` over ${measured} day${measured === 1 ? "" : "s"}` : ""}`}
            </span>
            <span>Today</span>
          </Box>
        </>
      )}
    </Box>
  );
}

function Incidents({ data }: { data: StatusData }) {
  const names = Object.fromEntries(data.components.map((c) => [c.id, c.name]));
  return (
    <Box sx={{ mt: { xs: 6, md: 8 } }}>
      <Typography variant="h2" sx={{ fontSize: { xs: 24, md: 28 }, color: brand.navy, mb: 1 }}>
        Incidents in the last {data.incident_days} days
      </Typography>
      <Typography sx={{ color: "text.secondary", mb: 3, lineHeight: 1.6 }}>
        Written by the checks themselves, not by hand: an incident starts at the first failed check and ends at the next one that
        passes. Times are Singapore time.
      </Typography>
      {data.incidents.length === 0 ? (
        <Card sx={{ p: 3, color: "text.secondary" }}>No incidents. Every check passed.</Card>
      ) : (
        <Card sx={{ p: 0 }}>
          {data.incidents.map((i, n) => (
            <Box key={`${i.component}-${i.started_at}`} sx={{ px: { xs: 2.5, md: 3.5 }, py: 2.5, borderTop: n ? `1px solid ${brand.line}` : "none" }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, alignItems: "flex-start" }}>
                <Typography sx={{ fontWeight: 600 }}>{i.title}</Typography>
                <StatusChip tone={i.ended_at ? "neutral" : "block"}>{i.ended_at ? "Resolved" : "Ongoing"}</StatusChip>
              </Box>
              <Typography sx={{ color: "text.secondary", fontSize: 14.5, mt: 0.5 }}>
                {names[i.component]} · {dayTime.format(new Date(i.started_at))}
                {i.ended_at ? ` to ${time.format(new Date(i.ended_at))}` : ", still going"} · {duration(i.minutes)}
              </Typography>
            </Box>
          ))}
        </Card>
      )}
    </Box>
  );
}

export default function Status() {
  usePageTitle("Status");
  const [data, setData] = useState<StatusData | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(STATUS_URL, { cache: "no-store", credentials: "omit" });
      if (!response.ok) throw new Error(String(response.status));
      setData((await response.json()) as StatusData);
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  const headline = HEADLINE[failed ? "unreachable" : data?.status ?? "operational"];

  return (
    <>
      <Box sx={{ bgcolor: brand.slate, pt: { xs: 7, md: 10 }, pb: { xs: 6, md: 8 } }}>
        <Box sx={{ maxWidth: 880, mx: "auto", px: { xs: 2, sm: 3 } }}>
          <Typography variant="overline" component="p" sx={{ color: "text.secondary", mb: 2 }}>
            System status
          </Typography>
          {data || failed ? (
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }} role="status" aria-live="polite">
              <Box component="span" aria-hidden sx={{ width: 18, height: 18, borderRadius: "50%", flex: "none", bgcolor: { allow: brand.allow, verify: brand.verify, block: brand.block, neutral: brand.muted }[headline.tone], boxShadow: `0 0 0 6px ${brand.mist}` }} />
              <Typography variant="h1" sx={{ fontSize: { xs: 32, md: 48 }, color: brand.navy }}>
                {headline.text}
              </Typography>
            </Box>
          ) : (
            <Skeleton variant="text" sx={{ fontSize: 48, maxWidth: 480 }} />
          )}
          <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 2, mt: 2.5 }}>
            <Typography sx={{ color: "text.secondary", fontSize: 16 }}>
              {data
                ? `Every part is checked every ${data.check_every_minutes} minutes. Updated ${time.format(new Date(data.updated_at))} SGT.`
                : "Checking the server…"}
            </Typography>
            <Button size="small" variant="outlined" startIcon={<RefreshRoundedIcon />} onClick={() => void load()} disabled={loading}>
              Check again
            </Button>
          </Box>
        </Box>
      </Box>

      <Section py={{ xs: 5, md: 8 }}>
        <Box sx={{ maxWidth: 880, mx: "auto" }}>
          {failed && (
            <Alert severity="error" sx={{ mb: 3 }}>
              This page couldn’t get an answer from the SecurePay server at {GATEWAY_URL.replace(/^https?:\/\//, "")}. The whole server
              may be down or restarting, or your network may be blocking it. Payments and the demo shop are probably unavailable too.
              We’ll try again every minute.
            </Alert>
          )}
          {data?.notice && (
            <Alert severity="info" sx={{ mb: 3 }}>
              {data.notice}
            </Alert>
          )}
          {data ? (
            <Card sx={{ p: 0, opacity: failed ? 0.6 : 1 }}>
              {data.components.map((c, i) => (
                <ComponentRow key={c.id} c={c} first={i === 0} historyDays={data.history_days} />
              ))}
            </Card>
          ) : !failed ? (
            <Skeleton variant="rounded" height={420} />
          ) : null}
          {failed && data && (
            <Typography sx={{ color: "text.secondary", fontSize: 14, mt: 1.5 }}>
              Showing the last answer, from {time.format(new Date(data.updated_at))} SGT.
            </Typography>
          )}

          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2.5, mt: 2.5, fontSize: 13.5, color: "text.secondary" }} aria-label="Bar colours">
            {[
              [brand.allow, "99.9% or more"],
              [brand.verify, "99% to 99.9%"],
              [brand.block, "under 99%"],
              [brand.line, "no data"],
            ].map(([colour, label]) => (
              <Box key={label} sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}>
                <Box component="span" sx={{ width: 10, height: 10, borderRadius: "2px", bgcolor: colour }} />
                {label}
              </Box>
            ))}
          </Box>

          {data && <Incidents data={data} />}

          <Box sx={{ mt: { xs: 6, md: 8 }, pt: 4, borderTop: `1px solid ${brand.line}` }}>
            <Typography variant="h2" sx={{ fontSize: { xs: 20, md: 22 }, color: brand.navy, mb: 1.5 }}>
              About this page
            </Typography>
            <Box component="ul" sx={{ color: "text.secondary", lineHeight: 1.75, pl: 2.5, m: 0 }}>
              <li>
                SecurePay is a student project running on one small cloud server in Singapore. There is no promised uptime, and the server
                may be restarted for updates or reset between demos.
              </li>
              <li>
                The checks run on that same server, so they can’t report the server itself going down. When that happens this page shows
                “We can’t reach SecurePay”, and the team also gets an alert from an outside monitor.
              </li>
              <li>
                Short gaps of a minute or two while an update is deployed aren’t counted. Longer gaps in the checks count as downtime for the
                background worker, and as “no data” for the other parts.
              </li>
              <li>
                {data?.measured_since
                  ? `History starts on ${dayOnly.format(new Date(data.measured_since.slice(0, 10)))}, when the checks were switched on.`
                  : "History starts when the checks are switched on."}{" "}
                Developers can read the same data at{" "}
                <Link href={STATUS_URL} sx={{ fontFamily: fonts.mono, fontSize: "0.92em", wordBreak: "break-all" }}>
                  {STATUS_URL.replace(/^https?:\/\//, "")}
                </Link>
                .
              </li>
              <li>
                Something wrong that this page doesn’t show? <Link component={RouterLink} to="/contact">Tell us</Link>.
              </li>
            </Box>
          </Box>
        </Box>
      </Section>
    </>
  );
}
