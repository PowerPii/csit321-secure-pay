import { Box, Typography } from "@mui/material";
import { brand, shadows } from "../theme";

type Shot = { src: string; alt: string; w: number; h: number };

/** A real screenshot on a soft raised card (no fake browser frame), with an optional caption underneath. */
export function Screenshot({ shot, caption, dark }: { shot: Shot; caption?: string; dark?: boolean }) {
  return (
    <Box component="figure" sx={{ m: 0 }}>
      <Box
        sx={{
          borderRadius: "14px",
          overflow: "hidden",
          border: `1px solid ${dark ? "rgba(255,255,255,0.12)" : brand.line}`,
          bgcolor: "#fff",
          boxShadow: dark ? "0 32px 64px -32px rgba(0,0,0,0.55)" : shadows.float,
        }}
      >
        <Box
          component="img"
          src={shot.src}
          alt={shot.alt}
          width={shot.w}
          height={shot.h}
          loading="lazy"
          decoding="async"
          sx={{ display: "block", width: "100%", height: "auto", aspectRatio: `${shot.w} / ${shot.h}` }}
        />
      </Box>
      {caption && (
        <Typography component="figcaption" sx={{ mt: 1.5, fontSize: 14, color: dark ? "rgba(255,255,255,0.65)" : "text.secondary", lineHeight: 1.5 }}>
          {caption}
        </Typography>
      )}
    </Box>
  );
}
