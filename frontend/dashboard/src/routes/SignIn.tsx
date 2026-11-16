// D1 Staff sign-in and D2 Two-step verification (with first-time authenticator setup).
import { Alert, Box, Button, Link as MuiLink, Paper, Stack, TextField, Typography } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link as RouterLink, useLocation, useNavigate } from "react-router-dom";
import { api, ApiError, post, type Staff } from "../api/client";
import { ShieldIcon } from "../components/ui";

interface Setup { secret: string; otpauth_uri: string; qr_svg: string }
interface LoginReply { next: "totp"; email: string; setup: Setup | null }

export function Card({ children, maxWidth = 420 }: { children: React.ReactNode; maxWidth?: number }) {
  return (
    <Stack alignItems="center" justifyContent="center" sx={{ minHeight: "100vh", bgcolor: "background.default", p: 2 }}>
      <Paper sx={{ p: { xs: 3, sm: 4 }, width: "100%", maxWidth, borderRadius: 2 }}>{children}</Paper>
    </Stack>
  );
}

export function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

export function SignIn() {
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Sets the CSRF cookie before the first POST (the 401 is expected).
  useEffect(() => {
    api("/me").then(() => navigate("/payments", { replace: true })).catch(() => undefined);
  }, [navigate]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const reply = await post<LoginReply>("/auth/login", { email, password });
      navigate("/login/totp", { state: { email: reply.email, setup: reply.setup, from: location.state?.from } });
    } catch (err) {
      setError(message(err));
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <Typography variant="h6" fontWeight={700}>SecurePay</Typography>
      <Typography variant="h5" component="h1" mt={2}>Sign in to the dashboard</Typography>
      <Typography color="text.secondary" variant="body2" mt={1} mb={3}>
        For merchant operators, administrators and fraud analysts.
      </Typography>
      <Box component="form" onSubmit={submit} noValidate>
        <Stack gap={2}>
          <TextField label="Email" type="email" autoComplete="username" value={email} required
            onChange={(e) => setEmail(e.target.value)} autoFocus size="medium" />
          <TextField label="Password" type="password" autoComplete="current-password" value={password} required
            onChange={(e) => setPassword(e.target.value)} size="medium" />
          <Button type="submit" variant="contained" size="large" disabled={busy || !email || !password}>
            Sign in
          </Button>
          {error && <Alert severity="error" role="alert">{error}</Alert>}
          <MuiLink component={RouterLink} to="/forgot-password" variant="body2">Forgot your password?</MuiLink>
          <Typography variant="caption" color="text.secondary">
            After 5 failed attempts the account is locked for 15 minutes.
          </Typography>
          <Typography variant="body2" color="text.secondary" textAlign="center">
            New merchant? <MuiLink component={RouterLink} to="/register">Register your business</MuiLink>
          </Typography>
        </Stack>
      </Box>
    </Card>
  );
}

/** Six boxes that behave like one input (paste fills all of them). */
export function CodeInput({ value, onChange, autoFocus = true }: { value: string; onChange: (v: string) => void; autoFocus?: boolean }) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const set = (i: number, text: string) => {
    const digits = text.replace(/\D/g, "");
    if (digits.length > 1) {
      onChange(digits.slice(0, 6));
      refs.current[Math.min(digits.length, 5)]?.focus();
      return;
    }
    const chars = value.padEnd(6, " ").split("");
    chars[i] = digits || " ";
    onChange(chars.join("").trimEnd());
    if (digits && i < 5) refs.current[i + 1]?.focus();
  };
  return (
    <Stack direction="row" gap={1} justifyContent="center" my={2}>
      {Array.from({ length: 6 }, (_, i) => (
        <Box
          key={i}
          component="input"
          ref={(el: HTMLInputElement | null) => { refs.current[i] = el; }}
          inputMode="numeric"
          autoComplete={i === 0 ? "one-time-code" : "off"}
          aria-label={`Digit ${i + 1}`}
          value={value[i]?.trim() ?? ""}
          autoFocus={autoFocus && i === 0}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => set(i, e.target.value)}
          onKeyDown={(e: React.KeyboardEvent<HTMLInputElement>) => {
            if (e.key === "Backspace" && !value[i]?.trim() && i > 0) refs.current[i - 1]?.focus();
          }}
          sx={{
            width: 46, height: 54, textAlign: "center", fontSize: 22, border: "1px solid #8a8a8a",
            borderRadius: 1.5, outlineColor: "#333",
          }}
        />
      ))}
    </Stack>
  );
}

export function Totp() {
  const navigate = useNavigate();
  const location = useLocation();
  const client = useQueryClient();
  const state = (location.state ?? {}) as { email?: string; setup?: Setup | null; from?: string };
  const [email, setEmail] = useState(state.email ?? "");
  const [setup] = useState<Setup | null>(state.setup ?? null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!state.email) {
      api<{ email: string }>("/auth/totp")
        .then((r) => setEmail(r.email))
        .catch(() => navigate("/login", { replace: true }));
    }
  }, [state.email, navigate]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const staff = await post<Staff>("/auth/totp", { code });
      client.setQueryData(["me"], staff);
      navigate(state.from && state.from !== "/login" ? state.from : "/payments", { replace: true });
    } catch (err) {
      setError(message(err));
      setCode("");
      if (err instanceof ApiError && (err.code === "account_locked" || err.code === "sign_in_required")) {
        navigate("/login", { replace: true, state: {} });
      }
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    navigate("/login", { replace: true });
  };

  return (
    <Card>
      <Stack alignItems="center" textAlign="center">
        <ShieldIcon />
        <Typography variant="h5" component="h1" mt={1.5}>Two-step verification</Typography>
        {setup ? (
          <>
            <Typography color="text.secondary" variant="body2" mt={1}>
              First sign-in: scan this code with an authenticator app (Google Authenticator, Microsoft
              Authenticator, 1Password...), then enter the 6-digit code it shows.
            </Typography>
            <Box component="img" src={setup.qr_svg} alt="QR code for your authenticator app"
              sx={{ width: 200, height: 200, my: 2 }} />
            <Typography variant="caption" color="text.secondary">Or enter this key by hand:</Typography>
            <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-all" }} data-testid="totp-secret">
              {setup.secret}
            </Typography>
          </>
        ) : (
          <Typography color="text.secondary" variant="body2" mt={1}>
            Enter the 6-digit code from your authenticator app.
          </Typography>
        )}
      </Stack>
      <Box component="form" onSubmit={submit}>
        <CodeInput value={code} onChange={setCode} />
        <Button type="submit" variant="contained" size="large" fullWidth disabled={busy || code.length !== 6}>
          Verify
        </Button>
        {error && <Alert severity="error" role="alert" sx={{ mt: 2 }}>{error}</Alert>}
      </Box>
      <Stack direction="row" justifyContent="flex-end" mt={2}>
        <MuiLink component="button" variant="body2" color="text.secondary" onClick={signOut}>
          Not you? Sign out
        </MuiLink>
      </Stack>
      {email && (
        <Typography variant="body2" color="text.secondary" textAlign="center" mt={1}>
          Signed in as {email}
        </Typography>
      )}
    </Card>
  );
}
