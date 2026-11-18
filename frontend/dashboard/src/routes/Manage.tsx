// Administrator account management and limits (FR-ADM-02 to FR-ADM-05, FR-ADM-07, FR-ADM-12;
// UC-33, UC-34, UC-36, UC-43). No wireframe: reuses the Merchants table and dialogs.
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, MenuItem, Paper, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, post, query, type Limits, type Merchant, type Role, type StaffList, type StaffRow } from "../api/client";
import { useStaff } from "../auth";
import { Badge, ErrorAlert, PageHeader, Section, SrOnly } from "../components/ui";
import { longDate, money, parseMoney, titleCase } from "../format";

export const REASONS = [
  "Suspected misuse", "Security incident", "Left the organisation", "Requested by the account holder", "Investigation closed",
];

export type StatusAction = "suspend" | "deactivate" | "reinstate";
const ACTION_LABEL: Record<StatusAction, string> = { suspend: "Suspend", deactivate: "Deactivate", reinstate: "Reinstate" };

/** Suspend, deactivate or reinstate a staff account or a merchant: reason, then confirm (UC-33). */
export function StatusDialog({ target, onClose, onDone }: {
  target: { kind: "staff" | "merchant"; id: string; name: string; action: StatusAction } | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState(REASONS[0]);
  const [note, setNote] = useState("");
  const change = useMutation({
    mutationFn: () => post(`/${target!.kind === "staff" ? "staff" : "merchants"}/${target!.id}/status`, {
      action: target!.action, reason: note.trim() ? `${reason}: ${note.trim()}`.slice(0, 200) : reason, confirm: true,
    }),
    onSuccess: () => { setNote(""); onDone(); },
  });
  const close = () => { setNote(""); change.reset(); onClose(); };
  if (!target) return null;
  const effect = target.action === "reinstate"
    ? "The account can sign in and use the API again."
    : target.kind === "merchant"
      ? `Its API keys stop working and its operators are signed out.${target.action === "deactivate" ? " The keys are revoked and this cannot be undone." : ""} Payments and audit history are kept.`
      : `The account is signed out and cannot sign in.${target.action === "deactivate" ? " This cannot be undone." : ""} Its history is kept.`;
  return (
    <Dialog open onClose={close} fullWidth maxWidth="xs" aria-labelledby="status-title">
      <DialogTitle id="status-title">{ACTION_LABEL[target.action]} {target.name}</DialogTitle>
      <DialogContent>
        <DialogContentText mb={2}>{effect}</DialogContentText>
        <Stack gap={2}>
          <TextField select label="Reason" value={reason} onChange={(e) => setReason(e.target.value)}>
            {REASONS.map((r) => <MenuItem key={r} value={r}>{r}</MenuItem>)}
          </TextField>
          <TextField label="Note (optional, kept in the audit log)" value={note} onChange={(e) => setNote(e.target.value)}
            inputProps={{ maxLength: 150 }} />
        </Stack>
        <ErrorAlert error={change.error} />
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button variant="contained" disabled={change.isPending} onClick={() => change.mutate()}>
          Confirm {ACTION_LABEL[target.action].toLowerCase()}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function RoleDialog({ account, roles, onClose }: { account: StaffRow | null; roles: StaffList["roles"]; onClose: () => void }) {
  const client = useQueryClient();
  const [role, setRole] = useState<Role | "">("");
  const [merchant, setMerchant] = useState("");
  const merchants = useQuery({ queryKey: ["merchants"], queryFn: () => api<{ data: Merchant[] }>("/merchants"), enabled: !!account });
  const save = useMutation({
    mutationFn: () => post<StaffRow>(`/staff/${account!.id}/role`, {
      role: role || account!.role, merchant_id: (role || account!.role) === "merchant_operator" ? merchant || account!.merchant?.id : undefined,
    }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["staff"] }); close(); },
  });
  const close = () => { setRole(""); setMerchant(""); save.reset(); onClose(); };
  if (!account) return null;
  const chosen = role || account.role;
  return (
    <Dialog open onClose={close} fullWidth maxWidth="xs" aria-labelledby="role-title">
      <DialogTitle id="role-title">Role of {account.name}</DialogTitle>
      <DialogContent>
        <DialogContentText mb={2}>Now: {account.role_label}{account.merchant ? ` of ${account.merchant.name}` : ""}. A change applies from the account's next request.</DialogContentText>
        <Stack gap={2}>
          <TextField select label="Role" value={chosen} onChange={(e) => setRole(e.target.value as Role)}>
            {roles.map((r) => <MenuItem key={r.value} value={r.value}>{r.label}</MenuItem>)}
          </TextField>
          {chosen === "merchant_operator" && (
            <TextField select label="Merchant" value={merchant || account.merchant?.id || ""} onChange={(e) => setMerchant(e.target.value)}>
              {merchants.data?.data.map((m) => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
            </TextField>
          )}
        </Stack>
        <ErrorAlert error={save.error} />
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button variant="contained" disabled={save.isPending} onClick={() => save.mutate()}>Save role</Button>
      </DialogActions>
    </Dialog>
  );
}

export function Accounts() {
  const me = useStaff();
  const client = useQueryClient();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<{ kind: "staff"; id: string; name: string; action: StatusAction } | null>(null);
  const [roleOf, setRoleOf] = useState<StaffRow | null>(null);
  const list = useQuery({
    queryKey: ["staff", search],
    queryFn: () => api<StaffList>(`/staff${query({ q: search })}`),
    placeholderData: keepPreviousData,
  });
  const rows = list.data?.data ?? [];
  return (
    <>
      <PageHeader title="Accounts" subtitle="Suspend or deactivate staff accounts and assign roles" />
      <Stack component="form" direction="row" gap={1} mb={2} onSubmit={(e) => { e.preventDefault(); setSearch(q.trim()); }}>
        <TextField size="small" label="Search by name or email" value={q} onChange={(e) => setQ(e.target.value)} sx={{ width: 320 }} />
        <Button type="submit" variant="outlined">Search</Button>
      </Stack>
      <ErrorAlert error={list.error} />
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        <Table aria-label="Staff accounts">
          <TableHead>
            <TableRow><TableCell>Account</TableCell><TableCell>Role</TableCell><TableCell>Status</TableCell><TableCell>Last sign-in</TableCell><TableCell><SrOnly>Actions</SrOnly></TableCell></TableRow>
          </TableHead>
          <TableBody>
            {rows.map((a) => (
              <TableRow key={a.id}>
                <TableCell>
                  {a.name}<Typography variant="caption" color="text.secondary" display="block">{a.email}</Typography>
                </TableCell>
                <TableCell>{a.role_label}{a.merchant && <Typography variant="caption" color="text.secondary" display="block">{a.merchant.name}</Typography>}</TableCell>
                <TableCell>
                  <Badge label={titleCase(a.status)} tone={a.status === "active" ? "dark" : "neutral"} />
                  {a.status_reason && <Typography variant="caption" display="block" mt={0.5}>{a.status_reason}</Typography>}
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{a.last_sign_in_at ? longDate(a.last_sign_in_at) : "Never"}</TableCell>
                <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                  {a.status !== "deactivated" && <Button size="small" onClick={() => setRoleOf(a)}>Role</Button>}
                  {a.id !== me.id && a.status === "active" && (
                    <Button size="small" onClick={() => setStatus({ kind: "staff", id: a.id, name: a.name, action: "suspend" })}>Suspend</Button>
                  )}
                  {a.id !== me.id && a.status === "suspended" && (
                    <Button size="small" onClick={() => setStatus({ kind: "staff", id: a.id, name: a.name, action: "reinstate" })}>Reinstate</Button>
                  )}
                  {a.id !== me.id && a.status !== "deactivated" && (
                    <Button size="small" color="error" onClick={() => setStatus({ kind: "staff", id: a.id, name: a.name, action: "deactivate" })}>Deactivate</Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {list.data && rows.length === 0 && (
              <TableRow><TableCell colSpan={5}><Typography color="text.secondary" py={2} textAlign="center">No accounts match.</Typography></TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <StatusDialog target={status} onClose={() => setStatus(null)}
        onDone={() => { setStatus(null); client.invalidateQueries({ queryKey: ["staff"] }); }} />
      <RoleDialog account={roleOf} roles={list.data?.roles ?? []} onClose={() => setRoleOf(null)} />
    </>
  );
}

export function LimitsPage() {
  const client = useQueryClient();
  const limits = useQuery({ queryKey: ["limits"], queryFn: () => api<Limits>("/limits") });
  const [form, setForm] = useState<{ amount: string; key: string; ip: string } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [saved, setSaved] = useState(false);
  const l = limits.data;
  const values = form ?? (l ? {
    amount: (l.effective.max_amount_cents / 100).toFixed(2),
    key: String(l.effective.api_key_requests_per_minute),
    ip: String(l.effective.ip_requests_per_minute),
  } : null);
  const amount = values ? parseMoney(values.amount) : null;
  const save = useMutation({
    mutationFn: () => post<Limits>("/limits", {
      max_amount_cents: amount, api_key_requests_per_minute: Number(values!.key), ip_requests_per_minute: Number(values!.ip),
    }),
    onSuccess: (next) => { client.setQueryData(["limits"], next); setForm(null); setConfirming(false); setSaved(true); },
    onError: () => setConfirming(false),
  });
  const set = (k: "amount" | "key" | "ip", v: string) => { setSaved(false); setForm({ ...values!, [k]: v }); };
  const whole = (v: string) => /^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= 10000;
  const valid = !!values && amount !== null && whole(values.key) && whole(values.ip)
    && !!l && amount >= l.bounds.max_amount_cents[0] && amount <= l.bounds.max_amount_cents[1];
  return (
    <>
      <PageHeader title="Limits" subtitle="Maximum amount per payment and request rate limits for the merchant API" />
      <ErrorAlert error={limits.error ?? save.error} />
      {saved && <Alert severity="success" sx={{ mb: 2 }}>Saved. New requests use the new limits within a few seconds.</Alert>}
      {l && values && (
        <Section title="Current limits">
          <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "repeat(3, 1fr)" }, mb: 2 }}>
            <TextField label="Maximum per payment (SGD)" value={values.amount} onChange={(e) => set("amount", e.target.value)}
              helperText={`Up to ${money(l.bounds.max_amount_cents[1])}. Above it: "amount exceeds limit", before screening.`} />
            <TextField label="Requests a minute per API key" value={values.key} onChange={(e) => set("key", e.target.value)}
              helperText={`Default ${l.defaults.api_key_requests_per_minute}`} />
            <TextField label="Requests a minute per IP address" value={values.ip} onChange={(e) => set("ip", e.target.value)}
              helperText={`Default ${l.defaults.ip_requests_per_minute}`} />
          </Box>
          <Stack direction="row" alignItems="center" gap={2}>
            <Button variant="contained" disabled={!form || !valid} onClick={() => setConfirming(true)}>Save limits</Button>
            {form && <Button onClick={() => setForm(null)}>Cancel</Button>}
            <Typography variant="caption" color="text.secondary">
              {l.updated_at ? `Last changed ${longDate(l.updated_at)} by ${l.updated_by}.` : "Using the defaults."} Every change is in the audit log.
            </Typography>
          </Stack>
        </Section>
      )}
      <Dialog open={confirming} onClose={() => setConfirming(false)} aria-labelledby="limits-title">
        <DialogTitle id="limits-title">Change the limits?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Payments above {amount !== null ? money(amount) : "–"} will be refused. Clients sending more than {values?.key} requests a minute
            per key or {values?.ip} per IP address get "too many requests". Payments already in progress are not affected.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirming(false)}>Cancel</Button>
          <Button variant="contained" disabled={save.isPending} onClick={() => save.mutate()}>Confirm</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
