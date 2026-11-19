// The public website's CI journey (completion audit, 19 Nov 2026, section 3). It walks the
// routes a first-time visitor uses (home -> developers quickstart -> API reference, the status
// page, the legal pages, a wrong link and the contact page) and checks the fixes from the audit
// stay fixed. Every route is also scanned with axe-core against WCAG 2.2 A and AA. jsdom draws
// nothing, so colour contrast and phone width are checked in a real browser instead
// (docs/test-report/ACCESSIBILITY.md, "Public website").
import { CssBaseline, ThemeProvider } from "@mui/material";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { headlineFor } from "./pages/Status";
import { theme } from "./theme";

function visit(path: string) {
  return render(
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

async function expectNoAxeViolations() {
  const result = await axe.run(document.body, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    rules: { "color-contrast": { enabled: false } }, // needs a real renderer
  });
  expect(result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

const NOW = Date.parse("2026-11-19T10:00:00Z");
const part = (id: string, status: "operational" | "outage" | "unknown") => ({
  id, name: id, description: `${id} part`, status, uptime: status === "unknown" ? null : 100, days: [],
});
function statusData(over: Record<string, unknown> = {}) {
  return {
    status: "operational", updated_at: new Date(NOW).toISOString(), checked_at: new Date(NOW - 120_000).toISOString(),
    notice: "", time_zone: "Asia/Singapore", check_every_minutes: 5, history_days: 90, incident_days: 14,
    measured_since: "2026-11-19T00:00:00Z", incidents: [],
    components: ["api", "database", "worker", "network", "shop"].map((id) => part(id, "operational")),
    ...over,
  };
}
const json = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });

beforeAll(() => {
  window.scrollTo = () => {}; // jsdom has no layout; the app scrolls to the top on each page
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("first-time developer journey", () => {
  it("goes from the home page to the quickstart and on to the API reference", async () => {
    visit("/");
    expect(await screen.findByRole("heading", { level: 1 })).toBeTruthy();
    await expectNoAxeViolations();

    const [toDevelopers] = screen.getAllByRole("link", { name: /developers/i });
    fireEvent.click(toDevelopers);
    expect(await screen.findByRole("heading", { level: 1, name: /build against a small, strict api/i })).toBeTruthy();
    const quickstart = screen.getByRole("heading", { name: "Quickstart" });
    expect(quickstart.closest("section, [id]")?.getAttribute("id")).toBe("quickstart");
    await expectNoAxeViolations();

    const [toReference] = screen.getAllByRole("link", { name: /api reference/i });
    fireEvent.click(toReference);
    expect(await screen.findByRole("heading", { level: 1, name: /merchant api v1/i })).toBeTruthy();
    await expectNoAxeViolations();
  });
});

describe("status page", () => {
  it("says it is checking before the first answer, never 'operational'", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    visit("/status");
    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("Checking status");
    expect(document.body.textContent).not.toContain("All systems operational");
    await expectNoAxeViolations();
  });

  it("shows when it last checked, and the healthy headline only with fresh checks of every part", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(statusData({ updated_at: new Date().toISOString(), checked_at: new Date().toISOString() }))));
    visit("/status");
    expect(await screen.findByText("All systems operational")).toBeTruthy();
    expect(screen.getByText(/Last checked/)).toBeTruthy();
    await expectNoAxeViolations();
  });

  it("keeps 'no recent check' apart from healthy, and old checks apart from fresh ones", () => {
    const data = statusData();
    expect(headlineFor(data as never, false, NOW)).toBe("operational");
    const someUnknown = { ...data, components: [...data.components.slice(1), part("shop", "unknown")] };
    expect(headlineFor(someUnknown as never, false, NOW)).toBe("unknown");
    expect(headlineFor({ ...data, status: "unknown" } as never, false, NOW)).toBe("unknown");
    expect(headlineFor({ ...data, checked_at: new Date(NOW - 60 * 60_000).toISOString() } as never, false, NOW)).toBe("stale");
    // A known outage is shown even when other checks are old.
    expect(headlineFor({ ...data, status: "partial_outage", checked_at: "2026-11-01T00:00:00Z" } as never, false, NOW)).toBe("partial_outage");
    expect(headlineFor(null, false, NOW)).toBe("checking");
    expect(headlineFor(data as never, true, NOW)).toBe("unreachable");
  });

  it("says it can't reach the server when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    visit("/status");
    expect(await screen.findByText("We can’t reach SecurePay")).toBeTruthy();
  });

  it("never lets an older, slower answer overwrite a newer one", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const replies: ((r: Response) => void)[] = [];
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => replies.push(resolve))));
    visit("/status");
    await screen.findByText("Checking status");
    const fresh = new Date().toISOString();
    act(() => vi.advanceTimersByTime(60_000)); // the page asks again every minute
    expect(replies.length).toBe(2);
    await act(async () => replies[1](json(statusData({ updated_at: fresh, checked_at: fresh }))));
    expect(await screen.findByText("All systems operational")).toBeTruthy();
    await act(async () => replies[0](json(statusData({ status: "major_outage", updated_at: fresh, checked_at: fresh }))));
    expect(screen.getByText("All systems operational")).toBeTruthy();
    expect(screen.queryByText("Payments are down")).toBeNull();
  });
});

describe("legal pages", () => {
  for (const [path, title] of [["/privacy", "Privacy policy"], ["/terms", "Terms of use"]] as const) {
    it(`${title}: links in the text are underlined, not told apart by colour alone`, async () => {
      visit(path);
      await screen.findByRole("heading", { level: 1, name: title });
      const inText = [...document.querySelectorAll<HTMLAnchorElement>("main section[id] p a, main section[id] li a")];
      expect(inText.length).toBeGreaterThan(0);
      // MUI's underline="always" (the theme default since the audit); jsdom does not compute it.
      for (const a of inText) expect(a.className).toContain("MuiLink-underlineAlways");
      await expectNoAxeViolations();
    });
  }

  it("Privacy: every table that scrolls sideways can be reached and scrolled with the keyboard", async () => {
    visit("/privacy");
    await screen.findByRole("heading", { level: 1, name: "Privacy policy" });
    const tables = document.querySelectorAll("main table");
    expect(tables.length).toBeGreaterThanOrEqual(4);
    for (const table of tables) {
      const scroller = table.parentElement!;
      expect(scroller.getAttribute("tabindex")).toBe("0");
      expect(scroller.getAttribute("role")).toBe("region");
      expect(scroller.getAttribute("aria-label")).toBeTruthy();
    }
  });
});

describe("dead ends", () => {
  it("a wrong link has a page heading and a way to get help", async () => {
    visit("/no-such-page");
    expect(await screen.findByRole("heading", { level: 1, name: /doesn’t exist/ })).toBeTruthy();
    const main = screen.getByRole("main");
    expect(within(main).getByRole("link", { name: /contact the team/i }).getAttribute("href")).toBe("/contact");
    await expectNoAxeViolations();
  });

  it("the contact page never sends a visitor to a private GitHub page", async () => {
    visit("/contact");
    await screen.findByRole("heading", { level: 1, name: "Contact the team" });
    fireEvent.change(screen.getByLabelText(/name/i, { selector: "input" }), { target: { value: "Ada" } });
    fireEvent.change(screen.getByLabelText(/email/i, { selector: "input" }), { target: { value: "ada@example.com" } });
    fireEvent.change(screen.getByLabelText(/message/i), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: /send message/i }));
    const main = screen.getByRole("main");
    const links = within(main).getAllByRole("link").map((a) => a.getAttribute("href") ?? "");
    expect(links.filter((h) => h.includes("github.com"))).toEqual([]);
    expect(within(main).getByRole("link", { name: /developer guide/i }).getAttribute("href")).toBe("/developers");
    await expectNoAxeViolations();
  });
});
