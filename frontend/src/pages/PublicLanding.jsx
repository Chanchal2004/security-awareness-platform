import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Shield, AlertTriangle, CheckCircle2, Flag } from "lucide-react";
import { api, apiError } from "../lib/api";
import { Loading } from "../components/common";

export default function PublicLanding() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [responses, setResponses] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [started, setStarted] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/public/landing/${token}`).then((r) => setData(r.data)).catch((e) => setError(apiError(e)));
  }, [token]);

  const onFocus = () => {
    if (!started) {
      setStarted(true);
      api.post(`/public/form-start/${token}`).catch(() => {});
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/public/form-submit/${token}`, { responses });
      setSubmitted(true);
    } catch (err) {
      setError(apiError(err));
    }
  };

  if (error) return <div className="min-h-screen flex items-center justify-center text-muted-foreground">Link not found or expired.</div>;
  if (!data) return <div className="min-h-screen dark bg-background"><Loading /></div>;

  const lp = data.landing_page;
  return (
    <div className="min-h-screen dark bg-background text-foreground flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-card border border-border rounded-xl p-6 sm:p-10">
        <div className="flex items-center gap-3 mb-6">
          <div className="h-11 w-11 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-center justify-center">
            <AlertTriangle className="h-6 w-6 text-amber-400" />
          </div>
          <div>
            <div className="font-head font-bold text-lg tracking-tight">{lp?.title || "TALBROS SECURITY AWARENESS CHECK"}</div>
            <div className="text-xs text-muted-foreground">Talbros Security Awareness Center</div>
          </div>
        </div>

        <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-4 mb-6">
          <p className="text-sm text-amber-200">{lp?.message || "This was a simulated phishing awareness exercise. No harm was done."}</p>
        </div>

        {lp?.indicators && (
          <div className="mb-5">
            <div className="flex items-center gap-2 text-sm font-semibold mb-1"><Shield className="h-4 w-4 text-primary" />How to spot a suspicious email</div>
            <p className="text-sm text-muted-foreground">{lp.indicators}</p>
          </div>
        )}
        {lp?.reporting_instructions && (
          <div className="mb-6">
            <div className="flex items-center gap-2 text-sm font-semibold mb-1"><Flag className="h-4 w-4 text-cyan-400" />Reporting</div>
            <p className="text-sm text-muted-foreground">{lp.reporting_instructions}</p>
          </div>
        )}

        {data.form_enabled && !submitted && (
          <form onSubmit={submit} className="border-t border-border pt-6 space-y-4" data-testid="awareness-form">
            <div className="text-sm font-semibold">{data.form.name}</div>
            {data.form.fields.map((f) => (
              <div key={f.id}>
                <label className="text-xs font-semibold text-muted-foreground">{f.label}{f.required && " *"}</label>
                {f.type === "textarea" ? (
                  <textarea onFocus={onFocus} required={f.required} value={responses[f.label] || ""}
                    onChange={(e) => setResponses({ ...responses, [f.label]: e.target.value })}
                    className="mt-1 w-full min-h-[80px] p-2.5 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60" />
                ) : (
                  <input onFocus={onFocus} required={f.required} type={f.type === "email" ? "email" : "text"} value={responses[f.label] || ""}
                    onChange={(e) => setResponses({ ...responses, [f.label]: e.target.value })}
                    className="mt-1 w-full h-10 px-3 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60" />
                )}
              </div>
            ))}
            <button data-testid="awareness-form-submit" type="submit" className="h-10 px-5 rounded-md bg-primary text-primary-foreground text-sm font-semibold">Submit</button>
          </form>
        )}

        {submitted && (
          <div className="border-t border-border pt-6 flex items-center gap-2 text-emerald-400" data-testid="form-submitted-confirm">
            <CheckCircle2 className="h-5 w-5" /> Thank you — your acknowledgement was recorded.
          </div>
        )}
      </div>
    </div>
  );
}
