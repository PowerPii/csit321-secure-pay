// The privacy notice (FR-ACC-12), shown before any personal data is collected: on the card
// form and on the account sign-up form. The version is GATEWAY_RULES["PRIVACY_NOTICE_VERSION"]
// on the gateway, which records it with the consent.
import type { ReactNode } from "react";
import { errorId, invalidProps } from "./ui";

export const PRIVACY_NOTICE_VERSION = "2026-11-16";

// The full policy is on the marketing website: www. next to this page's gateway. name.
export function privacyPolicyUrl(hostname = window.location.hostname): string {
  const domain = hostname.startsWith("gateway.") && !hostname.endsWith("localhost") ? hostname.slice("gateway.".length) : "securepaysg.me";
  return `https://www.${domain}/privacy`;
}

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
        With an account you can see and correct your details on the Profile page.{" "}
        <a href={privacyPolicyUrl()} target="_blank" rel="noopener noreferrer">Read the full privacy policy</a>. Notice
        version {PRIVACY_NOTICE_VERSION}.
      </p>
    </details>
  );
}

export function ConsentBox({ id, checked, onChange, error, children }: {
  id: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className={`field${error ? " has-error" : ""}`}>
      <label className="check consent">
        <input type="checkbox" id={id} checked={checked} onChange={(e) => onChange(e.target.checked)}
          {...invalidProps(id, error)} />
        <span>{children}</span>
      </label>
      {error && <span className="error" id={errorId(id)} role="alert">{error}</span>}
      <PrivacyNotice />
    </div>
  );
}
