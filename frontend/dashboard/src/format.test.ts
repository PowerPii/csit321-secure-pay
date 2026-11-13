import { describe, expect, it } from "vitest";
import { cardLabel, money, parseMoney, riskLabel, shortDate, statusLabel } from "./format";

describe("format", () => {
  it("formats SGD cents", () => {
    expect(money(8990)).toBe("S$ 89.90");
    expect(money(41200)).toBe("S$ 412.00");
    expect(money(123456789)).toBe("S$ 1,234,567.89");
  });

  it("parses amounts typed by staff", () => {
    expect(parseMoney("30")).toBe(3000);
    expect(parseMoney("30.5")).toBe(3050);
    expect(parseMoney("S$ 1,030.05")).toBe(103005);
    expect(parseMoney("30.555")).toBeNull();
    expect(parseMoney("-1")).toBeNull();
    expect(parseMoney("")).toBeNull();
  });

  it("shows refunds in the status as the wireframes do", () => {
    expect(statusLabel("captured", 12900, 0)).toBe("Captured");
    expect(statusLabel("captured", 12900, 2900)).toBe("Partially refunded");
    expect(statusLabel("captured", 12900, 12900)).toBe("Refunded");
    expect(statusLabel("verification_required")).toBe("Awaiting code");
  });

  it("labels risk decisions and cards", () => {
    expect(riskLabel({ decision: "verify", verification: "passed" })).toBe("Verify · passed");
    expect(riskLabel({ decision: "block", verification: null })).toBe("Block");
    expect(cardLabel({ brand: "mastercard", last4: "8812" })).toBe("MC •••• 8812");
  });

  it("shows Singapore time", () => {
    expect(shortDate("2026-11-02T06:52:00Z")).toMatch(/2 Nov.*14:52/);
  });
});
