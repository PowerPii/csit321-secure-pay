// Configure fraud rules and evaluation freezes (FR-FRD-02, FR-FRD-03).
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, MenuItem,
  Paper, Stack, Switch, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, post, type FraudRule, type RuleConflict, type RuleSet } from "../api/client";
import { useStaff } from "../auth";
import { Badge, ErrorAlert, PageHeader, Section } from "../components/ui";
import { longDate, shortDate, titleCase } from "../format";

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
