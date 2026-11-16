import { Field } from "../ui";
import { AccountApiError } from "../accountApi";

export const MIN_PASSWORD = 12;
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Local checks for a new password and its confirmation, keyed by field name. */
export function newPasswordProblems(value: string, repeat: string): Record<string, string> {
  if (value.length < MIN_PASSWORD) return { password: tooShort() };
  return repeat === value ? {} : { confirm: "The passwords do not match." };
}

const tooShort = () => `Use at least ${MIN_PASSWORD} characters.`;

export const asError = (err: unknown) =>
  err instanceof AccountApiError ? err : new AccountApiError(0, "unknown_error", "Something went wrong.", null, null);

export function NewPasswordFields({ password, confirm, errors, onPassword, onConfirm }: {
  password: string; confirm: string; errors: Record<string, string>;
  onPassword: (v: string) => void; onConfirm: (v: string) => void;
}) {
  return (
    <>
      <Field label="New password" error={errors.password} id="pw-new">
        <input id="pw-new" type="password" autoComplete="new-password" value={password} onChange={(e) => onPassword(e.target.value)} />
      </Field>
      <Field label="Confirm new password" error={errors.confirm} id="pw-confirm">
        <input id="pw-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => onConfirm(e.target.value)} />
      </Field>
      <p className="muted tiny">At least {MIN_PASSWORD} characters. Saving signs you out on every other device.</p>
    </>
  );
}
