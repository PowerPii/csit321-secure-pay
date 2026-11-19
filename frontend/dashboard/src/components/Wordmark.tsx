import { Box } from "@mui/material";
import { BRAND } from "../theme";

/** The SecurePay logo: lowercase "securepay" with a brass full stop (frontend/brand/securepay-wordmark.svg). */
export function Wordmark({ size = 21 }: { size?: number }) {
  return (
    <Box component="p" sx={{ m: 0, fontFamily: BRAND.headFont, fontWeight: 600, fontSize: size, letterSpacing: "-0.045em", lineHeight: 1.1, color: BRAND.navy }}>
      <span>securepay</span>
      <Box component="span" aria-hidden="true" sx={{ color: BRAND.brass }}>.</Box>
    </Box>
  );
}
