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
    api.get(`/public/landing/${token}`)
      .then((r) => setData(r.data))
      .catch((e) => setError(apiError(e)));
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

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <Shield className="mx-auto mb-3 h-10 w-10 text-slate-400" />
          <h2 className="text-lg font-semibold text-slate-900">Page unavailable</h2>
          <p className="mt-2 text-sm text-slate-600">This link may be invalid or expired.</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <Loading />
      </div>
    );
  }

  // On submit, show only the concise acknowledgment—no awareness title, banner, or footer.
  if (submitted) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4 py-10">
        <div className="w-full max-w-xl rounded-2xl border border-emerald-200 bg-emerald-50 p-6 sm:p-8 text-emerald-800">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <p className="font-semibold">Thank you!</p>
              <p className="mt-1 text-sm">Your acknowledgement was recorded.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const lp = data.landing_page;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex items-center justify-center px-4 py-10 sm:px-6">
      <div className="w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60">
        <div className="h-1.5 w-full bg-indigo-600" />
        <div className="p-6 sm:p-10">
          <div className="mb-7 flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-amber-200 bg-amber-50">
              <AlertTriangle className="h-6 w-6 text-amber-600" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-slate-900 sm:text-xl">
                {lp?.title || "TALBROS SECURITY AWARENESS CHECK"}
              </h1>
              <p className="mt-1 text-sm text-slate-500">Talbros Security Awareness Center</p>
            </div>
          </div>

          <div className="mb-7 rounded-xl border border-amber-200 bg-amber-50 p-4">
            <div className="flex items-start gap-3">
              <Shield className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
              <p className="text-sm leading-6 text-amber-950">
                {lp?.message || "This was a simulated phishing awareness exercise. No harm was done."}
              </p>
            </div>
          </div>

          {lp?.indicators && (
            <div className="mb-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Shield className="h-4 w-4 text-indigo-600" />How to spot a suspicious email
              </div>
              <p className="text-sm leading-6 text-slate-600">{lp.indicators}</p>
            </div>
          )}

          {lp?.reporting_instructions && (
            <div className="mb-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Flag className="h-4 w-4 text-indigo-600" />Reporting
              </div>
              <p className="text-sm leading-6 text-slate-600">{lp.reporting_instructions}</p>
            </div>
          )}

          {data.form_enabled && (
            <form onSubmit={submit} className="space-y-5 border-t border-slate-200 pt-7" data-testid="awareness-form">
              <div>
                <h2 className="text-base font-semibold text-slate-900">{data.form.name}</h2>
                <p className="mt-1 text-sm text-slate-500">Please complete the fields below.</p>
              </div>

              {data.form.fields.map((f) => (
                <div key={f.id}>
                  <label className="text-sm font-medium text-slate-700">
                    {f.label}{f.required && " *"}
                  </label>
                  {f.type === "textarea" ? (
                    <textarea
                      onFocus={onFocus}
                      required={f.required}
                      value={responses[f.label] || ""}
                      onChange={(e) => setResponses({ ...responses, [f.label]: e.target.value })}
                      className="mt-2 w-full min-h-[100px] rounded-lg border border-slate-300 bg-white p-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                    />
                  ) : f.type === "yes_no" ? (
                    <select
                      onFocus={onFocus}
                      required={f.required}
                      value={responses[f.label] || ""}
                      onChange={(e) => setResponses({ ...responses, [f.label]: e.target.value })}
                      className="mt-2 h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                    >
                      <option value="">Select an option</option>
                      <option value="Yes">Yes</option>
                      <option value="No">No</option>
                    </select>
                  ) : (
                    <input
                      onFocus={onFocus}
                      required={f.required}
                      type={f.type === "email" ? "email" : "text"}
                      value={responses[f.label] || ""}
                      onChange={(e) => setResponses({ ...responses, [f.label]: e.target.value })}
                      className="mt-2 h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                    />
                  )}
                </div>
              ))}

              <button data-testid="awareness-form-submit" type="submit" className="inline-flex h-11 items-center justify-center rounded-lg bg-indigo-600 px-6 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus:ring-4 focus:ring-indigo-200">
                Submit
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
