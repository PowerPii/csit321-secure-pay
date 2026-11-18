// Overview (demo-day polish): today at a glance, 14 days of payments, the screening mix and
// the latest payments. Same scope as the payments list: operators see their merchant.
import {
  Box, Link as MuiLink, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type PaymentRow } from "../api/client";
import { useStaff } from "../auth";
import { Badge, ErrorAlert, PageHeader, Section, Tile, RowAction, visuallyHidden } from "../components/ui";
import { money, riskLabel, shortDate, statusLabel, statusTone } from "../format";

export interface Overview {
  today: {
    payments: number; approved: number; declined: number; blocked: number;
    verification_asked: number; approved_volume: number; approval_rate: number | null;
  };
  daily: { date: string; approved: number; declined: number; blocked: number; volume: number }[];
  screening_7d: { allow: number; verify: number; block: number; not_screened: number };
  recent: PaymentRow[];
}

const COLOURS = { approved: "#1F9D63", declined: "#8792A8", blocked: "#D9434B" } as const;
const MIX = [
  { key: "allow", label: "Allowed", colour: "#1F9D63" },
  { key: "verify", label: "Verification code", colour: "#D98A0B" },
  { key: "block", label: "Blocked", colour: "#D9434B" },
  { key: "not_screened", label: "Not screened", colour: "#8792A8" },
] as const;

function DailyChart({ daily }: { daily: Overview["daily"] }) {
  const W = 640, H = 200, pad = { l: 28, r: 8, t: 10, b: 26 };
  const max = Math.max(1, ...daily.map((d) => d.approved + d.declined + d.blocked));
  const step = (W - pad.l - pad.r) / daily.length;
  const bar = Math.min(28, step * 0.62);
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, Math.ceil(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);
  const label = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-SG", { day: "numeric", month: "short" });
  return (
    <Box component="svg" viewBox={`0 0 ${W} ${H}`} role="img" sx={{ width: "100%", height: "auto", display: "block" }}
      aria-label="Payments per day for the last 14 days, split into approved, declined and blocked">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="#E6E1D8" />
          <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize="11" fill="#5B6475">{t}</text>
        </g>
      ))}
      {daily.map((d, i) => {
        const x = pad.l + i * step + (step - bar) / 2;
        let base = 0;
        return (
          <g key={d.date}>
            <title>{`${label(d.date)}: ${d.approved} approved, ${d.declined} declined, ${d.blocked} blocked, ${money(d.volume)}`}</title>
            {(["approved", "declined", "blocked"] as const).map((k) => {
              const v = d[k];
              if (!v) return null;
              const top = y(base + v), bottom = y(base);
              base += v;
              return <rect key={k} x={x} y={top} width={bar} height={Math.max(0, bottom - top - 1)} rx="2" fill={COLOURS[k]} />;
            })}
            {(daily.length - 1 - i) % 2 === 0 && (
              <text x={x + bar / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="#5B6475">{label(d.date)}</text>
            )}
          </g>
        );
      })}
    </Box>
  );
}

/** The chart's numbers as a table for screen-reader users (the chart itself is one image). */
function DailyTable({ daily }: { daily: Overview["daily"] }) {
  const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-SG", { day: "numeric", month: "short" });
  return (
    // In a hidden div: a table ignores width: 1px and would widen the page on phones.
    <Box sx={visuallyHidden}>
    <table>
      <caption>Payments per day, last 14 days</caption>
      <thead><tr><th scope="col">Day</th><th scope="col">Approved</th><th scope="col">Declined</th><th scope="col">Blocked</th><th scope="col">Volume</th></tr></thead>
      <tbody>
        {daily.map((d) => (
          <tr key={d.date}><th scope="row">{day(d.date)}</th><td>{d.approved}</td><td>{d.declined}</td><td>{d.blocked}</td><td>{money(d.volume)}</td></tr>
        ))}
      </tbody>
    </table>
    </Box>
  );
}

function Legend({ items }: { items: { label: string; colour: string; value?: number }[] }) {
  return (
    <Stack direction="row" flexWrap="wrap" gap={2} mt={1}>
      {items.map((it) => (
        <Stack key={it.label} direction="row" alignItems="center" gap={0.8}>
          <Box aria-hidden="true" sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: it.colour }} />
          <Typography variant="body2" color="text.secondary">
            {it.label}{it.value !== undefined && <> · <strong>{it.value}</strong></>}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}

function ScreeningMix({ mix }: { mix: Overview["screening_7d"] }) {
  const total = MIX.reduce((s, m) => s + mix[m.key], 0);
  return (
    <>
      <Box sx={{ display: "flex", height: 14, borderRadius: 7, overflow: "hidden", bgcolor: "#EEEAE2", mt: 1 }}
        role="img" aria-label={MIX.map((m) => `${m.label} ${mix[m.key]}`).join(", ")}>
        {total > 0 && MIX.map((m) => mix[m.key] > 0 && (
          <Box key={m.key} sx={{ width: `${(100 * mix[m.key]) / total}%`, bgcolor: m.colour }} />
        ))}
      </Box>
      <Legend items={MIX.map((m) => ({ label: m.label, colour: m.colour, value: mix[m.key] }))} />
      <Typography variant="body2" color="text.secondary" mt={1.5}>
        {total === 0 ? "No payments screened in the last 7 days."
          : `${total} payment${total === 1 ? "" : "s"} screened in the last 7 days.`}
      </Typography>
    </>
  );
}

export default function OverviewPage() {
  const staff = useStaff();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["overview"], queryFn: () => api<Overview>("/overview"), refetchInterval: 15_000 });
  const d = q.data;
  const allMerchants = staff.merchant === null;
  return (
    <>
      <PageHeader title="Overview" subtitle={allMerchants ? "All merchants, Singapore time" : `${staff.merchant?.name ?? "Your shop"}, Singapore time`} />
      <ErrorAlert error={q.error} />
      {d && (
        <Stack gap={2.5}>
          <Stack direction="row" flexWrap="wrap" gap={2}>
            <Tile label="Payments today" value={d.today.payments} />
            <Tile label="Approval rate" value={d.today.approval_rate === null ? "–" : `${Math.round(d.today.approval_rate * 100)}%`} />
            <Tile label="Approved today" value={money(d.today.approved_volume)} />
            <Tile label="Asked for a code" value={d.today.verification_asked} />
            <Tile label="Blocked today" value={d.today.blocked} />
          </Stack>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", lg: "2fr 1fr" }, gap: 2.5 }}>
            <Section title="Last 14 days">
              <DailyChart daily={d.daily} />
              <DailyTable daily={d.daily} />
              <Legend items={[
                { label: "Approved", colour: COLOURS.approved },
                { label: "Declined by the bank", colour: COLOURS.declined },
                { label: "Blocked by screening", colour: COLOURS.blocked },
              ]} />
            </Section>
            <Section title="Fraud screening">
              <ScreeningMix mix={d.screening_7d} />
            </Section>
          </Box>
          <Section title="Latest payments" action={<MuiLink component={Link} to="/payments" variant="body2">See all</MuiLink>}>
            {d.recent.length === 0 ? (
              <Typography color="text.secondary" variant="body2">No payments yet.</Typography>
            ) : (
              <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}>
                <Table size="small" aria-label="Latest payments">
                  <TableHead>
                    <TableRow>
                      <TableCell>Reference</TableCell>
                      <TableCell>Created</TableCell>
                      {allMerchants && <TableCell>Merchant</TableCell>}
                      <TableCell align="right">Amount</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Risk decision</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {d.recent.map((p) => (
                      <TableRow key={p.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/payments/${p.id}`)}>
                        <TableCell><RowAction onClick={() => navigate(`/payments/${p.id}`)}>{p.reference}</RowAction></TableCell>
                        <TableCell sx={{ whiteSpace: "nowrap" }}>{shortDate(p.created_at)}</TableCell>
                        {allMerchants && <TableCell>{p.merchant.name}</TableCell>}
                        <TableCell align="right">{money(p.amount)}</TableCell>
                        <TableCell><Badge label={statusLabel(p.status, p.amount, p.refunded_amount)} tone={statusTone(p.status)} /></TableCell>
                        <TableCell>{riskLabel(p.risk)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Section>
        </Stack>
      )}
    </>
  );
}
