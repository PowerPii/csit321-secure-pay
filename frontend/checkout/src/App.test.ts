import { describe, expect, it } from "vitest";
import { sessionIdFromPath } from "./App";

describe("sessionIdFromPath", () => {
  it("reads the session id from the hosted checkout URL", () => {
    expect(sessionIdFromPath("/checkout/cs_123")).toBe("cs_123");
    expect(sessionIdFromPath("/elsewhere")).toBeNull();
  });
});
