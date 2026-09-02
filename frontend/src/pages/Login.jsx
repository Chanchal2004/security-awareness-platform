import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Shield, Loader2, Lock } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("jbenterpriises01@gmail.com");
  const [password, setPassword] = useState("Talbros@2026");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    const res = await login(email, password);
    setLoading(false);
    if (res.ok) navigate("/", { replace: true });
    else setError(res.error);
  };

  return (
    <div className="min-h-screen dark bg-background text-foreground flex items-center justify-center p-4 relative overflow-hidden">
      <div className="absolute inset-0 opacity-30" style={{
        background: "radial-gradient(circle at 20% 20%, rgba(99,102,241,0.25), transparent 40%), radial-gradient(circle at 80% 60%, rgba(6,182,212,0.18), transparent 45%)",
      }} />
      <div className="relative w-full max-w-md">
        <div className="flex items-center gap-3 justify-center mb-8">
          <div className="h-12 w-12 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center">
            <Shield className="h-6 w-6 text-primary" />
          </div>
          <div className="text-left">
            <div className="font-head font-extrabold text-lg tracking-tight">TALBROS</div>
            <div className="text-[11px] text-muted-foreground uppercase tracking-widest">Security Awareness Center</div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-xl p-6 sm:p-8 shadow-2xl">
          <h1 className="font-head text-xl font-bold tracking-tight mb-1">Administrator Sign-in</h1>
          <p className="text-sm text-muted-foreground mb-6">Employee Phishing Awareness & Security Simulation Platform</p>

          <form onSubmit={submit} className="space-y-4" autoComplete="off">
            <div>
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Email</label>
              <input
                data-testid="login-email-input"
                type="email"
                autoComplete="off"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="mt-1.5 w-full h-11 px-3 rounded-md bg-background border border-border outline-none focus:border-primary/60 text-sm"
                placeholder="you@talbros.test"
              />
            </div>
            <div>
              <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Password</label>
              <input
                data-testid="login-password-input"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="mt-1.5 w-full h-11 px-3 rounded-md bg-background border border-border outline-none focus:border-primary/60 text-sm"
                placeholder="••••••••"
              />
            </div>
            {error && (
              <div data-testid="login-error" className="text-sm text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-md px-3 py-2">
                {error}
              </div>
            )}
            <button
              data-testid="login-submit-button"
              type="submit"
              disabled={loading}
              className="w-full h-11 rounded-md bg-primary text-primary-foreground font-semibold text-sm flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-60"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lock className="h-4 w-4" />}
              Sign in
            </button>
          </form>

          <div className="mt-5 rounded-md bg-muted/50 border border-border p-3 text-xs">
            <div className="flex items-center justify-between gap-2">
              <div className="text-muted-foreground">
                <div>Admin email: <span className="font-mono-t text-foreground">jbenterpriises01@gmail.com</span></div>
                <div>Password: <span className="font-mono-t text-foreground">Talbros@2026</span></div>
              </div>
              <button
                type="button"
                data-testid="fill-credentials-btn"
                onClick={() => { setEmail("jbenterpriises01@gmail.com"); setPassword("Talbros@2026"); setError(""); }}
                className="shrink-0 h-8 px-3 rounded-md border border-primary/40 bg-primary/10 text-primary font-medium"
              >
                Fill
              </button>
            </div>
            <p className="text-muted-foreground mt-2">If sign-in fails, click <strong>Fill</strong> (your browser may have autofilled an old password), then Sign in.</p>
          </div>
        </div>
        <p className="text-center text-xs text-muted-foreground mt-6">
          Authorized use only. All access is logged.
        </p>
      </div>
    </div>
  );
}
