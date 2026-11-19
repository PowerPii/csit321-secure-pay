import { Alert, Box, Button, CircularProgress, Container } from "@mui/material";
import ArrowBackRoundedIcon from "@mui/icons-material/ArrowBackRounded";
import DownloadRoundedIcon from "@mui/icons-material/DownloadRounded";
import { useEffect, useRef, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
// Redoc's self-contained bundle, served from this site (no third-party script). Vite copies it
// to /assets with a content hash; it is fetched only when this page opens.
import redocUrl from "redoc/bundles/redoc.standalone.js?url";
import { PageHero } from "../components/Section";
import { usePageTitle } from "../components/usePageTitle";
import { OPENAPI_JSON, OPENAPI_YAML } from "../content/site";
import { brand, fonts } from "../theme";

type RedocGlobal = { init: (spec: string | object, options: object, element: HTMLElement, callback?: (error?: unknown) => void) => void };

let loading: Promise<RedocGlobal> | null = null;
function loadRedoc(): Promise<RedocGlobal> {
  const existing = (window as { Redoc?: RedocGlobal }).Redoc;
  if (existing) return Promise.resolve(existing);
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = redocUrl;
    script.async = true;
    script.onload = () => {
      const r = (window as { Redoc?: RedocGlobal }).Redoc;
      if (r) resolve(r);
      else reject(new Error("Redoc did not load"));
    };
    script.onerror = () => {
      loading = null;
      reject(new Error("Redoc did not load"));
    };
    document.head.appendChild(script);
  });
  return loading;
}

// Redoc's options: https://redocly.com/docs/redoc/config
const REDOC_OPTIONS = {
  scrollYOffset: 72,
  hideDownloadButton: true, // the page has its own download buttons
  expandResponses: "200,201,202",
  jsonSampleExpandLevel: 2,
  pathInMiddlePanel: true,
  sortPropsAlphabetically: false,
  theme: {
    colors: {
      primary: { main: brand.navy },
      // Darker than brand.allow: Redoc writes 2xx response text in this colour on a light tint,
      // and brand.allow there is 3.2:1 (axe color-contrast, completion audit 19 Nov 2026).
      success: { main: "#146C44" },
      warning: { main: brand.verify },
      error: { main: brand.block },
      text: { primary: brand.ink, secondary: brand.muted },
      border: { dark: brand.line, light: brand.mist },
    },
    typography: {
      fontFamily: fonts.body,
      fontSize: "15px",
      headings: { fontFamily: fonts.heading, fontWeight: "600" },
      code: { fontFamily: fonts.mono, fontSize: "13px", color: brand.navy, backgroundColor: brand.mist },
      links: { color: brand.navy },
    },
    sidebar: { backgroundColor: "#F4F6F9", textColor: brand.ink, activeTextColor: brand.navy, width: "260px" },
    rightPanel: { backgroundColor: brand.ink, width: "40%" },
    codeBlock: { backgroundColor: "#0A1424" },
  },
};

export default function ApiExplorer() {
  usePageTitle("Interactive API reference");
  const target = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    loadRedoc()
      .then((redoc) => {
        if (cancelled || !target.current) return;
        redoc.init(OPENAPI_JSON, REDOC_OPTIONS, target.current, (error) => !cancelled && setState(error ? "error" : "ready"));
      })
      .catch(() => !cancelled && setState("error"));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <PageHero
        overline="API reference"
        title="Every endpoint, from the OpenAPI file"
        lead="This page is drawn from the same OpenAPI 3.1 file the gateway is tested against. Download it to generate a client, import it into Postman or Insomnia, or read it here."
      >
        <Box sx={{ mt: 4, display: "flex", gap: 1.5, flexWrap: "wrap" }}>
          <Button component={RouterLink} to="/developers/api" variant="contained" color="secondary" size="large" startIcon={<ArrowBackRoundedIcon />}>
            Written reference
          </Button>
          <Button href={OPENAPI_YAML} download size="large" startIcon={<DownloadRoundedIcon />} sx={{ color: brand.navy }}>
            OpenAPI (YAML)
          </Button>
          <Button href={OPENAPI_JSON} download size="large" startIcon={<DownloadRoundedIcon />} sx={{ color: brand.navy }}>
            OpenAPI (JSON)
          </Button>
        </Box>
      </PageHero>
      <Box sx={{ bgcolor: "#fff", borderTop: `1px solid ${brand.line}`, minHeight: 400 }}>
        {state === "loading" && (
          <Box sx={{ display: "grid", placeItems: "center", py: 10 }}>
            <CircularProgress aria-label="Loading the API reference" />
          </Box>
        )}
        {state === "error" && (
          <Container maxWidth="lg" sx={{ py: 6 }}>
            <Alert severity="warning">
              The interactive reference did not load. The <RouterLink to="/developers/api">written reference</RouterLink> has the same content, or download the OpenAPI file above.
            </Alert>
          </Container>
        )}
        <Box ref={target} sx={{ "& .menu-content": { top: "72px !important" } }} />
      </Box>
    </>
  );
}
