import { Box, Container, Link, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import { Fragment, useEffect, useState, type ReactNode } from "react";
import { Link as RouterLink, useLocation } from "react-router-dom";
import type { Field } from "../content/apiReference";
import { brand, fonts } from "../theme";

/** Text with `backticks` shown as inline code. */
export function Inline({ text }: { text: string }) {
  const parts = text.split("`");
  return (
    <>
      {parts.map((p, i) =>
        i % 2 ? (
          <Box key={i} component="code" sx={{ fontFamily: fonts.mono, fontSize: "0.88em", px: 0.6, py: 0.1, borderRadius: 1, bgcolor: "rgba(15,34,64,0.06)", wordBreak: "break-word" }}>
            {p}
          </Box>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}

export const P = ({ children }: { children: ReactNode }) => (
  <Typography component="div" sx={{ color: "text.secondary", lineHeight: 1.7, mb: 2.5, maxWidth: 760, "& code": { fontFamily: fonts.mono, fontSize: "0.88em" } }}>
    {typeof children === "string" ? <Inline text={children} /> : children}
  </Typography>
);

export function DocSection({ id, title, children, level = 2 }: { id: string; title: string; children: ReactNode; level?: 2 | 3 }) {
  return (
    <Box
      component="section"
      id={id}
      data-doc-section={level === 2 ? "" : undefined}
      sx={{ scrollMarginTop: 96, py: level === 2 ? { xs: 5, md: 6 } : 3, borderTop: level === 2 ? `1px solid ${brand.line}` : 0, "&:first-of-type": { borderTop: 0, pt: 0 } }}
    >
      <Typography variant={level === 2 ? "h3" : "h4"} component={level === 2 ? "h2" : "h3"} sx={{ fontSize: level === 2 ? { xs: 26, md: 32 } : { xs: 20, md: 22 }, mb: 2 }}>
        {title}
      </Typography>
      {children}
    </Box>
  );
}

export function Callout({ children, tone = "warn" }: { children: ReactNode; tone?: "warn" | "info" }) {
  const c = tone === "warn" ? { bg: "#FFF6E5", line: "#F3D9A4" } : { bg: brand.mist, line: brand.line };
  return (
    <Box sx={{ my: 2.5, p: 2.5, borderRadius: 3, bgcolor: c.bg, border: `1px solid ${c.line}`, maxWidth: 760 }}>
      <Typography component="div" sx={{ fontSize: 15, lineHeight: 1.6 }}>
        {typeof children === "string" ? <Inline text={children} /> : children}
      </Typography>
    </Box>
  );
}

const tableSx = { bgcolor: "#fff", border: `1px solid ${brand.line}`, borderRadius: 3, mb: 3 };
const headSx = { fontWeight: 600, whiteSpace: "nowrap" as const };

/** A plain table; cells are strings with `inline code`. The first column is set in mono. */
export function SimpleTable({ head, rows, monoCols = [0] }: { head: string[]; rows: string[][]; monoCols?: number[] }) {
  return (
    <TableContainer sx={tableSx}>
      <Table size="small">
        <TableHead>
          <TableRow>
            {head.map((h) => (
              <TableCell key={h} sx={headSx}>
                {h}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.join("|")}>
              {r.map((c, i) => (
                <TableCell key={i} sx={monoCols.includes(i) ? { fontFamily: fonts.mono, fontSize: 13, whiteSpace: { sm: "nowrap" }, verticalAlign: "top" } : { color: "text.secondary", verticalAlign: "top" }}>
                  {monoCols.includes(i) ? c : <Inline text={c} />}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

/** Parameters or object fields: name and type on the left, description on the right. */
export function FieldList({ fields, compact = false }: { fields: Field[]; compact?: boolean }) {
  return (
    <Box sx={{ ...tableSx, overflow: "hidden" }}>
      {fields.map((f, i) => (
        <Box
          key={f.name}
          sx={{ display: "grid", gridTemplateColumns: compact ? "1fr" : { xs: "1fr", sm: "240px 1fr" }, gap: compact ? 0.5 : { xs: 0.5, sm: 2 }, px: 2, py: 1.5, borderTop: i ? `1px solid ${brand.line}` : 0 }}
        >
          <Box>
            <Typography component="span" sx={{ fontFamily: fonts.mono, fontSize: 13.5, fontWeight: 600, wordBreak: "break-word" }}>
              {f.name}
            </Typography>
            <Typography component="span" sx={{ fontFamily: fonts.mono, fontSize: 12, color: "text.secondary", ml: 1 }}>
              {f.type}
            </Typography>
            {f.required && (
              <Typography component="span" sx={{ fontSize: 11.5, fontWeight: 600, color: "text.secondary", ml: 1, }}>
                required
              </Typography>
            )}
          </Box>
          <Typography sx={{ color: "text.secondary", fontSize: 14.5, lineHeight: 1.6 }}>
            <Inline text={f.text} />
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

export function MethodBadge({ method }: { method: string }) {
  const post = method === "POST";
  return (
    <Box
      component="span"
      sx={{
        display: "inline-block",
        minWidth: 46,
        textAlign: "center",
        px: 0.75,
        py: 0.2,
        borderRadius: 1.5,
        fontFamily: fonts.mono,
        fontSize: 11.5,
        fontWeight: 700,
        color: post ? "#7A4A00" : "#0B4F33",
        bgcolor: post ? "#FDEBC8" : "#D5F2E3",
      }}
    >
      {method}
    </Box>
  );
}

// ---------------------------------------------------------------- shell with sidebar

export type DocNavGroup = { title: string; base: string; items: { id: string; label: string }[] };

/** Highlights the sidebar entry of the section in view. */
function useActiveSection(ids: string[]) {
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    const els = ids.map((id) => document.getElementById(id)).filter((e): e is HTMLElement => !!e);
    if (!els.length || typeof IntersectionObserver === "undefined") return;
    const seen = new Map<string, boolean>();
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => seen.set(e.target.id, e.isIntersecting));
        const first = ids.find((id) => seen.get(id));
        if (first) setActive(first);
      },
      { rootMargin: "-90px 0px -60% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [ids.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  return active;
}

export function DocsShell({ nav, children }: { nav: DocNavGroup[]; children: ReactNode }) {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/+$/, "");
  const currentIds = nav.find((g) => g.base === here)?.items.map((i) => i.id) ?? [];
  const active = useActiveSection(currentIds);

  return (
    <Container maxWidth="lg" sx={{ py: { xs: 4, md: 8 } }}>
      {/* Guides / reference switch, always visible (the only nav on phones). */}
      <Box sx={{ display: "flex", gap: 1, mb: { xs: 4, md: 6 }, borderBottom: `1px solid ${brand.line}` }}>
        {nav.map((g) => {
          const on = g.base === here;
          return (
            <Link
              key={g.base}
              component={RouterLink}
              to={g.base}
              underline="none"
              sx={{
                px: 1.5,
                py: 1.25,
                mb: "-1px",
                fontWeight: 600,
                fontSize: 15,
                color: on ? "text.primary" : "text.secondary",
                borderBottom: `2px solid ${on ? brand.brass : "transparent"}`,
                "&:hover": { color: "text.primary" },
              }}
            >
              {g.title}
            </Link>
          );
        })}
      </Box>

      <Grid container spacing={{ xs: 0, md: 6 }}>
        <Grid size={{ md: 3 }} sx={{ display: { xs: "none", md: "block" } }}>
          <Box component="nav" aria-label="Documentation" sx={{ position: "sticky", top: 100, maxHeight: "calc(100vh - 120px)", overflowY: "auto", pr: 1 }}>
            {nav.map((g) => (
              <Box key={g.base} sx={{ mb: 3 }}>
                <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: "text.secondary", mb: 1 }}>{g.title}</Typography>
                {g.items.map((t) => {
                  const on = g.base === here && active === t.id;
                  return (
                    <Link
                      key={t.id}
                      component={RouterLink}
                      to={`${g.base}#${t.id}`}
                      underline="none"
                      sx={{
                        display: "block",
                        py: 0.6,
                        pl: 1.5,
                        fontSize: 14.5,
                        borderLeft: `2px solid ${on ? brand.brass : brand.line}`,
                        color: on ? "text.primary" : "text.secondary",
                        fontWeight: on ? 600 : 400,
                        "&:hover": { color: "text.primary" },
                      }}
                    >
                      {t.label}
                    </Link>
                  );
                })}
              </Box>
            ))}
          </Box>
        </Grid>
        <Grid size={{ xs: 12, md: 9 }} sx={{ minWidth: 0 }}>
          {children}
        </Grid>
      </Grid>
    </Container>
  );
}

export const DOCS_NAV: DocNavGroup[] = [
  {
    title: "Guides",
    base: "/developers",
    items: [
      { id: "get-started", label: "Get started" },
      { id: "quickstart", label: "Quickstart" },
      { id: "sdk", label: "Node.js SDK" },
      { id: "auth", label: "Authentication" },
      { id: "lifecycle", label: "Payment lifecycle" },
      { id: "capture", label: "Capture and refunds" },
      { id: "idempotency", label: "Idempotency" },
      { id: "webhooks", label: "Webhooks" },
      { id: "errors", label: "Errors" },
      { id: "test-cards", label: "Test cards" },
      { id: "resources", label: "Contracts and specs" },
    ],
  },
  {
    title: "API reference",
    base: "/developers/api",
    items: [
      { id: "basics", label: "Basics" },
      { id: "create-payment", label: "Create a payment" },
      { id: "get-payment", label: "Retrieve a payment" },
      { id: "capture-payment", label: "Capture a payment" },
      { id: "cancel-payment", label: "Cancel a payment" },
      { id: "create-refund", label: "Refund a payment" },
      { id: "list-refunds", label: "List refunds" },
      { id: "get-refund", label: "Retrieve a refund" },
      { id: "payment-object", label: "The Payment object" },
      { id: "refund-object", label: "The Refund object" },
      { id: "events", label: "Webhook events" },
      { id: "error-codes", label: "Error codes" },
    ],
  },
];
