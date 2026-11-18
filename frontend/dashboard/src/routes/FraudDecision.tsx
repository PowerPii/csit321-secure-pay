// The decision record (FR-FRD-01) as on D4: score on the policy scale, why it was decided in
// plain words (rule hits plus the model's TreeSHAP contributions), reasons and versions.
import { Box, Divider, Stack, Typography } from "@mui/material";
import type { Explanation, ExplanationFactor, MerchantScreening, Screening } from "../api/client";
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

const RAISES = "#B23A48";
const LOWERS = "#4C7FC0";

function ModelFactors({ factors, baseScore }: { factors: ExplanationFactor[]; baseScore: number | null }) {
  const max = Math.max(...factors.map((f) => Math.abs(f.effect ?? 0)), 0.0001);
  return (
    <Box mt={1.5}>
      <Typography fontWeight={600} variant="body2" mb={0.5}>What moved the model score</Typography>
      <Stack gap={0.75} component="ul" sx={{ m: 0, p: 0, listStyle: "none" }}>
        {factors.map((f) => {
          const effect = f.effect ?? 0;
          const up = f.direction === "raises";
          return (
            <Box component="li" key={f.feature} sx={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 90px 52px", gap: 1, alignItems: "center" }}>
              <Typography variant="body2">
                {f.text}
                <Box component="span" sx={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>
                  {up ? ", raised the risk" : ", lowered the risk"}
                </Box>
              </Typography>
              <Box aria-hidden="true" sx={{ height: 8, bgcolor: "#EEEAE2", borderRadius: 1 }}>
                <Box sx={{ height: 8, width: `${Math.max(4, (Math.abs(effect) / max) * 100)}%`, bgcolor: up ? RAISES : LOWERS, borderRadius: 1 }} />
              </Box>
              <Typography variant="caption" textAlign="right" sx={{ fontVariantNumeric: "tabular-nums", color: up ? RAISES : LOWERS }}>
                {effect > 0 ? "+" : "−"}{Math.abs(effect).toFixed(2)}
              </Typography>
            </Box>
          );
        })}
      </Stack>
      <Typography variant="caption" color="text.secondary" display="block" mt={0.75}>
        TreeSHAP contributions in log-odds{baseScore !== null ? `, starting from the model's average score of ${baseScore.toFixed(3)}` : ""}.
        Red raised the risk, blue lowered it.
      </Typography>
    </Box>
  );
}

/** Why: the plain-language explanation stored with the decision. */
function Why({ explanation }: { explanation: Explanation }) {
  if ("areas" in explanation) {
    if (!explanation.areas.length) return null;
    return (
      <Box mb={1}>
        <Typography fontWeight={600} variant="body2" mb={0.5}>Main risk areas</Typography>
        <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
          {explanation.areas.map((a) => <Typography component="li" variant="body2" key={a} py={0.25}>{a}</Typography>)}
        </Box>
      </Box>
    );
  }
  const rules = explanation.factors.filter((f) => f.source !== "model");
  const model = explanation.factors.filter((f) => f.source === "model");
  return (
    <Box mb={1}>
      <Typography fontWeight={600} variant="body2" mb={0.5}>Why</Typography>
      <Typography variant="body2" sx={{ fontWeight: 600, bgcolor: "#F6F3EE", borderRadius: 1, px: 1.25, py: 1 }}>
        {explanation.headline.charAt(0).toUpperCase() + explanation.headline.slice(1)}
      </Typography>
      {rules.length > 0 && (
        <Box mt={1.5}>
          <Typography fontWeight={600} variant="body2" mb={0.5}>Rules and lists that fired</Typography>
          <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
            {rules.map((f) => <Typography component="li" variant="body2" key={f.code ?? f.text} py={0.25}>{f.text}</Typography>)}
          </Box>
        </Box>
      )}
      {model.length > 0 && <ModelFactors factors={model} baseScore={explanation.base_score} />}
    </Box>
  );
}

/** Merchant operators: what was decided and the broad areas, never the screening internals. */
function MerchantDecision({ screening, badge }: { screening: MerchantScreening; badge: string }) {
  const areas = screening.explanation?.areas ?? [];
  const text: Record<string, string> = {
    allow: "Screening found nothing that needed a check.",
    verify: "The customer was asked for an emailed code before the payment went ahead.",
    block: "The payment was stopped before it reached the bank.",
    not_screened: "Screening could not be completed, so the payment was stopped. This is not a fraud finding.",
  };
  return (
    <Section title="Fraud decision" action={<Badge label={badge} />}>
      <Typography variant="body2">{text[screening.outcome] ?? ""}</Typography>
      {areas.length > 0 && (
        <Box mt={1.5}>
          <Typography fontWeight={600} variant="body2" mb={0.5}>Main risk areas</Typography>
          <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
            {areas.map((a) => <Typography component="li" variant="body2" key={a} py={0.25}>{a}</Typography>)}
          </Box>
        </Box>
      )}
      <Typography variant="caption" color="text.secondary" display="block" mt={1.5}>
        The fraud team can see the full decision. Contact them if you think this was a mistake.
      </Typography>
    </Section>
  );
}

export function FraudDecision({ screening, badge, showFeatures = true }: {
  screening: Screening | MerchantScreening; badge: string; showFeatures?: boolean;
}) {
  if ("merchant_view" in screening) return <MerchantDecision screening={screening} badge={badge} />;
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
      {s.explanation && <Why explanation={s.explanation} />}
      <Typography fontWeight={600} variant="body2" mb={0.5}>{s.explanation ? "Recorded reasons" : "Why"}</Typography>
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
