/** The securepay. wordmark and the test-mode pill shown in the top bar of every customer page
 * (Slate rebrand: a lowercase name with a brass full stop, no separate symbol). */
export function Wordmark() {
  return (
    <span className="wordmark">
      <span>securepay</span>
      <span className="wordmark-dot">.</span>
    </span>
  );
}

export function Brand() {
  return (
    <span className="brand">
      <Wordmark />
      <span className="testmode" title="Simulated payments: no real money moves">Test mode</span>
    </span>
  );
}
