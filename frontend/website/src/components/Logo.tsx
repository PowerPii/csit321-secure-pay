import { Box } from "@mui/material";
import { brand, fonts } from "../theme";

/** The logo is the wordmark: lowercase "securepay" with a brass full stop. */
export function Logo({ light = false, size = 22 }: { light?: boolean; size?: number }) {
  return (
    <Box
      component="span"
      sx={{
        fontFamily: fonts.heading,
        fontWeight: 600,
        fontSize: size,
        letterSpacing: "-0.045em",
        lineHeight: 1,
        color: light ? "#EEF1F6" : brand.navy,
        whiteSpace: "nowrap",
      }}
    >
      <span>securepay</span>
      <Box component="span" sx={{ color: light ? brand.brassLight : brand.brass }}>
        .
      </Box>
    </Box>
  );
}
