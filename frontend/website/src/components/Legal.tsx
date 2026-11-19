import { Alert, Box, Link, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { brand } from "../theme";
import { PageHero, Section } from "./Section";

/* Shared layout for the privacy policy and the terms of use: a short hero, the student-project
   notice, a list of sections on wide screens and the sections themselves. */

export interface LegalSection {
  id: string;
  title: string;
  body: ReactNode;
}

export function LegalPage({
  overline,
  title,
  lead,
  updated,
  notice,
  sections,
}: {
  overline: string;
  title: string;
  lead: ReactNode;
  updated: string;
  notice: ReactNode;
  sections: LegalSection[];
}) {
  return (
    <>
      <PageHero overline={overline} title={title} lead={lead}>
        <Typography sx={{ color: "text.secondary", mt: 3, fontSize: 15 }}>Last updated {updated}</Typography>
      </PageHero>
      <Section tone="white" py={{ xs: 6, md: 9 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "220px minmax(0, 1fr)" }, gap: { xs: 4, md: 8 } }}>
          <Box component="nav" aria-label="On this page" sx={{ display: { xs: "none", md: "block" } }}>
            <Box sx={{ position: "sticky", top: 96 }}>
              <Typography variant="overline" component="p" sx={{ color: "text.secondary", mb: 1.5 }}>
                On this page
              </Typography>
              <Box component="ol" sx={{ listStyle: "none", p: 0, m: 0, display: "grid", gap: 1 }}>
                {sections.map((s, i) => (
                  <li key={s.id}>
                    <Link href={`#${s.id}`} underline="hover" sx={{ color: "text.secondary", fontSize: 14.5 }}>
                      {i + 1}. {s.title}
                    </Link>
                  </li>
                ))}
              </Box>
            </Box>
          </Box>
          <Box sx={{ maxWidth: 760 }}>
            <Alert severity="warning" sx={{ mb: 5, fontSize: 15.5, lineHeight: 1.6 }}>
              {notice}
            </Alert>
            {sections.map((s, i) => (
              <Box key={s.id} component="section" id={s.id} sx={{ scrollMarginTop: 96, mb: 6 }}>
                <Typography variant="h2" sx={{ fontSize: { xs: 22, md: 26 }, color: brand.navy, mb: 2 }}>
                  {i + 1}. {s.title}
                </Typography>
                <Box sx={LEGAL_TEXT}>{s.body}</Box>
              </Box>
            ))}
          </Box>
        </Box>
      </Section>
    </>
  );
}

const LEGAL_TEXT = {
  color: "text.secondary",
  fontSize: 16.5,
  lineHeight: 1.75,
  "& p": { m: 0, mb: 2 },
  "& ul": { m: 0, mb: 2, pl: 2.5 },
  "& li": { mb: 0.75 },
  "& strong": { color: "text.primary", fontWeight: 600 },
  "& table": { width: "100%", minWidth: 520, borderCollapse: "collapse", mb: 2, fontSize: 15 },
  "& th, & td": { textAlign: "left", verticalAlign: "top", py: 1.25, pr: 2, borderTop: `1px solid ${brand.line}` },
  "& th": { color: "text.primary", fontWeight: 600 },
  "& code": { fontSize: "0.9em", bgcolor: brand.mist, px: 0.5, borderRadius: "4px" },
};

/** A table that scrolls sideways on a phone instead of widening the page. */
export function LegalTable({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <Box sx={{ overflowX: "auto", mb: 2 }}>
      <table>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </Box>
  );
}
