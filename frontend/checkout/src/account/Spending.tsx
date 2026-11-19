// Spending insights on the customer account (/account/spending): what this customer spent in
// the last 12 months, by month and by merchant, after refunds. Only their own payments (the
// ones in Payment history) are counted; the gateway works the numbers out (GET
// /customer/insights) and sends no card details.
//
// Accessibility (as in the 18 Nov 2026 pass): each chart is an SVG with a text summary
// (role="img"), every bar has a tooltip title, and a button swaps the chart for a table with
// the same numbers. Charts draw at their real width so the text stays readable on a phone.
// Only SVG attributes are used, no inline styles, so the page CSP stays as it is.
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { getInsights, type Insights, type MerchantSpend, type MonthSpend } from "../accountApi";
import { money } from "../format";
import { asError } from "./forms";

const BAR = "#13243F"; // brand navy: 15:1 against white
const GRID = "#E1E6ED";
const INK = "#4f4f4f"; // axis text, 8:1 against white

export function monthLabel(key: string, style: "short" | "long" = "short"): string {
  const [y, m] = key.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, 1));
  return date.toLocaleDateString("en-SG", style === "short"
    ? { month: "short", timeZone: "UTC" } : { month: "long", year: "numeric", timeZone: "UTC" });
}

/** Whole dollars for axis ticks: "S$ 0", "S$ 1,200". */
function dollars(cents: number): string {
  return `S$ ${Math.round(cents / 100).toLocaleString("en-SG")}`;
}

/** A round axis top and step (1, 2 or 5 times a power of ten) above `max` cents. */
export function niceScale(max: number, ticks = 4): { top: number; step: number } {
  if (max <= 0) return { top: 10000, step: 2500 };
  const raw = max / ticks;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((f) => f * power).find((s) => s >= raw) ?? 10 * power;
  return { top: step * Math.ceil(max / step), step };
}

function useWidth(fallback = 560) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(typeof ResizeObserver === "undefined" ? fallback : 0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width);
      if (w > 0) setWidth(w);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

export function Spending({ onEnded }: { onEnded: () => void }) {
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState<string>();

  useEffect(() => {
    getInsights()
      .then(setData)
      .catch((err) => (asError(err).status === 401 ? onEnded() : setError(asError(err).message)));
  }, [onEnded]);

  const range = data ? `${monthLabel(data.from, "long")} to ${monthLabel(data.to, "long")}` : "";
  return (
    <>
      <h1>Spending</h1>
      <p className="muted small">
        What you paid in the last 12 months{range && ` (${range})`}, after refunds. Only payments made while signed in to this
        account are counted, the same ones as in your payment history.
      </p>
      {error && <p className="alert" role="alert">{error}</p>}
      {!data && !error && <p className="muted">Loading…</p>}
      {data && data.totals.payments === 0 && (
        <div className="box grey">
          <strong>Nothing spent yet</strong>
          <p className="muted small">Once a shop charges a payment you made while signed in, it is added up here by month and by shop.</p>
          {data.totals.on_hold_payments > 0 && <OnHold data={data} />}
        </div>
      )}
      {data && data.totals.payments > 0 && (
        <>
          <dl className="spend-tiles">
            <Tile label="Spent after refunds" value={money(data.totals.net)} />
            <Tile label="Charged payments" value={String(data.totals.payments)} />
            <Tile label="Refunded" value={money(data.totals.refunded)} />
            <Tile label="Shops" value={String(data.totals.merchants)} />
          </dl>
          {data.totals.on_hold_payments > 0 && <OnHold data={data} />}
          <ChartSection title="By month" table={<MonthTable rows={data.by_month} />}>
            <MonthChart rows={data.by_month} />
          </ChartSection>
          <ChartSection title="By shop" table={<MerchantTable rows={data.by_merchant} />}>
            <MerchantChart rows={data.by_merchant} />
          </ChartSection>
          <p className="muted small">
            A payment counts in the month it was made (Singapore time). A refund lowers the month and shop of the payment it
            belongs to, once the refund is complete.
          </p>
        </>
      )}
    </>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="spend-tile">
      <dt className="muted small">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function OnHold({ data }: { data: Insights }) {
  const n = data.totals.on_hold_payments;
  return (
    <p className="muted small">
      {money(data.totals.on_hold)} in {n} {n === 1 ? "payment is" : "payments are"} on hold: approved but not yet charged by the
      shop, so not counted above.
    </p>
  );
}

function ChartSection({ title, table, children }: { title: string; table: ReactNode; children: ReactNode }) {
  const [asTable, setAsTable] = useState(false);
  const headingId = useId();
  const bodyId = useId();
  return (
    <section className="box spend-section" aria-labelledby={headingId}>
      <div className="row-between">
        <h2 id={headingId} className="small-heading">{title}</h2>
        <button type="button" className="link" aria-controls={bodyId} aria-pressed={asTable} onClick={() => setAsTable((t) => !t)}>
          {asTable ? "Show chart" : "Show table"}
        </button>
      </div>
      {/* A wide table scrolls sideways on a phone, so the region takes keyboard focus. */}
      <div id={bodyId} tabIndex={asTable ? 0 : undefined} role={asTable ? "region" : undefined}
        aria-label={asTable ? `${title} table` : undefined}>{asTable ? table : children}</div>
    </section>
  );
}

export function MonthChart({ rows }: { rows: MonthSpend[] }) {
  const { ref, width } = useWidth();
  const height = 200;
  const left = 64, right = 8, top = 10, bottom = 26;
  const max = Math.max(0, ...rows.map((r) => r.net));
  const { top: axisTop, step } = niceScale(max);
  const plotW = Math.max(0, width - left - right);
  const plotH = height - top - bottom;
  const slot = plotW / rows.length;
  const barW = Math.max(4, Math.min(36, slot * 0.6));
  const y = (v: number) => top + plotH - (v / axisTop) * plotH;
  const ticks: number[] = [];
  for (let v = 0; v <= axisTop; v += step) ticks.push(v);
  const labelEvery = slot < 34 ? 2 : 1; // every other month on a narrow phone
  const highest = rows.reduce((a, b) => (b.net > a.net ? b : a), rows[0]);
  const summary = `Bar chart of money spent after refunds in each of the last ${rows.length} months. ` +
    (max > 0 ? `Highest: ${monthLabel(highest.month, "long")}, ${money(highest.net)}.` : "Nothing was spent.");

  return (
    <div ref={ref} className="spend-chart">
      {width > 0 && (
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary}>
          {ticks.map((v) => (
            <g key={v}>
              <line x1={left} x2={width - right} y1={y(v)} y2={y(v)} stroke={GRID} />
              <text x={left - 6} y={y(v)} dy="0.32em" textAnchor="end" fontSize="11" fill={INK}>{dollars(v)}</text>
            </g>
          ))}
          {rows.map((r, i) => {
            const cx = left + slot * i + slot / 2;
            const h = Math.max(0, y(0) - y(r.net));
            return (
              <g key={r.month}>
                {r.net > 0 && (
                  <rect x={cx - barW / 2} y={y(r.net)} width={barW} height={h} rx="2" fill={BAR}>
                    <title>{`${monthLabel(r.month, "long")}: ${money(r.net)} (${r.payments} ${r.payments === 1 ? "payment" : "payments"})`}</title>
                  </rect>
                )}
                {(i % labelEvery === (rows.length - 1) % labelEvery) && (
                  <text x={cx} y={height - 8} textAnchor="middle" fontSize="11" fill={INK}>{monthLabel(r.month)}</text>
                )}
              </g>
            );
          })}
          <line x1={left} x2={width - right} y1={y(0)} y2={y(0)} stroke="#8a8a8a" />
        </svg>
      )}
    </div>
  );
}

export function MerchantChart({ rows }: { rows: MerchantSpend[] }) {
  const { ref, width } = useWidth();
  const rowH = 30, gap = 8;
  const height = rows.length * (rowH + gap);
  const labelW = Math.min(150, Math.round(width * 0.36));
  const valueW = 92;
  const plotW = Math.max(0, width - labelW - valueW);
  const max = Math.max(1, ...rows.map((r) => r.net));
  const summary = `Bar chart of money spent after refunds at each shop. ` +
    rows.map((r) => `${r.merchant_name}: ${money(r.net)}`).join("; ") + ".";
  const fit = (name: string) => {
    const chars = Math.max(6, Math.floor(labelW / 7));
    return name.length > chars ? `${name.slice(0, chars - 1)}…` : name;
  };

  return (
    <div ref={ref} className="spend-chart">
      {width > 0 && (
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary}>
          {rows.map((r, i) => {
            const yTop = i * (rowH + gap);
            const w = r.net > 0 ? Math.max(2, (r.net / max) * plotW) : 0;
            return (
              <g key={r.merchant_name}>
                <title>{`${r.merchant_name}: ${money(r.net)} (${r.payments} ${r.payments === 1 ? "payment" : "payments"})`}</title>
                <text x={0} y={yTop + rowH / 2} dy="0.32em" fontSize="13" fill="#1f1f1f">{fit(r.merchant_name)}</text>
                <rect x={labelW} y={yTop + 4} width={w} height={rowH - 8} rx="2" fill={BAR} />
                <text x={labelW + w + 6} y={yTop + rowH / 2} dy="0.32em" fontSize="12" fill={INK}>{money(r.net)}</text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

function MonthTable({ rows }: { rows: MonthSpend[] }) {
  return (
    <table className="history-table spend-table">
      <caption className="sr-only">Spending by month</caption>
      <thead>
        <tr><th scope="col">Month</th><th scope="col">Payments</th><th scope="col">Charged</th><th scope="col">Refunded</th><th scope="col">After refunds</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.month}>
            <th scope="row">{monthLabel(r.month, "long")}</th>
            <td>{r.payments}</td><td>{money(r.spent)}</td><td>{money(r.refunded)}</td><td>{money(r.net)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MerchantTable({ rows }: { rows: MerchantSpend[] }) {
  return (
    <table className="history-table spend-table">
      <caption className="sr-only">Spending by shop</caption>
      <thead>
        <tr><th scope="col">Shop</th><th scope="col">Payments</th><th scope="col">Charged</th><th scope="col">Refunded</th><th scope="col">After refunds</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.merchant_name}>
            <th scope="row">{r.merchant_count ? `${r.merchant_name} (${r.merchant_count})` : r.merchant_name}</th>
            <td>{r.payments}</td><td>{money(r.spent)}</td><td>{money(r.refunded)}</td><td>{money(r.net)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
