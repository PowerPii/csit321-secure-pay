import { Box, Typography } from "@mui/material";
import { brand } from "../theme";

type Shot = { src: string; alt: string; w: number; h: number };

/** A real screenshot in a plain browser frame, with an optional caption underneath. */
export function Screenshot({ shot, caption, url, dark }: { shot: Shot; caption?: string; url?: string; dark?: boolean }) {
  return (
    <Box component="figure" sx={{ m: 0 }}>
      <Box
        sx={{
          borderRadius: 3,
          overflow: "hidden",
          border: `1px solid ${dark ? "rgba(255,255,255,0.16)" : brand.line}`,
          bgcolor: "#fff",
          boxShadow: dark ? "0 40px 80px -30px rgba(0,0,0,0.6)" : "0 24px 48px -28px rgba(15,34,64,0.35)",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, px: 1.5, py: 1, bgcolor: "#EEF0F3", borderBottom: "1px solid #DDE1E6" }}>
          {["#E5E7EB", "#E5E7EB", "#E5E7EB"].map((c, i) => (
            <Box key={i} sx={{ width: 9, height: 9, borderRadius: "50%", bgcolor: c, border: "1px solid #CBD0D6" }} />
          ))}
          {url && (
            <Typography sx={{ ml: 1, fontSize: 11.5, color: "#6B7280", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{url}</Typography>
          )}
        </Box>
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
        <Typography component="figcaption" sx={{ mt: 1.25, fontSize: 14, color: dark ? "rgba(255,255,255,0.65)" : "text.secondary", lineHeight: 1.5 }}>
          {caption}
        </Typography>
      )}
    </Box>
  );
}
