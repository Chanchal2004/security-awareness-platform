
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Shield, CheckCircle2, Flag } from "lucide-react";
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
    let active = true;

    api
      .get(`/public/landing/${token}`)
      .then((r) => {
        if (active) setData(r.data);
      })
      .catch((e) => {
        if (active) setError(apiError(e));
      });

    return () => {
      active = false;
    };
  }, [token]);

  const onFocus = () => {
    if (!started) {
      setStarted(true);
      api.post(`/public/form-start/${token}`).catch(() => {});
    }
  };

  const handleChange = (label, value) => {
    setResponses((previous) => ({
      ...previous,
      [label]: value,
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");

    try {
      await api.post(`/public/form-submit/${token}`, { responses });
      setSubmitted(true);
    } catch (err) {
      setError(apiError(err));
    }
  };

  if (error && !data) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <Shield className="mx-auto mb-4 h-10 w-10 text-slate-400" />
          <h2 className="text-xl font-bold text-slate-900">
            Page unavailable
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            This link may be invalid or expired.
          </p>
        </section>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50">
        <Loading />
      </main>
    );
  }

  if (submitted) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
        <section className="w-full max-w-xl rounded-2xl border border-emerald-200 bg-white p-8 shadow-sm">
          <div className="flex items-start gap-4">
            <CheckCircle2 className="mt-1 h-6 w-6 shrink-0 text-emerald-600" />
            <div>
              <h2 className="text-xl font-bold text-slate-900">
                Thank you!
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Your acknowledgement was recorded.
              </p>
            </div>
          </div>
        </section>
      </main>
    );
  }

  const lp = data.landing_page;

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10 text-slate-900 sm:px-6">
      <div className="mx-auto w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg shadow-slate-200/50">
        <div className="h-1.5 w-full bg-indigo-600" />

        <div className="p-6 sm:p-10">
          <header className="mb-8">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              Employee Details
            </h1>

            <p className="mt-2 text-sm leading-6 text-slate-600">
              Fill in the details below.
            </p>

            <p className="mt-3 text-xs leading-5 text-slate-500">
              Authorized internal security-awareness exercise.
            </p>
          </header>

          {lp?.indicators && (
            <section className="mb-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Shield className="h-4 w-4 text-indigo-600" />
                How to spot a suspicious email
              </div>
              <p className="text-sm leading-6 text-slate-600">
                {lp.indicators}
              </p>
            </section>
          )}

          {lp?.reporting_instructions && (
            <section className="mb-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Flag className="h-4 w-4 text-indigo-600" />
                Reporting
              </div>
              <p className="text-sm leading-6 text-slate-600">
                {lp.reporting_instructions}
              </p>
            </section>
          )}

          {data.form_enabled && (
            <form
              onSubmit={submit}
              onFocus={onFocus}
              className="space-y-5 pt-2"
              data-testid="awareness-form"
            >
              {data.form.fields.map((f) => (
                <div key={f.id}>
                  <label
                    htmlFor={`field-${f.id}`}
                    className="block text-sm font-medium text-slate-700"
                  >
                    {f.label}
                    {f.required && " *"}
                  </label>

                  {f.type === "textarea" ? (
                    <textarea
                      id={`field-${f.id}`}
                      required={f.required}
                      value={responses[f.label] || ""}
                      onChange={(e) =>
                        handleChange(f.label, e.target.value)
                      }
                      className="mt-2 min-h-[100px] w-full rounded-lg border border-slate-300 bg-white p-3 text-sm outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                    />
                  ) : f.type === "yes_no" ? (
                    <select
                      id={`field-${f.id}`}
                      required={f.required}
                      value={responses[f.label] || ""}
                      onChange={(e) =>
                        handleChange(f.label, e.target.value)
                      }
                      className="mt-2 h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                    >
                      <option value="">Select an option</option>
                      <option value="Yes">Yes</option>
                      <option value="No">No</option>
                    </select>
                  ) : (
                    <input
                      id={`field-${f.id}`}
                      required={f.required}
                      type={f.type === "email" ? "email" : "text"}
                      value={responses[f.label] || ""}
                      onChange={(e) =>
                        handleChange(f.label, e.target.value)
                      }
                      className="mt-2 h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none transition placeholder:text-slate-400 focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                    />
                  )}
                </div>
              ))}

              {error && (
                <p role="alert" className="text-sm text-red-600">
                  {error}
                </p>
              )}

              <button
                type="submit"
                data-testid="awareness-form-submit"
                className="inline-flex h-11 items-center justify-center rounded-lg bg-indigo-600 px-6 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus:ring-4 focus:ring-indigo-200"
              >
                Submit
              </button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
