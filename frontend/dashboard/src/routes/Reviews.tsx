// D6 Fraud review queue (highest score first, side panel with the case on wide screens)
// and D6b Case detail (linked activity, record a finding). Analysts and administrators.
import {
  Alert, Box, Breadcrumbs, Button, Chip, Link as MuiLink, MenuItem, Paper, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, TextField, Typography, useMediaQuery, useTheme,
} from "@mui/material";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, post, query, type CaseDetail as Detail, type CaseList, type LinkCount } from "../api/client";
import { useStaff } from "../auth";
import { Badge, ErrorAlert, PageHeader, Row, ScoreBar } from "../components/ui";
import {
  CASE_DECISION_LABELS, cardLabel, FINDING_LABELS, longDate, money, reasonLabel, shortDate, STATUS_LABELS,
} from "../format";
import { FraudDecision } from "./FraudDecision";
import { BlocklistDialog } from "./FraudTools";

const TABS = [
  { key: "open", label: "Open" },
  { key: "mine", label: "Assigned to me" },
  { key: "closed", label: "Closed" },
] as const;

export function ReviewQueue() {
  const theme = useTheme();
  const wide = useMediaQuery(theme.breakpoints.up("lg"));
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const get = (k: string, d = "") => params.get(k) ?? d;
  const filters = {
    tab: get("tab", "open"), decision: get("decision"), min_score: get("min_score"), from: get("from"),
    to: get("to"), sort: get("sort", "score_desc"), page: get("page", "1"),
  };
  const selected = get("case");
  const list = useQuery({
    queryKey: ["reviews", filters],
    queryFn: () => api<CaseList>(`/reviews${query(filters)}`),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  });
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page" && key !== "case") next.delete("page");
    setParams(next);
  };
  const open = (id: string) => (wide ? set("case", id) : navigate(`/reviews/${id}`));
  const data = list.data;
  const pages = data ? Math.max(1, Math.ceil(data.count / data.page_size)) : 1;

  return (
    <>
      <PageHeader title="Fraud review queue" subtitle="Flagged payments across all merchants, highest score first" />
      <Stack direction="row" gap={1} mb={2} flexWrap="wrap">
        {TABS.map((t) => (
          <Chip key={t.key} clickable onClick={() => set("tab", t.key)}
            label={`${t.label}${data ? ` (${data.counts[t.key]})` : ""}`}
            sx={{ fontWeight: 600, bgcolor: filters.tab === t.key ? "#333" : "#e6e6e6",
              color: filters.tab === t.key ? "#fff" : "#333", border: "1px solid #8a8a8a" }} />
        ))}
      </Stack>
      <Box sx={{ display: "grid", gap: 2, mb: 2, gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(5, 1fr)" } }}>
        <TextField select label="Decision" value={filters.decision} onChange={(e) => set("decision", e.target.value)}>
          <MenuItem value="">All flagged</MenuItem>
          <MenuItem value="blocked,verify_failed">Blocked + Verify failed</MenuItem>
          <MenuItem value="blocked">Blocked</MenuItem>
          <MenuItem value="verify_failed">Verify failed</MenuItem>
          <MenuItem value="verify_passed">Verify passed</MenuItem>
          <MenuItem value="verify_pending">Verify pending</MenuItem>
        </TextField>
        <TextField select label="Score" value={filters.min_score} onChange={(e) => set("min_score", e.target.value)}>
          <MenuItem value="">Any score</MenuItem>
          {["0.5", "0.7", "0.9"].map((v) => <MenuItem key={v} value={v}>≥ {v}</MenuItem>)}
        </TextField>
        <TextField label="From" type="date" value={filters.from} onChange={(e) => set("from", e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField label="To" type="date" value={filters.to} onChange={(e) => set("to", e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField select label="Sort" value={filters.sort} onChange={(e) => set("sort", e.target.value)}>
          <MenuItem value="score_desc">Highest score first</MenuItem>
          <MenuItem value="score_asc">Lowest score first</MenuItem>
          <MenuItem value="newest">Newest first</MenuItem>
        </TextField>
      </Box>
      <ErrorAlert error={list.error} />
      <Box sx={{ display: "grid", gap: 2.5, alignItems: "start",
        gridTemplateColumns: { xs: "1fr", lg: selected ? "minmax(0, 1.5fr) minmax(0, 1fr)" : "1fr" } }}>
        <Box minWidth={0}>
          <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
            <Table aria-label="Flagged payments">
              <TableHead>
                <TableRow>
                  <TableCell>Score</TableCell><TableCell>Payment</TableCell><TableCell>Merchant</TableCell>
                  <TableCell align="right">Amount</TableCell><TableCell>Decision</TableCell><TableCell>Top reason</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data?.data.map((c) => (
                  <TableRow key={c.id} hover selected={c.id === selected} sx={{ cursor: "pointer" }} onClick={() => open(c.id)}>
                    <TableCell><ScoreBar score={c.score} /></TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>
                      {c.payment.reference}
                      <Typography variant="caption" color="text.secondary" display="block">{shortDate(c.occurred_at)}</Typography>
                    </TableCell>
                    <TableCell>{c.merchant.name}</TableCell>
                    <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>{money(c.payment.amount)}</TableCell>
                    <TableCell><Badge label={CASE_DECISION_LABELS[c.decision] ?? c.decision} tone={c.decision === "blocked" ? "dark" : "neutral"} /></TableCell>
                    <TableCell>{c.reasons[0] ? reasonLabel(c.reasons[0]) : ""}</TableCell>
                  </TableRow>
                ))}
                {data && data.data.length === 0 && (
                  <TableRow><TableCell colSpan={6}><Typography color="text.secondary" py={2} textAlign="center">No cases here.</Typography></TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <Stack direction="row" justifyContent="flex-end" gap={1} mt={2}>
            <Button variant="outlined" disabled={Number(filters.page) <= 1} onClick={() => set("page", String(Number(filters.page) - 1))}>Previous</Button>
            <Button variant="outlined" disabled={Number(filters.page) >= pages} onClick={() => set("page", String(Number(filters.page) + 1))}>Next</Button>
          </Stack>
        </Box>
        {selected && wide && (
          <Paper sx={{ p: 2.5, borderRadius: 2, position: "sticky", top: 16 }}>
            <CasePanel caseId={selected} compact onClose={() => set("case", "")} />
          </Paper>
        )}
      </Box>
    </>
  );
}

function linkLine(c: LinkCount | null, unit: string): string {
  if (!c) return "not available";
  if (!c.attempts) return "no other attempts";
  const merchants = c.merchants > 1 ? ` · ${c.merchants} merchants` : "";
  return `${c.attempts} other ${unit}${c.attempts === 1 ? "" : "s"}${merchants}${c.blocked ? ` · ${c.blocked} blocked` : ""}`;
}

function CasePanel({ caseId, compact = false, onClose }: { caseId: string; compact?: boolean; onClose?: () => void }) {
  const staff = useStaff();
  const client = useQueryClient();
  const [blocking, setBlocking] = useState<{ kind: "card" | "ip"; case_id: string; label: string } | null>(null);
  const detail = useQuery({ queryKey: ["case", caseId], queryFn: () => api<Detail>(`/reviews/${caseId}`) });
  const [finding, setFinding] = useState("");
  const [notes, setNotes] = useState("");
  useEffect(() => {
    if (detail.data) {
      setFinding(detail.data.review.finding ?? "");
      setNotes(detail.data.review.notes ?? "");
    }
  }, [detail.data]);
  const act = useMutation({
    mutationFn: (body: Record<string, string>) => post<Detail>(`/reviews/${caseId}`, body),
    onSuccess: (data) => {
      client.setQueryData(["case", caseId], data);
      client.invalidateQueries({ queryKey: ["reviews"] });
    },
  });

  if (detail.isPending) return <Typography color="text.secondary">Loading…</Typography>;
  if (detail.isError) return <ErrorAlert error={detail.error} />;
  const c = detail.data;
  const closed = c.review.status === "closed";
  const mine = c.review.assigned_to?.id === staff.id;
  const la = c.linked_activity;

  return (
    <Stack gap={1.5}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h6">Case · {c.payment.reference}</Typography>
        {onClose && <Button size="small" onClick={onClose} aria-label="Close case">Close</Button>}
      </Stack>
      <Stack direction="row" gap={1} flexWrap="wrap">
        <Badge label={`Score ${c.score === null ? "–" : c.score.toFixed(2)}`} tone="dark" />
        <Badge label={CASE_DECISION_LABELS[c.decision] ?? c.decision} />
        <Badge label={closed ? `Closed · ${FINDING_LABELS[c.review.finding ?? ""] ?? ""}` : c.review.assigned_to ? `Assigned · ${c.review.assigned_to.name}` : "Unassigned"} />
      </Stack>
      <Box>
        <Row label="Merchant" value={c.merchant.name} />
        <Row label="Amount" value={money(c.payment.amount)} />
        <Row label="Payment status" value={STATUS_LABELS[c.payment.status]} />
        {c.payment.card && <Row label="Card" value={cardLabel(c.payment.card)} />}
        <Row label="Customer" value={c.payment.customer ?? "guest"} />
        <Row label="Screened" value={longDate(c.occurred_at)} />
      </Box>
      <Stack direction="row" gap={1} flexWrap="wrap">
        <Button size="small" component={Link} to={`/payments/${c.payment.id}`} sx={{ px: 0, mr: 1 }}>Open payment</Button>
        {c.payment.card && (
          <Button size="small" variant="outlined" onClick={() => setBlocking({ kind: "card", case_id: c.id, label: cardLabel(c.payment.card!) })}>
            Blocklist card
          </Button>
        )}
        {la.ip && (
          <Button size="small" variant="outlined" onClick={() => setBlocking({ kind: "ip", case_id: c.id, label: `IP of ${c.payment.reference}` })}>
            Blocklist IP
          </Button>
        )}
      </Stack>
      <BlocklistDialog target={blocking} onClose={() => setBlocking(null)} />

      <Typography fontWeight={600}>Linked activity ({la.window_hours} h either side)</Typography>
      <Box>
        <Row label="Same card fingerprint" value={linkLine(la.card, "attempt")} />
        <Row label="Same email (hashed)" value={linkLine(la.email, "attempt")} />
        <Row label="Same IP address (hashed)" value={linkLine(la.ip, "attempt")} />
      </Box>
      {!compact && c.related.length > 0 && (
        <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
          <Table size="small" aria-label="Related attempts">
            <TableHead>
              <TableRow><TableCell>When</TableCell><TableCell>Payment</TableCell><TableCell>Merchant</TableCell><TableCell align="right">Amount</TableCell><TableCell>Outcome</TableCell><TableCell>Shared</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {c.related.map((r) => (
                <TableRow key={r.payment.id}>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{shortDate(r.occurred_at)}</TableCell>
                  <TableCell>
                    {r.case_id ? <MuiLink component={Link} to={`/reviews/${r.case_id}`}>{r.payment.reference}</MuiLink> : r.payment.reference}
                  </TableCell>
                  <TableCell>{r.merchant}</TableCell>
                  <TableCell align="right">{money(r.amount)}</TableCell>
                  <TableCell>{r.outcome}</TableCell>
                  <TableCell>{r.shared.join(", ")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      <Typography fontWeight={600} mt={1}>Record finding</Typography>
      <Stack direction="row" gap={1} flexWrap="wrap" role="radiogroup" aria-label="Finding">
        {Object.entries(FINDING_LABELS).map(([value, label]) => (
          <Chip key={value} label={label} clickable={!closed} role="radio" aria-checked={finding === value}
            onClick={() => !closed && setFinding(value)}
            sx={{ fontWeight: 600, bgcolor: finding === value ? "#333" : "#e6e6e6", color: finding === value ? "#fff" : "#333",
              border: "1px solid #8a8a8a" }} />
        ))}
      </Stack>
      <TextField label="Notes" multiline minRows={2} value={notes} onChange={(e) => setNotes(e.target.value)}
        disabled={closed} inputProps={{ maxLength: 1000 }} />
      <Typography variant="caption" color="text.secondary">
        A finding closes the case. It never changes the payment or its screening outcome.
      </Typography>
      <ErrorAlert error={act.error} />
      {closed ? (
        <>
          <Alert severity="success">
            {FINDING_LABELS[c.review.finding ?? ""]} recorded by {c.review.reviewed_by} on {longDate(c.review.reviewed_at)}.
          </Alert>
          <Button variant="outlined" onClick={() => act.mutate({ action: "reopen" })} disabled={act.isPending}>Reopen case</Button>
        </>
      ) : (
        <>
          <Button variant="contained" size="large" disabled={!finding || act.isPending}
            onClick={() => act.mutate({ action: "save", finding, notes })}>
            Save finding
          </Button>
          <Button variant="outlined" disabled={act.isPending}
            onClick={() => act.mutate({ action: mine ? "unassign" : "assign" })}>
            {mine ? "Unassign me" : "Assign to me"}
          </Button>
        </>
      )}
      {!compact && <FraudDecision screening={c.screening} badge={CASE_DECISION_LABELS[c.decision] ?? c.decision} />}
      {compact && (
        <Button component={Link} to={`/reviews/${c.id}`} size="small" sx={{ alignSelf: "flex-start", px: 0 }}>
          Full case detail
        </Button>
      )}
    </Stack>
  );
}

export function CaseDetail() {
  const { caseId = "" } = useParams();
  return (
    <>
      <Breadcrumbs sx={{ mb: 1.5, fontSize: 13 }}>
        <MuiLink component={Link} to="/reviews" color="text.secondary" underline="hover">Fraud review</MuiLink>
        <Typography fontSize={13} color="text.secondary">Case</Typography>
      </Breadcrumbs>
      <Box sx={{ maxWidth: 820 }}>
        <Paper sx={{ p: { xs: 2, sm: 3 }, borderRadius: 2 }}>
          <CasePanel caseId={caseId} />
        </Paper>
      </Box>
    </>
  );
}
