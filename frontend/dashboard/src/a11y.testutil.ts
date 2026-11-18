// NFR-USE-02 for the staff dashboard (accessibility pass, 18 Nov 2026): the page tests also run
// axe-core (the engine of the axe DevTools extension) against WCAG 2.2 A and AA on what they
// render. jsdom draws nothing, so colour contrast and phone width are checked in a real browser
// instead (docs/test-report/ACCESSIBILITY.md).
import axe from "axe-core";
import { expect } from "vitest";

export async function expectAccessible(root: Element = document.body) {
  const result = await axe.run(root, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false } },
  });
  expect(result.violations.flatMap((v) => v.nodes.map((n) => `${v.id}: ${n.target.join(" ")}`))).toEqual([]);
}
