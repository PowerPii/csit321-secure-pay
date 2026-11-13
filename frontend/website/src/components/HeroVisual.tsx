import { Box, Typography } from "@mui/material";
import LockRoundedIcon from "@mui/icons-material/LockRounded";
import { useEffect, useState } from "react";
import { brand, fonts } from "../theme";
import { StatusChip, type Tone } from "./StatusChip";

type Decision = { ref: string; amount: string; score: number; tone: Tone; label: string; reason: string };

const FEED: Decision[] = [
  { ref: "SP-7KQ4-M2XD", amount: "S$42.90", score: 0.04, tone: "allow", label: "allow", reason: "usual amount for this card" },
  { ref: "SP-H8RW-3NPA", amount: "S$1,280.00", score: 0.41, tone: "verify", label: "verify", reason: "new card, amount above usual" },
  { ref: "SP-Z5TB-9CUE", amount: "S$18.50", score: 0.02, tone: "allow", label: "allow", reason: "returning customer" },
  { ref: "SP-Q2LM-6VJS", amount: "S$9,400.00", score: 0.93, tone: "block", label: "block", reason: "6 cards from one IP in 10 min" },
  { ref: "SP-B4NC-7GWY", amount: "S$65.00", score: 0.07, tone: "allow", label: "allow", reason: "low risk" },
  { ref: "SP-T9EK-2HFR", amount: "S$730.00", score: 0.38, tone: "verify", label: "verify", reason: "3 attempts on this card in 10 min" },
];

function useTicker(length: number, ms: number) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setI((x) => (x + 1) % length), ms);
    return () => clearInterval(t);
  }, [length, ms]);
  return i;
}

export function HeroVisual() {
  const tick = useTicker(FEED.length, 2200);
  const rows = Array.from({ length: 4 }, (_, k) => FEED[(tick + k) % FEED.length]);

  return (
    <Box sx={{ position: "relative", width: "100%", maxWidth: 520, mx: "auto", minHeight: { xs: 600, sm: 580 } }} aria-hidden>
      {/* Checkout card */}
      <Box
        sx={{
          position: "absolute",
          top: 0,
          left: { xs: 0, sm: 0 },
          width: { xs: "88%", sm: 330 },
          bgcolor: "#fff",
          color: brand.inkDeep,
          borderRadius: 4,
          p: 3,
          boxShadow: "0 40px 80px -30px rgba(0,0,0,0.55)",
        }}
      >
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
          <Typography sx={{ fontWeight: 700, fontSize: 15 }}>Kopi &amp; Co. Roasters</Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, color: brand.muted, fontSize: 12 }}>
            <LockRoundedIcon sx={{ fontSize: 14 }} /> Secure checkout
          </Box>
        </Box>
        {[
          ["Single-origin beans ×2", "S$36.00"],
          ["Pour-over filter", "S$6.90"],
        ].map(([n, a]) => (
          <Box key={n} sx={{ display: "flex", justifyContent: "space-between", fontSize: 14, color: brand.muted, py: 0.5 }}>
            <span>{n}</span>
            <span>{a}</span>
          </Box>
        ))}
        <Box sx={{ display: "flex", justifyContent: "space-between", fontWeight: 700, borderTop: `1px solid ${brand.line}`, mt: 1, pt: 1.5, mb: 2.5 }}>
          <span>Total</span>
          <span>S$42.90</span>
        </Box>
        <FakeInput label="Card number" value="4242 4242 4242 4242" mono />
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1.5 }}>
          <FakeInput label="Expiry" value="12 / 29" mono />
          <FakeInput label="CVC" value="•••" mono />
        </Box>
        <Box sx={{ mt: 1, bgcolor: brand.ink, color: "#fff", borderRadius: 999, textAlign: "center", py: 1.25, fontWeight: 600, fontSize: 15 }}>
          Pay S$42.90
        </Box>
      </Box>

      {/* Screening feed */}
      <Box
        sx={{
          position: "absolute",
          right: 0,
          bottom: 0,
          width: { xs: "92%", sm: 340 },
          bgcolor: "rgba(16,32,58,0.92)",
          backdropFilter: "blur(10px)",
          border: "1px solid rgba(255,255,255,0.12)",
          borderRadius: 4,
          p: 2.25,
          boxShadow: "0 40px 80px -30px rgba(0,0,0,0.6)",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
          <Typography sx={{ color: "#fff", fontWeight: 600, fontSize: 14 }}>Screening decisions</Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, color: "rgba(255,255,255,0.6)", fontSize: 12, fontFamily: fonts.mono }}>
            <Box
              sx={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                bgcolor: brand.allow,
                "@keyframes pulse": { "0%,100%": { opacity: 1 }, "50%": { opacity: 0.3 } },
                animation: "pulse 1.6s infinite",
              }}
            />
            p95 &lt; 200 ms
          </Box>
        </Box>
        {rows.map((d, k) => (
          <Box
            key={`${d.ref}-${tick}-${k}`}
            sx={{
              display: "grid",
              gridTemplateColumns: "1fr auto",
              gap: 0.25,
              py: 1.1,
              borderTop: k ? "1px solid rgba(255,255,255,0.07)" : "none",
              "@keyframes slideIn": { from: { opacity: 0, transform: "translateY(-6px)" }, to: { opacity: 1, transform: "none" } },
              animation: k === 0 ? "slideIn .45s ease-out" : undefined,
              opacity: 1 - k * 0.16,
            }}
          >
            <Box sx={{ fontFamily: fonts.mono, fontSize: 12.5, color: "#fff" }}>
              {d.ref} <Box component="span" sx={{ color: "rgba(255,255,255,0.5)" }}>· {d.amount}</Box>
            </Box>
            <StatusChip tone={d.tone} dark>
              {d.label}
            </StatusChip>
            <Box sx={{ fontSize: 12, color: "rgba(255,255,255,0.55)" }}>{d.reason}</Box>
            <Box sx={{ fontFamily: fonts.mono, fontSize: 11.5, color: "rgba(255,255,255,0.45)", textAlign: "right" }}>risk {d.score.toFixed(2)}</Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

function FakeInput({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <Box sx={{ mb: 1.5 }}>
      <Box sx={{ fontSize: 11.5, color: brand.muted, mb: 0.5, fontWeight: 500 }}>{label}</Box>
      <Box sx={{ border: `1px solid ${brand.line}`, borderRadius: 2, px: 1.5, py: 1, fontSize: 14, fontFamily: mono ? fonts.mono : undefined, bgcolor: "#FCFBF9" }}>
        {value}
      </Box>
    </Box>
  );
}
