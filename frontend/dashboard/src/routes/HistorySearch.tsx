// Search screened attempts by card, email or IP (FR-FRD-06).
import {
  Alert, Button, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  TextField, Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, query, type HistorySearch } from "../api/client";
import { BlocklistDialog } from "../components/BlocklistDialog";
import { Pagination } from "../components/Pagination";
import { Badge, ErrorAlert, PageHeader, ScoreBar, Tile } from "../components/ui";
import { money, reasonLabel, shortDate, titleCase } from "../format";

// --- search -------------------------------------------------------------------------------------

const BY_LABEL = { card: "Card", email: "Email address", ip: "IP address" } as const;
const HINT = {
  card: "Card fingerprint, or a payment ID or reference",
  email: "Email address",
  ip: "IP address, or a payment ID or reference",
} as const;

export function HistorySearchPage() {
  const [params, setParams] = useSearchParams();
  const by = (params.get("by") ?? "email") as keyof typeof BY_LABEL;
  const value = params.get("value") ?? "";
  const page = Number(params.get("page") ?? "1") || 1;
  const [draftBy, setDraftBy] = useState<keyof typeof BY_LABEL>(by);
  const [draft, setDraft] = useState(value);
  const [target, setTarget] = useState<{ kind: "card" | "ip"; payment_id?: string; ip?: string; label: string } | null>(null);
  const search = useQuery({
    queryKey: ["history-search", by, value, page],
    queryFn: () => api<HistorySearch>(`/fraud/search${query({ by, value, page })}`),
    enabled: !!value,
  });
  const submit = (e: FormEvent) => { e.preventDefault(); if (draft.trim()) setParams({ by: draftBy, value: draft.trim() }); };
  const r = search.data;
  const blockTarget = () => {
    if (!r || r.by === "email") return null;
    if (r.by === "ip" && !/^(pay_|SP-)/i.test(value)) return { kind: "ip" as const, ip: value, label: r.searched };
    const first = r.data[0];
    return first ? { kind: r.by, payment_id: first.payment.id, label: r.searched } : null;
  };
  return (
    <>
      <PageHeader title="Search payment history" subtitle="Every screened attempt that shares a card, email address or IP address. Each search is logged." />
      <Stack component="form" direction={{ xs: "column", sm: "row" }} gap={1} mb={2} onSubmit={submit}>
        <TextField select size="small" label="Search by" value={draftBy} onChange={(e) => setDraftBy(e.target.value as keyof typeof BY_LABEL)} sx={{ minWidth: 160 }}>
          {Object.entries(BY_LABEL).map(([k, l]) => <MenuItem key={k} value={k}>{l}</MenuItem>)}
        </TextField>
        <TextField size="small" label={HINT[draftBy]} value={draft} onChange={(e) => setDraft(e.target.value)} sx={{ minWidth: 320 }} />
        <Button type="submit" variant="contained">Search</Button>
      </Stack>
      <ErrorAlert error={search.error} />
      {r && (
        <>
          <Stack direction={{ xs: "column", sm: "row" }} gap={2} mb={2}>
            <Tile label={`Attempts · ${r.searched}`} value={r.summary.attempts} />
            <Tile label="Merchants" value={r.summary.merchants} />
            <Tile label="Flagged" value={r.summary.flagged} />
            <Tile label="Blocked" value={r.summary.blocked} />
          </Stack>
          {r.blocklisted ? (
            <Alert severity="info" sx={{ mb: 2 }}>On the block list since {shortDate(r.blocklisted.created_at)}: {r.blocklisted.reason}</Alert>
          ) : blockTarget() && (
            <Button variant="outlined" sx={{ mb: 2 }} onClick={() => setTarget(blockTarget())}>
              Blocklist this {r.by === "card" ? "card" : "IP address"}
            </Button>
          )}
          <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
            <Table aria-label="Search results">
              <TableHead>
                <TableRow><TableCell>When</TableCell><TableCell>Payment</TableCell><TableCell>Merchant</TableCell><TableCell align="right">Amount</TableCell><TableCell>Score</TableCell><TableCell>Outcome</TableCell><TableCell>Reasons</TableCell></TableRow>
              </TableHead>
              <TableBody>
                {r.data.map((a) => (
                  <TableRow key={a.payment.id}>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{shortDate(a.occurred_at)}</TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>
                      <Link to={a.case_id ? `/reviews/${a.case_id}` : `/payments/${a.payment.id}`}>{a.payment.reference}</Link>
                      {a.card && <Typography variant="caption" color="text.secondary" display="block">{a.card}</Typography>}
                    </TableCell>
                    <TableCell>{a.merchant.name}</TableCell>
                    <TableCell align="right">{money(a.amount)}</TableCell>
                    <TableCell><ScoreBar score={a.score} /></TableCell>
                    <TableCell><Badge label={titleCase(a.outcome.replace("_", " "))} tone={a.outcome === "block" ? "dark" : "neutral"} /></TableCell>
                    <TableCell>{a.reasons.map(reasonLabel).join(", ")}</TableCell>
                  </TableRow>
                ))}
                {r.data.length === 0 && (
                  <TableRow><TableCell colSpan={7}><Typography color="text.secondary" py={2} textAlign="center">No screened attempts match.</Typography></TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <Pagination page={page} data={r} onChange={(next) => setParams({ by, value, page: String(next) })} />
        </>
      )}
      <BlocklistDialog target={target} onClose={() => setTarget(null)} />
    </>
  );
}
