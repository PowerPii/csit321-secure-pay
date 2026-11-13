import { Box, IconButton, Tab, Tabs, Tooltip } from "@mui/material";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import CheckRoundedIcon from "@mui/icons-material/CheckRounded";
import { useState } from "react";
import { brand, fonts } from "../theme";

export type Snippet = { label: string; code: string };

export function CodeBlock({ snippets, title }: { snippets: Snippet[]; title?: string }) {
  const [tab, setTab] = useState(0);
  const [copied, setCopied] = useState(false);
  const current = snippets[Math.min(tab, snippets.length - 1)];

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(current.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked; nothing to do */
    }
  };

  return (
    <Box sx={{ bgcolor: "#0B1424", borderRadius: 3, border: "1px solid rgba(255,255,255,0.08)", overflow: "hidden", boxShadow: "0 30px 60px -30px rgba(10,24,48,0.6)" }}>
      <Box sx={{ display: "flex", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)", pl: 2, pr: 1, minHeight: 44 }}>
        <Box sx={{ display: "flex", gap: 0.75, mr: 2 }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => (
            <Box key={c} sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: c, opacity: 0.8 }} />
          ))}
        </Box>
        {snippets.length > 1 ? (
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            variant="scrollable"
            scrollButtons={false}
            sx={{
              minHeight: 44,
              flex: 1,
              "& .MuiTab-root": { minHeight: 44, color: "rgba(255,255,255,0.55)", fontFamily: fonts.mono, fontSize: 12.5, px: 1.5, minWidth: 0 },
              "& .Mui-selected": { color: "#fff !important" },
              "& .MuiTabs-indicator": { bgcolor: brand.saffron },
            }}
          >
            {snippets.map((s) => (
              <Tab key={s.label} label={s.label} />
            ))}
          </Tabs>
        ) : (
          <Box sx={{ flex: 1, color: "rgba(255,255,255,0.55)", fontFamily: fonts.mono, fontSize: 12.5 }}>{title ?? current.label}</Box>
        )}
        <Tooltip title={copied ? "Copied" : "Copy"}>
          <IconButton size="small" onClick={copy} aria-label="Copy code" sx={{ color: "rgba(255,255,255,0.6)" }}>
            {copied ? <CheckRoundedIcon fontSize="small" /> : <ContentCopyRoundedIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
      </Box>
      <Box
        component="pre"
        sx={{
          m: 0,
          p: { xs: 2, md: 2.5 },
          overflowX: "auto",
          color: "#D6E2F5",
          fontFamily: fonts.mono,
          fontSize: { xs: 12.5, md: 13.5 },
          lineHeight: 1.7,
          "& .k": { color: brand.sky },
          "& .s": { color: "#9BE3B4" },
          "& .c": { color: "rgba(214,226,245,0.45)" },
          "& .n": { color: brand.saffron },
        }}
      >
        <code dangerouslySetInnerHTML={{ __html: highlight(current.code) }} />
      </Box>
    </Box>
  );
}

/** Tiny highlighter for the fixed snippets on this site: comments, strings, numbers, a few keywords. */
function highlight(src: string): string {
  const esc = src.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc.replace(
    /((?<=^|\s)(?:#|\/\/)[^\n]*)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|\b(curl|const|await|import|from|if|return|def|async|function|POST|GET|true|false|null)\b|\b(\d+)\b/gm,
    (m, c, s, k, n) => (c ? `<span class="c">${m}</span>` : s ? `<span class="s">${m}</span>` : k ? `<span class="k">${m}</span>` : n ? `<span class="n">${m}</span>` : m),
  );
}
