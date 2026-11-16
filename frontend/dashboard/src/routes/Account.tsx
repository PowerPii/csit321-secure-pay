// Signed-out account pages: D7 business registration and its email verification, and the
// forgot / reset password pages (FR-ACC-07 to FR-ACC-09, FR-MER-01).
// Emailed links carry their token in the URL fragment (#token=...), which browsers never send
// to a server; the page reads it once and removes it from the address bar.
import {
  Alert, Box, Button, Checkbox, FormControlLabel, Link as MuiLink, Stack, TextField, Typography,
} from "@mui/material";
import { useEffect, useState, type FormEvent } from "react";
import { Link as RouterLink } from "react-router-dom";
import { ApiError, post } from "../api/client";
import { Card, CodeInput, message } from "./SignIn";

/** The link's token, read once; the fragment is then removed from the address bar. */
function useLinkToken(): string {
  // The initialiser has no side effects: React may call it twice in development.
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "");
  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
    }
  }, []);
  return token;
}

function SignInLink({ text = "Back to sign in" }: { text?: string }) {
  return <MuiLink component={RouterLink} to="/login" variant="body2">{text}</MuiLink>;
}

function fieldError(error: unknown, field: string): string | undefined {
  return error instanceof ApiError && error.body?.error?.param === field ? error.message : undefined;
}

// --- D7 Register your business -------------------------------------------------------------

const STEPS = [
  "Verify your email from the link we send",
  "An administrator reviews the registration",
  "Once approved, sign in and generate API keys",
];

function WhatHappensNext({ children }: { children?: React.ReactNode }) {
  return (
    <Box>
      <Typography variant="overline" color="text.secondary">What happens next</Typography>
      <Box component="ol" sx={{ pl: 2.5, mt: 0.5, mb: 2 }}>
        {STEPS.map((s) => <Typography component="li" variant="body2" key={s} sx={{ mb: 0.5 }}>{s}</Typography>)}
      </Box>
      {children}
    </Box>
  );
}

export function Register() {
  const [form, setForm] = useState({
    business_name: "", registration_number: "", website: "", contact_name: "", email: "", password: "",
  });
  const [confirmPassword, setConfirmPassword] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [sent, setSent] = useState("");
  const [busy, setBusy] = useState(false);
  const mismatch = confirmPassword !== "" && confirmPassword !== form.password;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setError(null);
    try {
      const reply = await post<{ message: string }>("/register", { ...form, confirmed });
      setSent(reply.message);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const field = (name: keyof typeof form, label: string, extra: Record<string, unknown> = {}) => (
    <TextField
      label={label} value={form[name]} required fullWidth
      onChange={(e) => setForm({ ...form, [name]: e.target.value })}
      error={!!fieldError(error, name)} helperText={fieldError(error, name)} {...extra}
    />
  );
  const general = !!error && !(error instanceof ApiError && error.body?.error?.param && error.body.error.param !== "confirmed");

  return (
    <Card maxWidth={900}>
      <Box sx={{ display: "grid", gap: 4, gridTemplateColumns: { xs: "1fr", md: "3fr 2fr" } }}>
        <Box>
          <Typography variant="h6" fontWeight={700}>SecurePay</Typography>
          <Typography variant="h5" component="h1" mt={2}>Register your business</Typography>
          <Typography color="text.secondary" variant="body2" mt={0.5} mb={3}>
            Create a merchant account to accept test payments.
          </Typography>
          {sent ? (
            <Stack gap={2}>
              <Alert severity="success" role="status">{sent}</Alert>
              <Typography variant="body2" color="text.secondary">
                No email? Check the spam folder. The link works once; if it expires, register again.
              </Typography>
              <SignInLink />
            </Stack>
          ) : (
            <Box component="form" onSubmit={submit} noValidate>
              <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
                {field("business_name", "Business name", { autoFocus: true, autoComplete: "organization" })}
                {field("registration_number", "Registration number (UEN)", { placeholder: "202612345K" })}
                {field("website", "Website", { placeholder: "https://", autoComplete: "url" })}
                {field("contact_name", "Contact name", { autoComplete: "name" })}
                <Box sx={{ gridColumn: { sm: "1 / -1" } }}>
                  {field("email", "Contact email", { type: "email", autoComplete: "email" })}
                </Box>
                {field("password", "Password", { type: "password", autoComplete: "new-password",
                  helperText: fieldError(error, "password") ?? "At least 12 characters" })}
                <TextField label="Confirm password" type="password" autoComplete="new-password" required fullWidth
                  value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                  error={mismatch} helperText={mismatch ? "The passwords do not match." : undefined} />
              </Box>
              <FormControlLabel sx={{ mt: 1 }}
                control={<Checkbox checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />}
                label={<Typography variant="body2">I confirm the business details are correct</Typography>} />
              {fieldError(error, "confirmed") && <Alert severity="error">{fieldError(error, "confirmed")}</Alert>}
              <Button type="submit" variant="contained" size="large" fullWidth sx={{ mt: 1 }}
                disabled={busy || !confirmed || mismatch || !confirmPassword}>
                Register business
              </Button>
              {general && <Alert severity="error" role="alert" sx={{ mt: 2 }}>{message(error)}</Alert>}
              <Typography variant="body2" textAlign="center" mt={2}>
                Already registered? <SignInLink text="Sign in" />
              </Typography>
            </Box>
          )}
        </Box>
        <Box sx={{ borderLeft: { md: 1 }, borderColor: { md: "divider" }, pl: { md: 4 } }}>
          <WhatHappensNext />
        </Box>
      </Box>
    </Card>
  );
}

interface Verified { merchant: { id: string; name: string; status: string }; email: string }

// A verification link works once, so the request is sent once per page load even if React
// runs the effect twice (development StrictMode).
const verifying = new Map<string, Promise<Verified>>();
function verifyOnce(token: string): Promise<Verified> {
  if (!verifying.has(token)) verifying.set(token, post<Verified>("/register/verify", { token }));
  return verifying.get(token)!;
}

export function VerifyEmail() {
  const token = useLinkToken();
  const [state, setState] = useState<{ done?: Verified; error?: unknown }>({});

  useEffect(() => {
    if (!token) {
      setState({ error: new Error("missing") });
      return;
    }
    verifyOnce(token).then((done) => setState({ done }), (error) => setState({ error }));
  }, [token]);

  return (
    <Card maxWidth={520}>
      <Typography variant="h6" fontWeight={700}>SecurePay</Typography>
      {state.done ? (
        <>
          <Typography variant="h5" component="h1" mt={2}>Registration received</Typography>
          <Typography variant="body2" mt={1}>
            Your email is verified. An administrator will review {state.done.merchant.name}. You can sign in, but no
            API key is issued until approval. We will email {state.done.email} when it is decided.
          </Typography>
          <Box mt={3}><WhatHappensNext /></Box>
          <Button component={RouterLink} to="/login" variant="contained" fullWidth>Sign in</Button>
        </>
      ) : state.error ? (
        <>
          <Typography variant="h5" component="h1" mt={2}>Link not valid</Typography>
          <Alert severity="error" sx={{ my: 2 }}>
            {state.error instanceof ApiError ? state.error.message : "This link is incomplete. Open it from the email again."}
          </Alert>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Verification links work once, for 24 hours. If yours has expired, register again.
          </Typography>
          <Stack direction="row" gap={2}>
            <MuiLink component={RouterLink} to="/register" variant="body2">Register again</MuiLink>
            <SignInLink />
          </Stack>
        </>
      ) : (
        <Typography mt={2}>Checking your link…</Typography>
      )}
    </Card>
  );
}

// --- Forgot / reset password ---------------------------------------------------------------

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setSent((await post<{ message: string }>("/auth/password-reset", { email })).message);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <Typography variant="h6" fontWeight={700}>SecurePay</Typography>
      <Typography variant="h5" component="h1" mt={2}>Reset your password</Typography>
      {sent ? (
        <Stack gap={2} mt={2}>
          <Alert severity="success" role="status">{sent}</Alert>
          <SignInLink />
        </Stack>
      ) : (
        <Box component="form" onSubmit={submit} noValidate>
          <Typography color="text.secondary" variant="body2" mt={1} mb={3}>
            Enter the email address of your dashboard account and we will send you a link to choose a new password.
          </Typography>
          <Stack gap={2}>
            <TextField label="Email" type="email" autoComplete="username" value={email} required autoFocus
              onChange={(e) => setEmail(e.target.value)} />
            <Button type="submit" variant="contained" size="large" disabled={busy || !email.includes("@")}>
              Send reset link
            </Button>
            {error ? <Alert severity="error" role="alert">{message(error)}</Alert> : null}
            <SignInLink />
          </Stack>
        </Box>
      )}
    </Card>
  );
}

export function ResetPassword() {
  const token = useLinkToken();
  const [link, setLink] = useState<{ email: string; mfa_required: boolean } | null>(null);
  const [linkError, setLinkError] = useState<unknown>(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const mismatch = confirm !== "" && confirm !== password;

  useEffect(() => {
    if (!token) {
      setLinkError(new Error("missing"));
      return;
    }
    post<{ email: string; mfa_required: boolean }>("/auth/password-reset/check", { token })
      .then(setLink, setLinkError);
  }, [token]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/auth/password-reset/confirm", { token, password, code: link?.mfa_required ? code : undefined });
      setDone(true);
    } catch (err) {
      setError(err);
      setCode("");
      if (err instanceof ApiError && (err.code === "link_invalid" || err.code === "account_locked")) setLinkError(err);
    } finally {
      setBusy(false);
    }
  };

  let body: React.ReactNode;
  if (done) {
    body = (
      <Stack gap={2} mt={2}>
        <Alert severity="success" role="status">
          Your password has been changed and every signed-in session has ended. Sign in with the new password.
        </Alert>
        <Button component={RouterLink} to="/login" variant="contained">Sign in</Button>
      </Stack>
    );
  } else if (linkError) {
    body = (
      <Stack gap={2} mt={2}>
        <Alert severity="error">
          {linkError instanceof ApiError ? linkError.message : "This link is incomplete. Open it from the email again."}
        </Alert>
        <MuiLink component={RouterLink} to="/forgot-password" variant="body2">Ask for a new link</MuiLink>
        <SignInLink />
      </Stack>
    );
  } else if (!link) {
    body = <Typography mt={2}>Checking your link…</Typography>;
  } else {
    body = (
      <Box component="form" onSubmit={submit} noValidate>
        <Typography color="text.secondary" variant="body2" mt={1} mb={3}>
          Choose a new password for {link.email}. Every signed-in session will end.
        </Typography>
        <Stack gap={2}>
          <TextField label="New password" type="password" autoComplete="new-password" value={password} required autoFocus
            onChange={(e) => setPassword(e.target.value)}
            error={!!fieldError(error, "password")} helperText={fieldError(error, "password") ?? "At least 12 characters"} />
          <TextField label="Confirm new password" type="password" autoComplete="new-password" value={confirm} required
            onChange={(e) => setConfirm(e.target.value)}
            error={mismatch} helperText={mismatch ? "The passwords do not match." : undefined} />
          {link.mfa_required && (
            <Box>
              <Typography variant="body2" textAlign="center">Confirm with the 6-digit code from your authenticator app</Typography>
              <CodeInput value={code} onChange={setCode} autoFocus={false} />
            </Box>
          )}
          <Button type="submit" variant="contained" size="large"
            disabled={busy || !password || mismatch || !confirm || (link.mfa_required && code.length !== 6)}>
            Change password
          </Button>
          {error && !fieldError(error, "password") ? <Alert severity="error" role="alert">{message(error)}</Alert> : null}
        </Stack>
      </Box>
    );
  }

  return (
    <Card>
      <Typography variant="h6" fontWeight={700}>SecurePay</Typography>
      <Typography variant="h5" component="h1" mt={2}>Choose a new password</Typography>
      {body}
    </Card>
  );
}
