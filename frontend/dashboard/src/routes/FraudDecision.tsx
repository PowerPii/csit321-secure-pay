// The decision record (FR-FRD-01) as on D4: score on the policy scale, reasons, versions.
import { Box, Divider, Stack, Typography } from "@mui/material";
import type { Screening } from "../api/client";
import { Badge, Row, Section } from "../components/ui";
import { FEATURE_LABELS, featureValue, orderedFeatures, reasonLabel } from "../format";

function Scale({ score, thresholds }: { score: number | null; thresholds: Screening["thresholds"] }) {
  if (!thresholds) return null;
  const { verify, block } = thresholds;
  return (
    <Box>
      <Box sx={{ position: "relative", display: "flex", height: 10, mt: 1 }} aria-hidden="true">
        <Box sx={{ width: `${verify * 100}%`, bgcolor: "#c4c4c4" }} />
        <Box sx={{ width: `${(block - verify) * 100}%`, bgcolor: "#8f8f8f" }} />
        <Box sx={{ flexGrow: 1, bgcolor: "#444" }} />
        {score !== null && (
          <Box sx={{ position: "absolute", left: `calc(${score * 100}% - 1px)`, top: -4, width: 3, height: 18, bgcolor: "#111" }} />
        )}
      </Box>
      <Typography variant="caption" color="text.secondary" display="block" mt={0.75}>
        Allow &lt; {verify.toFixed(2)} · Verify {verify.toFixed(2)}–{block.toFixed(2)} · Block ≥ {block.toFixed(2)}
      </Typography>
    </Box>
  );
}

export function FraudDecision({ screening, badge, showFeatures = true }: {
  screening: Screening; badge: string; showFeatures?: boolean;
}) {
  const s = screening;
  const rules = s.reasons.filter((r) => !r.startsWith("model_"));
  return (
    <Section title="Fraud decision" action={<Badge label={badge} />}>
      <Typography variant="body2" color="text.secondary">Risk score</Typography>
      <Typography sx={{ fontSize: 44, fontWeight: 700, lineHeight: 1.2 }}>
        {s.score === null ? "–" : s.score.toFixed(2)}
      </Typography>
      <Scale score={s.score} thresholds={s.thresholds} />
      <Divider sx={{ my: 1.5 }} />
      <Typography fontWeight={600} variant="body2" mb={0.5}>Why</Typography>
      {s.reasons.length ? (
        <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
          {s.reasons.map((r) => <Typography component="li" variant="body2" key={r} py={0.25}>{reasonLabel(r)}</Typography>)}
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary">
          {s.outcome === "allow" ? "No rule fired and the score is below the verify threshold." : "No reason recorded."}
        </Typography>
      )}
      <Typography variant="body2" color="text.secondary" mt={0.5}>
        Rules fired: {rules.length ? rules.length : "none"}
      </Typography>
      {s.error && <Typography variant="body2" color="error" mt={0.5}>Screening error: {s.error}</Typography>}
      <Divider sx={{ my: 1.5 }} />
      <Row label="Model" value={s.model_version ?? "none"} />
      <Row label="Rules" value={s.rules_version ?? "–"} />
      <Row label="Policy" value={s.policy_version ?? "–"} />
      <Row label="Feature schema" value={s.feature_schema_version ?? "–"} />
      <Row label="Screening time" value={`${Math.round(s.elapsed_ms)} ms`} />
      {showFeatures && Object.keys(s.features).length > 0 && (
        <>
          <Divider sx={{ my: 1.5 }} />
          <Typography fontWeight={600} variant="body2" mb={0.5}>Features at screening</Typography>
          <Stack>
            {orderedFeatures(s.features).map(([k, v]) => (
              <Row key={k} label={FEATURE_LABELS[k] ?? k} value={featureValue(k, v)} />
            ))}
          </Stack>
        </>
      )}
    </Section>
  );
}
