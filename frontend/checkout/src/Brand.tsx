/** The SecurePay mark, name and test-mode pill shown in the top bar of every customer page. */
export function BrandMark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <rect width="64" height="64" rx="14" fill="#0F2240" />
      <path d="M32 12 48 18v12c0 11-7 19-16 22-9-3-16-11-16-22V18z" fill="none" stroke="#F5A524" strokeWidth="4" strokeLinejoin="round" />
      <path d="m25 32 5 5 9-10" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Brand() {
  return (
    <span className="brand">
      <BrandMark />
      <span>SecurePay</span>
      <span className="testmode" title="Simulated payments: no real money moves">Test mode</span>
    </span>
  );
}
