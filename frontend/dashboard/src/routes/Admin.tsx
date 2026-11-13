// Administrator pages: merchant approval (FR-ADM-01, FR-MER-03, FR-ADM-13) and the
// read-only audit log (FR-ADM-10, FR-ADM-11).
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Stack, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, post, query, type AuditRow, type Merchant, type Page } from "../api/client";
import { Badge, ErrorAlert, PageHeader } from "../components/ui";
import { longDate, money, parseMoney, titleCase } from "../format";

function CreateMerchant({ open, onClose }: { open: boolean; onClose: () => void }) {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [webhook, setWebhook] = useState("");
  const [limit, setLimit] = useState("");
  const create = useMutation({
    mutationFn: () => post<Merchant>("/merchants", {
      name, webhook_url: webhook || undefined, max_amount_cents: limit ? parseMoney(limit) : undefined,
    }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["merchants"] }); onClose(); },
  });
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>New merchant</DialogTitle>
      <DialogContent>
        <Stack gap={2} mt={1}>
          <TextField label="Business name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          <TextField label="Webhook URL (https)" value={webhook} onChange={(e) => setWebhook(e.target.value)} />
          <TextField label="Maximum per payment (SGD, optional)" value={limit} onChange={(e) => setLimit(e.target.value)} />
          <Typography variant="caption" color="text.secondary">
            The merchant starts as pending. Approving it issues the API key and signing secret.
          </Typography>
          <ErrorAlert error={create.error} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>Create</Button>
      </DialogActions>
    </Dialog>
  );
}

function Credentials({ merchant, onClose }: { merchant: Merchant | null; onClose: () => void }) {
  return (
    <Dialog open={!!merchant?.credentials} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{merchant?.name} is approved</DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>Copy these now. They are shown once and cannot be shown again.</Alert>
        <Typography variant="body2" color="text.secondary">API key</Typography>
        <Typography sx={{ fontFamily: "monospace", wordBreak: "break-all", mb: 2 }} data-testid="api-key">
          {merchant?.credentials?.api_key}
        </Typography>
        <Typography variant="body2" color="text.secondary">Signing secret</Typography>
        <Typography sx={{ fontFamily: "monospace", wordBreak: "break-all" }} data-testid="signing-secret">
          {merchant?.credentials?.signing_secret}
        </Typography>
      </DialogContent>
      <DialogActions><Button variant="contained" onClick={onClose}>I have stored them</Button></DialogActions>
    </Dialog>
  );
}

export function Merchants() {
  const client = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [approved, setApproved] = useState<Merchant | null>(null);
  const [rejecting, setRejecting] = useState<Merchant | null>(null);
  const [reason, setReason] = useState("");
  const list = useQuery({ queryKey: ["merchants"], queryFn: () => api<{ data: Merchant[] }>("/merchants") });
  const refresh = () => client.invalidateQueries({ queryKey: ["merchants"] });
  const approve = useMutation({
    mutationFn: (id: string) => post<Merchant>(`/merchants/${id}/approve`),
    onSuccess: (m) => { setApproved(m); refresh(); },
  });
  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => post(`/merchants/${id}/reject`, { reason }),
    onSuccess: () => { setRejecting(null); setReason(""); refresh(); },
  });
  const webhook = useMutation({
    mutationFn: ({ id, ok }: { id: string; ok: boolean }) => post(`/merchants/${id}/webhook`, { approved: ok }),
    onSuccess: refresh,
  });
  return (
    <>
      <PageHeader title="Merchants" subtitle="Approve merchants and their webhook addresses"
        action={<Button variant="outlined" size="large" onClick={() => setCreating(true)}>New merchant</Button>} />
      <ErrorAlert error={list.error ?? approve.error ?? reject.error ?? webhook.error} />
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        <Table aria-label="Merchants">
          <TableHead>
            <TableRow>
              <TableCell>Merchant</TableCell><TableCell>Status</TableCell><TableCell>Webhook</TableCell>
              <TableCell>API key</TableCell><TableCell>Limit</TableCell><TableCell>Created</TableCell><TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {list.data?.data.map((m) => (
              <TableRow key={m.id}>
                <TableCell>{m.name}<Typography variant="caption" color="text.secondary" display="block">{m.id}</Typography></TableCell>
                <TableCell><Badge label={titleCase(m.status)} tone={m.status === "active" ? "dark" : "neutral"} /></TableCell>
                <TableCell sx={{ maxWidth: 260, wordBreak: "break-all" }}>
                  {m.webhook_url ?? "none"}
                  {m.webhook_url && (
                    <Stack direction="row" gap={1} alignItems="center" mt={0.5}>
                      <Badge label={m.webhook_url_approved ? "Approved" : "Not approved"} />
                      <Button size="small" onClick={() => webhook.mutate({ id: m.id, ok: !m.webhook_url_approved })}>
                        {m.webhook_url_approved ? "Withdraw" : "Approve"}
                      </Button>
                    </Stack>
                  )}
                </TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{m.api_key?.hint ?? "none"}</TableCell>
                <TableCell>{m.max_amount_cents ? money(m.max_amount_cents) : "global"}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{longDate(m.created_at)}</TableCell>
                <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                  {m.status === "pending" && (
                    <Stack direction="row" gap={1} justifyContent="flex-end">
                      <Button variant="contained" size="small" onClick={() => approve.mutate(m.id)} disabled={approve.isPending}>Approve</Button>
                      <Button variant="outlined" size="small" onClick={() => setRejecting(m)}>Reject</Button>
                    </Stack>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <CreateMerchant open={creating} onClose={() => setCreating(false)} />
      <Credentials merchant={approved} onClose={() => setApproved(null)} />
      <Dialog open={!!rejecting} onClose={() => setRejecting(null)} fullWidth maxWidth="xs">
        <DialogTitle>Reject {rejecting?.name}</DialogTitle>
        <DialogContent>
          <TextField label="Reason (kept in the audit log)" value={reason} onChange={(e) => setReason(e.target.value)}
            fullWidth autoFocus sx={{ mt: 1 }} inputProps={{ maxLength: 200 }} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejecting(null)}>Back</Button>
          <Button variant="contained" disabled={!reason.trim() || reject.isPending}
            onClick={() => rejecting && reject.mutate({ id: rejecting.id, reason: reason.trim() })}>Reject</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export function AuditLog() {
  const [params, setParams] = useSearchParams();
  const filters = Object.fromEntries(["action", "actor", "target", "merchant", "from", "to", "page"]
    .map((k) => [k, params.get(k) ?? ""]));
  const list = useQuery({
    queryKey: ["audit", filters],
    queryFn: () => api<Page<AuditRow>>(`/audit${query(filters)}`),
    placeholderData: keepPreviousData,
  });
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  };
  const page = Number(filters.page || 1);
  const pages = list.data ? Math.max(1, Math.ceil(list.data.count / list.data.page_size)) : 1;
  const text = (key: string, label: string, placeholder: string) => (
    <TextField label={label} placeholder={placeholder} defaultValue={filters[key]} key={`${key}-${filters[key]}`}
      onKeyDown={(e) => { if (e.key === "Enter") set(key, (e.target as HTMLInputElement).value.trim()); }}
      onBlur={(e) => { if (e.target.value.trim() !== filters[key]) set(key, e.target.value.trim()); }} />
  );
  return (
    <>
      <PageHeader title="Audit log" subtitle="Every sign-in and state change. Entries cannot be edited or deleted." />
      <Box sx={{ display: "grid", gap: 2, mb: 2, gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(6, 1fr)" } }}>
        {text("action", "Action starts with", "payment.")}
        {text("actor", "Actor ID", "stf_... or key_...")}
        {text("target", "Target ID", "pay_...")}
        {text("merchant", "Merchant ID", "mer_...")}
        <TextField label="From" type="date" value={filters.from} onChange={(e) => set("from", e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField label="To" type="date" value={filters.to} onChange={(e) => set("to", e.target.value)} InputLabelProps={{ shrink: true }} />
      </Box>
      <ErrorAlert error={list.error} />
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        <Table size="small" aria-label="Audit log">
          <TableHead>
            <TableRow><TableCell>Time</TableCell><TableCell>Action</TableCell><TableCell>Actor</TableCell><TableCell>Target</TableCell><TableCell>Details</TableCell></TableRow>
          </TableHead>
          <TableBody>
            {list.data?.data.map((e) => (
              <TableRow key={e.id}>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{longDate(e.at)}</TableCell>
                <TableCell>{e.action}</TableCell>
                <TableCell>{e.actor_type}{e.actor_id ? ` · ${e.actor_id}` : ""}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{e.target_id}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12, maxWidth: 360, wordBreak: "break-word" }}>
                  {Object.keys(e.details).length ? JSON.stringify(e.details) : ""}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mt={2}>
        <Typography variant="body2" color="text.secondary">{list.data ? `${list.data.count} entries` : "Loading…"}</Typography>
        <Stack direction="row" gap={1}>
          <Button variant="outlined" disabled={page <= 1} onClick={() => set("page", String(page - 1))}>Previous</Button>
          <Button variant="outlined" disabled={page >= pages} onClick={() => set("page", String(page + 1))}>Next</Button>
        </Stack>
      </Stack>
    </>
  );
}
