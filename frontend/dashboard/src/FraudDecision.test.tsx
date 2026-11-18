// "Why was this blocked?": the explanation on the decision record (apps.risk.explain).
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Screening } from "./api/client";
import { FraudDecision } from "./routes/FraudDecision";

afterEach(cleanup);

const base: Screening = {
  id: "scr_1", outcome: "block", score: 0.31, reasons: ["card_attempt_burst", "model_score_high"],
  features: { card_attempts_10m: 5 }, model_version: "hgb-fs02-2026-11-13", rules_version: "rules-0.1",
  policy_version: "policy-hgb-fs02-2026-11-13", feature_schema_version: "fs-0.2", thresholds: null,
  elapsed_ms: 14, error: null, occurred_at: "2026-11-18T06:00:00Z",
};

describe("fraud decision explanation", () => {
  it("shows the headline, the rules that fired and what moved the model score", () => {
    render(<FraudDecision badge="Block" screening={{
      ...base,
      explanation: {
        headline: "earlier tries with this card in 10 minutes ≥ 5 + amount 5.0× this card's usual",
        method: "tree-shap", base_score: 0.0227,
        factors: [
          { source: "rule", code: "card_attempt_burst", direction: "raises",
            text: "Rule card_attempt_burst: Earlier tries with this card in 10 minutes ≥ 5 (was 5)" },
          { source: "model", feature: "amount_to_card_mean_30d", value: 5, effect: 1.31, direction: "raises",
            text: "amount 5.0× this card's usual" },
          { source: "model", feature: "amount_cents", value: 4500, effect: -0.42, direction: "lowers",
            text: "amount S$45.00" },
        ],
      },
    }} />);
    expect(screen.getByText("Earlier tries with this card in 10 minutes ≥ 5 + amount 5.0× this card's usual")).toBeTruthy();
    expect(screen.getByText(/Rule card_attempt_burst/)).toBeTruthy();
    expect(screen.getByText("What moved the model score")).toBeTruthy();
    expect(screen.getByText("+1.31")).toBeTruthy();
    expect(screen.getByText("−0.42")).toBeTruthy();
    expect(screen.getByText(/, raised the risk/)).toBeTruthy();
    expect(screen.getByText(/average score of 0.023/)).toBeTruthy();
    expect(screen.getByText("Recorded reasons")).toBeTruthy();
  });

  it("gives a merchant operator the decision and broad areas only", () => {
    render(<FraudDecision badge="Block" screening={{ id: "scr_1", outcome: "block", occurred_at: "2026-11-18T06:00:00Z",
      merchant_view: true, explanation: { areas: ["Unusual activity on this card"] } }} />);
    expect(screen.getByText("The payment was stopped before it reached the bank.")).toBeTruthy();
    expect(screen.getByText("Main risk areas")).toBeTruthy();
    expect(screen.getByText("Unusual activity on this card")).toBeTruthy();
    for (const hidden of ["Risk score", "Recorded reasons", "Model", "Rules", "Policy", "What moved the model score"]) {
      expect(screen.queryByText(hidden)).toBeNull();
    }
  });

  it("still works for records made before explanations existed", () => {
    render(<FraudDecision badge="Block" screening={base} />);
    expect(screen.getByText("Why")).toBeTruthy();
    expect(screen.queryByText("Recorded reasons")).toBeNull();
  });
});
