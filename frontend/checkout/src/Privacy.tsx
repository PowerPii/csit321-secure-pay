// The privacy notice (FR-ACC-12), shown before any personal data is collected: on the card
// form and on the account sign-up form. The version is GATEWAY_RULES["PRIVACY_NOTICE_VERSION"]
// on the gateway, which records it with the consent.
import type { ReactNode } from "react";

export const PRIVACY_NOTICE_VERSION = "2026-11-16";

export function PrivacyNotice() {
  return (
    <details className="privacy">
      <summary>Privacy notice</summary>
      <p>
        SecurePay uses your name, email address, card details, device and network details only to process your
        payments, to screen them for fraud, to send you receipts and codes, and to keep the records that payment
        rules require.
      </p>
      <p>
        Your full card number and security code are encrypted and deleted as soon as the payment no longer needs
        them; we keep only the card brand and last four digits. We do not sell your data or use it for marketing. The shop sees
        your email address and the payment result.
      </p>
      <p>
        With an account you can see and correct your details on the Profile page. Notice version{" "}
        {PRIVACY_NOTICE_VERSION}.
      </p>
    </details>
  );
}

export function ConsentBox({ checked, onChange, error, children }: {
  checked: boolean;
  onChange: (v: boolean) => void;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className={`field${error ? " has-error" : ""}`}>
      <label className="check consent">
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span>{children}</span>
      </label>
      {error && <span className="error" role="alert">{error}</span>}
      <PrivacyNotice />
    </div>
  );
}
