import { Box, Card, Typography } from "@mui/material";
import { brand, fonts } from "../theme";
import { StatusChip, type Tone } from "./StatusChip";

/* "What payments experienced": the user-facing reliability measures from status.json's
   `measures` (gateway/apps/status/measures.py, docs/RELIABILITY-MEASURES.md). Uptime says
   whether each part answered; these say whether payments worked. Every number is shown with
   what it is out of (its denominator), its window and the environment it came from, so a
   figure lifted off this page still says what it means. */

export interface Measures {
  environment: string;
  window: { start: string; end: string; hours: number; settle_minutes: number };
  population: string;
  checkout_time: { definition: string; count: number; p50_ms: number | null; p95_ms: number | null };
  definite_answers: {
    definition: string;
    eligible: number;
    answered: number;
    percent: number | null;
    breakdown: Record<string, number>;
    excluded: { waiting_on_customer: number; too_recent: number };
  };
  screening_unavailable: { definition: string; count: number };
  oldest_outstanding: {
    definition: string;
    operations_open: number;
    operation_age_seconds: number | null;
    webhooks_waiting: number;
    webhook_age_seconds: number | null;
  };
}

/** Below this many payments a p95 is one or two payments' worth: show the count instead. */
export const MIN_FOR_P95 = 20;
/** Reconciliation settles or escalates a card-network call within this (NFR-AVA-03). */
const OPERATION_BOUND_SECONDS = 60 * 60;

const TZ = "Asia/Singapore";
const until = new Intl.DateTimeFormat("en-SG", { timeZone: TZ, day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString("en-SG")} ${n === 1 ? one : many}`;

export function formatMs(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
}

export function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  return minutes % 60 ? `${h} h ${minutes % 60} min` : `${h} h`;
}

function Tile({ title, value, tone, chip, children, foot }: {
  title: string;
  value: string;
  tone?: Tone;
  chip?: string;
  children: React.ReactNode;
  foot: string;
}) {
  return (
    <Card sx={{ p: { xs: 2.5, md: 3 }, display: "flex", flexDirection: "column", gap: 1 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 1.5 }}>
        <Typography component="h3" sx={{ fontWeight: 600, fontSize: 16, color: brand.navy }}>{title}</Typography>
        {chip && tone && <StatusChip tone={tone}>{chip}</StatusChip>}
      </Box>
      <Typography sx={{ fontFamily: fonts.heading, fontWeight: 600, fontSize: { xs: 30, md: 34 }, lineHeight: 1.15, color: brand.navy, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </Typography>
      <Box sx={{ color: "text.secondary", fontSize: 14.5, lineHeight: 1.55 }}>{children}</Box>
      <Typography sx={{ mt: "auto", pt: 1, color: "text.secondary", fontSize: 12.5, fontFamily: fonts.mono, lineHeight: 1.5 }}>{foot}</Typography>
    </Card>
  );
}

export function StatusMeasures({ m }: { m: Measures }) {
  const span = `Last ${m.window.hours} h to ${until.format(new Date(m.window.end))} SGT`;
  const ct = m.checkout_time;
  const da = m.definite_answers;
  const su = m.screening_unavailable;
  const oo = m.oldest_outstanding;
  const b = da.breakdown;
  const enoughForP95 = ct.count >= MIN_FOR_P95 && ct.p95_ms !== null;
  const opAge = oo.operation_age_seconds;
  // The chip covers both kinds of waiting work, so old webhooks never sit under "Clear".
  const [opTone, opChip]: [Tone, string] =
    opAge !== null && opAge >= OPERATION_BOUND_SECONDS ? ["block", "Over 60 min"]
      : opAge !== null && opAge >= 40 * 60 ? ["verify", "Near 60 min"]
        : oo.webhooks_waiting ? ["verify", `${plural(oo.webhooks_waiting, "webhook")} waiting`]
          : opAge !== null ? ["neutral", "Within 60 min"]
            : ["allow", "Clear"];
  const against = da.eligible - da.answered;

  return (
    <Box component="section" aria-labelledby="measures-heading" sx={{ mt: { xs: 6, md: 8 } }}>
      <Typography id="measures-heading" variant="h2" sx={{ fontSize: { xs: 24, md: 28 }, color: brand.navy, mb: 1 }}>
        What payments experienced
      </Typography>
      <Typography sx={{ color: "text.secondary", mb: 1.5, lineHeight: 1.6 }}>
        Uptime says whether each part answered. These numbers say whether payments worked. They are counted from every payment
        on this gateway whose card was submitted in the window. All of it is simulated demo and test traffic, so read them as
        evidence that the system behaves, not as real shopper numbers.
      </Typography>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mb: 3 }}>
        <StatusChip tone="neutral">Environment: {m.environment}</StatusChip>
        <StatusChip tone="neutral">{span}</StatusChip>
      </Box>

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
        <Tile
          title="Checkout time"
          value={ct.count === 0 || ct.p50_ms === null ? "No payments" : enoughForP95 ? `${formatMs(ct.p95_ms!)} p95` : `${formatMs(ct.p50_ms)} median`}
          foot={`Out of ${plural(ct.count, "payment")} approved without a code · ${span}`}
        >
          From card submission to the bank’s approval, timed on the server.
          {ct.count > 0 && ct.p50_ms !== null && (enoughForP95
            ? ` Median ${formatMs(ct.p50_ms)}.`
            : ` Too few payments for a fair p95 (fewer than ${MIN_FOR_P95}).`)}{" "}
          Payments that needed a verification code are left out, because their time is mostly someone reading an email.
        </Tile>

        <Tile
          title="Payments with a clear answer"
          value={da.percent === null ? "No payments" : `${da.percent}%`}
          tone={da.percent === null ? undefined : against === 0 ? "allow" : "verify"}
          chip={da.percent === null ? undefined : against === 0 ? "All answered" : `${against} without`}
          foot={`Out of ${plural(da.eligible, "eligible payment")} · ${span}`}
        >
          {da.eligible > 0 ? `${da.answered} of ${da.eligible} were approved (${b.approved ?? 0}), declined by the bank (${b.declined ?? 0}) or blocked on purpose (${b.expected_block ?? 0}). ` : ""}
          A block by the fraud checks is a clear answer. Left out: {plural(da.excluded.waiting_on_customer, "payment")} still waiting for the
          customer’s code, and {plural(da.excluded.too_recent, "payment")} from the last {m.window.settle_minutes} minutes that may still be
          settling.
        </Tile>

        <Tile
          title="Screening unavailable"
          value={plural(su.count, "payment")}
          tone={su.count ? "verify" : "allow"}
          chip={su.count ? "Counted against" : "None"}
          foot={`Out of ${plural(da.eligible, "eligible payment")} · ${span}`}
        >
          Blocked because fraud screening gave no decision in time. The shopper gets a quick, tidy reply, so speed and error graphs
          look fine, but it is not a decision. It is shown on its own and counts against the clear-answer share above.
        </Tile>

        <Tile
          title="Oldest unfinished work"
          value={opAge === null ? "No calls waiting" : formatAge(opAge)}
          tone={opTone}
          chip={opChip}
          foot={`Right now: ${plural(oo.operations_open, "card-network call")}, ${plural(oo.webhooks_waiting, "webhook")} waiting`}
        >
          Age of the oldest call to the card network still waiting for a final answer. The gateway settles or escalates each one within
          60 minutes.{" "}
          {oo.webhook_age_seconds === null
            ? "No merchant webhooks are waiting."
            : `The oldest merchant webhook still to deliver is ${formatAge(oo.webhook_age_seconds)} old.`}
        </Tile>
      </Box>
    </Box>
  );
}
