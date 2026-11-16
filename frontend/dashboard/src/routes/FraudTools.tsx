// Fraud tools for analysts and administrators: payment history search (FR-FRD-06), the block
// list (FR-FRD-09) and the fraud rules (FR-FRD-02, FR-FRD-03). No wireframes; they reuse the
// D6 table and dialog layouts.
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, MenuItem, Paper, Stack, Switch,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ApiError, api, post, query, type BlocklistEntry, type FraudRule, type HistorySearch, type RuleConflict, type RuleSet,
} from "../api/client";
import { useStaff } from "../auth";
import { Badge, ErrorAlert, PageHeader, ScoreBar, Section, Tile } from "../components/ui";
import { longDate, money, reasonLabel, shortDate, titleCase } from "../format";

// --- block list (shared dialog) ---------------------------------------------------------------

/** Add a card or IP to the block list, from a case or payment, or an IP address typed in. */
export function BlocklistDialog({ target, onClose }: {
  target: { kind: "card" | "ip"; case_id?: string; payment_id?: string; ip?: string; label: string } | null;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const [reason, setReason] = useState("");
  const add = useMutation({
    mutationFn: () => post<BlocklistEntry>("/blocklist", {
      kind: target!.kind, case_id: target!.case_id, payment_id: target!.payment_id, ip: target!.ip, reason: reason.trim(),
    }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["blocklist"] });
      client.invalidateQueries({ queryKey: ["history-search"] });
      close();
    },
  });
  const close = () => { setReason(""); add.reset(); onClose(); };
  return (
    <Dialog open={!!target} onClose={close} fullWidth maxWidth="xs" aria-labelledby="blocklist-title">
      <DialogTitle id="blocklist-title">Blocklist {target?.label}</DialogTitle>
      <DialogContent>
        <DialogContentText mb={2}>
          Later payment attempts with this {target?.kind === "card" ? "card" : "IP address"} are blocked, and the customer
          sees the general "payment not completed" message. Earlier payments do not change. Only an administrator can
          remove the entry.
        </DialogContentText>
        <TextField label="Reason (shown to analysts and kept in the audit log)" value={reason}
          onChange={(e) => setReason(e.target.value)} fullWidth autoFocus inputProps={{ maxLength: 100 }} />
        <ErrorAlert error={add.error} />
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button variant="contained" disabled={!reason.trim() || add.isPending} onClick={() => add.mutate()}>Add to block list</Button>
      </DialogActions>
    </Dialog>
  );
}

export function Blocklist() {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const show = params.get("show") ?? "active";
  const [adding, setAdding] = useState(false);
  const [ip, setIp] = useState("");
  const [target, setTarget] = useState<{ kind: "ip"; ip: string; label: string } | null>(null);
  const [removing, setRemoving] = useState<BlocklistEntry | null>(null);
  const [reason, setReason] = useState("");
  const list = useQuery({
    queryKey: ["blocklist", show],
    queryFn: () => api<{ data: BlocklistEntry[]; can_remove: boolean }>(`/blocklist${query({ show })}`),
  });
  const remove = useMutation({
    mutationFn: () => post(`/blocklist/${removing!.id}/remove`, { reason: reason.trim() }),
    onSuccess: () => { setRemoving(null); setReason(""); client.invalidateQueries({ queryKey: ["blocklist"] }); },
  });
  return (
    <>
      <PageHeader title="Block list" subtitle="Cards and IP addresses whose payment attempts are blocked"
        action={<Button variant="outlined" onClick={() => setAdding((a) => !a)}>Add IP address</Button>} />
      {adding && (
        <Stack component="form" direction={{ xs: "column", sm: "row" }} gap={1} mb={2}
          onSubmit={(e) => { e.preventDefault(); setTarget({ kind: "ip", ip: ip.trim(), label: ip.trim() }); }}>
          <TextField size="small" label="IP address" value={ip} onChange={(e) => setIp(e.target.value)} />
          <Button type="submit" variant="contained" disabled={!ip.trim()}>Continue</Button>
          <Typography variant="caption" color="text.secondary" alignSelf="center">
            To blocklist a card, open its case or search for it.
          </Typography>
        </Stack>
      )}
      <Stack direction="row" gap={1} mb={2}>
        {["active", "removed", "all"].map((k) => (
          <Button key={k} size="small" variant={show === k ? "contained" : "outlined"} onClick={() => setParams({ show: k })}>
            {titleCase(k)}
          </Button>
        ))}
      </Stack>
      <ErrorAlert error={list.error} />
      <TableContainer component={Paper} sx={{ borderRadius: 2 }}>
        <Table aria-label="Block list">
          <TableHead>
            <TableRow><TableCell>Entry</TableCell><TableCell>Reason</TableCell><TableCell>Added</TableCell><TableCell>Status</TableCell><TableCell /></TableRow>
          </TableHead>
          <TableBody>
            {list.data?.data.map((e) => (
              <TableRow key={e.id}>
                <TableCell>{e.display}<Typography variant="caption" color="text.secondary" display="block">{titleCase(e.kind)}</Typography></TableCell>
                <TableCell>{e.reason}{e.source_case && (
                  <Typography variant="caption" display="block"><Link to={`/reviews/${e.source_case}`}>From case</Link></Typography>)}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{shortDate(e.created_at)}{e.added_by && <Typography variant="caption" color="text.secondary" display="block">{e.added_by}</Typography>}</TableCell>
                <TableCell>
                  <Badge label={e.active ? "Blocking" : "Removed"} tone={e.active ? "dark" : "neutral"} />
                  {e.removal_reason && <Typography variant="caption" display="block" mt={0.5}>{e.removal_reason}</Typography>}
                </TableCell>
                <TableCell align="right">
                  {list.data.can_remove && e.active && <Button size="small" onClick={() => setRemoving(e)}>Remove</Button>}
                </TableCell>
              </TableRow>
            ))}
            {list.data && list.data.data.length === 0 && (
              <TableRow><TableCell colSpan={5}><Typography color="text.secondary" py={2} textAlign="center">Nothing here.</Typography></TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <BlocklistDialog target={target} onClose={() => { setTarget(null); setIp(""); setAdding(false); }} />
      <Dialog open={!!removing} onClose={() => setRemoving(null)} fullWidth maxWidth="xs" aria-labelledby="remove-title">
        <DialogTitle id="remove-title">Remove {removing?.display}</DialogTitle>
        <DialogContent>
          <DialogContentText mb={2}>Payments with it are screened normally again. The entry stays in the list as removed.</DialogContentText>
          <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} fullWidth autoFocus inputProps={{ maxLength: 100 }} />
          <ErrorAlert error={remove.error} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRemoving(null)}>Cancel</Button>
          <Button variant="contained" disabled={!reason.trim() || remove.isPending} onClick={() => remove.mutate()}>Remove</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

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
  const pages = r ? Math.max(1, Math.ceil(r.count / r.page_size)) : 1;
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
          <Stack direction="row" justifyContent="flex-end" gap={1} mt={2}>
            <Button variant="outlined" disabled={page <= 1} onClick={() => setParams({ by, value, page: String(page - 1) })}>Previous</Button>
            <Button variant="outlined" disabled={page >= pages} onClick={() => setParams({ by, value, page: String(page + 1) })}>Next</Button>
          </Stack>
        </>
      )}
      <BlocklistDialog target={target} onClose={() => setTarget(null)} />
    </>
  );
}

// --- rules --------------------------------------------------------------------------------------

type Draft = { code: string; description: string; feature: string; op: string; value: string; action: "block" | "verify" };
const EMPTY: Draft = { code: "", description: "", feature: "amount_cents", op: "gt", value: "", action: "verify" };

function RuleDialog({ open, rule, set, onClose }: { open: boolean; rule: FraudRule | null; set: RuleSet; onClose: () => void }) {
  const client = useQueryClient();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [conflicts, setConflicts] = useState<RuleConflict[] | null>(null);
  const d = draft ?? (rule ? { code: rule.code, description: rule.description ?? "", feature: rule.feature, op: rule.op,
    value: String(rule.value), action: rule.action } : EMPTY);
  const body = (confirm: boolean) => ({
    rule: { code: d.code.trim(), description: d.description.trim(), feature: d.feature, op: d.op, value: Number(d.value), action: d.action },
    confirm_conflicts: confirm,
  });
  const save = useMutation({
    mutationFn: (confirm: boolean) => post<RuleSet>(rule ? `/rules/${rule.id}` : "/rules", body(confirm)),
    onSuccess: (next) => { client.setQueryData(["rules"], next); close(); },
    onError: (e) => {
      if (e instanceof ApiError && e.code === "rule_conflict") {
        setConflicts(((e.body as unknown as { conflicts?: RuleConflict[] })?.conflicts) ?? []);
      }
    },
  });
  const close = () => { setDraft(null); setConflicts(null); save.reset(); onClose(); };
  const change = (k: keyof Draft, v: string) => { setConflicts(null); setDraft({ ...d, [k]: v } as Draft); };
  const valid = /^[a-z][a-z0-9_]{2,47}$/.test(d.code.trim()) && d.value.trim() !== "" && Number.isFinite(Number(d.value));
  const conflictError = save.error instanceof ApiError && save.error.code === "rule_conflict";
  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="sm" aria-labelledby="rule-title">
      <DialogTitle id="rule-title">{rule ? `Edit ${rule.code}` : "New fraud rule"}</DialogTitle>
      <DialogContent>
        <Stack gap={2} mt={1}>
          <Stack direction={{ xs: "column", sm: "row" }} gap={1}>
            <TextField select label="Feature" value={d.feature} onChange={(e) => change("feature", e.target.value)} sx={{ flex: 2 }}>
              {set.features.map((f) => <MenuItem key={f} value={f}>{f}</MenuItem>)}
            </TextField>
            <TextField select label="Is" value={d.op} onChange={(e) => change("op", e.target.value)} sx={{ flex: 1 }}>
              {set.ops.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
            </TextField>
            <TextField label="Value" value={d.value} onChange={(e) => change("value", e.target.value)} sx={{ flex: 1 }}
              helperText={d.feature === "amount_cents" ? "In cents" : " "} />
          </Stack>
          <TextField select label="Then" value={d.action} onChange={(e) => change("action", e.target.value)}>
            <MenuItem value="verify">Ask for a verification code</MenuItem>
            <MenuItem value="block">Block the payment</MenuItem>
          </TextField>
          <TextField label="Reason code (recorded on the decision)" value={d.code} onChange={(e) => change("code", e.target.value)}
            helperText="Lower-case letters, digits and underscores, e.g. large_order" />
          <TextField label="Description (optional)" value={d.description} onChange={(e) => change("description", e.target.value)}
            inputProps={{ maxLength: 200 }} />
          {conflicts && conflicts.length > 0 && (
            <Alert severity="warning">
              <Typography variant="body2" fontWeight={600} mb={0.5}>This rule conflicts with an existing rule:</Typography>
              {conflicts.map((c) => <Typography key={c.rule_id} variant="body2">{c.message}</Typography>)}
            </Alert>
          )}
          {!conflictError && <ErrorAlert error={save.error} />}
          <Typography variant="caption" color="text.secondary">
            The rule applies to payments screened after you save. Earlier decisions keep the rule set they were made with.
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        {conflicts && conflicts.length > 0 ? (
          <Button variant="contained" color="warning" disabled={save.isPending} onClick={() => save.mutate(true)}>Save anyway</Button>
        ) : (
          <Button variant="contained" disabled={!valid || save.isPending} onClick={() => save.mutate(false)}>Save rule</Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

function History({ ruleId, onClose }: { ruleId: string | null; onClose: () => void }) {
  const history = useQuery({
    queryKey: ["rule-history", ruleId],
    queryFn: () => api<{ revisions: FraudRule[] }>(`/rules/${ruleId}`),
    enabled: !!ruleId,
  });
  return (
    <Dialog open={!!ruleId} onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="history-title">
      <DialogTitle id="history-title">Rule history</DialogTitle>
      <DialogContent>
        <Table size="small" aria-label="Rule revisions">
          <TableHead><TableRow><TableCell>Rev.</TableCell><TableCell>Condition</TableCell><TableCell>Action</TableCell><TableCell>From</TableCell><TableCell>Until</TableCell></TableRow></TableHead>
          <TableBody>
            {history.data?.revisions.map((r) => (
              <TableRow key={r.revision}>
                <TableCell>{r.revision}{!r.enabled && " (off)"}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>{r.condition}</TableCell>
                <TableCell>{titleCase(r.action)}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{r.ruleset_version}<Typography variant="caption" display="block">{shortDate(r.created_at)}</Typography></TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{r.superseded_at ? shortDate(r.superseded_at) : "current"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  );
}

export function FraudRules() {
  const staff = useStaff();
  const admin = staff.role === "administrator";
  const client = useQueryClient();
  const set = useQuery({ queryKey: ["rules"], queryFn: () => api<RuleSet>("/rules") });
  const [editing, setEditing] = useState<FraudRule | "new" | null>(null);
  const [historyOf, setHistoryOf] = useState<string | null>(null);
  const [freezeNote, setFreezeNote] = useState<string | null>(null);
  const done = (next: RuleSet) => client.setQueryData(["rules"], next);
  const toggle = useMutation({ mutationFn: (r: FraudRule) => post<RuleSet>(`/rules/${r.id}/enabled`, { enabled: !r.enabled }), onSuccess: done });
  const freeze = useMutation({ mutationFn: (note: string) => post<RuleSet>("/rules/freeze", { note }), onSuccess: (n) => { done(n); setFreezeNote(null); } });
  const unfreeze = useMutation({ mutationFn: () => post<RuleSet>("/rules/unfreeze"), onSuccess: done });
  const s = set.data;
  const locked = !admin || !!s?.frozen;
  return (
    <>
      <PageHeader title="Fraud rules" subtitle={s ? `Rule set ${s.version}. Rules run after the block list, before the model.` : undefined}
        action={admin && s && (
          <Stack direction="row" gap={1}>
            {s.frozen
              ? <Button variant="outlined" onClick={() => unfreeze.mutate()} disabled={unfreeze.isPending}>End evaluation run</Button>
              : <Button variant="outlined" onClick={() => setFreezeNote("")}>Start evaluation run</Button>}
            <Button variant="contained" disabled={!!s.frozen} onClick={() => setEditing("new")}>New rule</Button>
          </Stack>
        )} />
      <ErrorAlert error={set.error ?? toggle.error ?? freeze.error ?? unfreeze.error} />
      {s?.frozen && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Frozen since {longDate(s.frozen.since)} for an evaluation run: {s.frozen.note}. Rules cannot change until it ends.
        </Alert>
      )}
      {s && (
        <TableContainer component={Paper} sx={{ borderRadius: 2, mb: 2 }}>
          <Table aria-label="Fraud rules">
            <TableHead>
              <TableRow><TableCell>Rule</TableCell><TableCell>Condition</TableCell><TableCell>Action</TableCell><TableCell>On</TableCell><TableCell /></TableRow>
            </TableHead>
            <TableBody>
              {s.rules.map((r) => (
                <TableRow key={r.id} sx={{ opacity: r.enabled ? 1 : 0.6 }}>
                  <TableCell>{r.code}<Typography variant="caption" color="text.secondary" display="block">{r.description}</Typography></TableCell>
                  <TableCell sx={{ fontFamily: "monospace", fontSize: 13 }}>{r.condition}</TableCell>
                  <TableCell><Badge label={r.action === "block" ? "Block" : "Verify"} tone={r.action === "block" ? "dark" : "neutral"} /></TableCell>
                  <TableCell>
                    <Switch checked={r.enabled} disabled={locked || toggle.isPending} onChange={() => toggle.mutate(r)}
                      inputProps={{ "aria-label": `${r.enabled ? "Switch off" : "Switch on"} ${r.code}` }} />
                  </TableCell>
                  <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                    <Button size="small" onClick={() => setHistoryOf(r.id)}>History</Button>
                    {!locked && <Button size="small" onClick={() => setEditing(r)}>Edit</Button>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      {s && (
        <Section title="Always applied">
          <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
            {s.fixed.map((f) => <Typography component="li" variant="body2" key={f}>{f}</Typography>)}
          </Box>
        </Section>
      )}
      {s && <RuleDialog open={!!editing} rule={editing === "new" ? null : editing} set={s} onClose={() => setEditing(null)} />}
      <History ruleId={historyOf} onClose={() => setHistoryOf(null)} />
      <Dialog open={freezeNote !== null} onClose={() => setFreezeNote(null)} fullWidth maxWidth="xs" aria-labelledby="freeze-title">
        <DialogTitle id="freeze-title">Start an evaluation run</DialogTitle>
        <DialogContent>
          <DialogContentText mb={2}>The rules are frozen until you end the run, so its results match one rule set.</DialogContentText>
          <TextField label="Which run" value={freezeNote ?? ""} onChange={(e) => setFreezeNote(e.target.value)} fullWidth autoFocus inputProps={{ maxLength: 200 }} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFreezeNote(null)}>Cancel</Button>
          <Button variant="contained" disabled={!freezeNote?.trim() || freeze.isPending} onClick={() => freeze.mutate(freezeNote!.trim())}>Freeze rules</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
