import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Send, Eye, TestTube2, Save, Rocket, Calendar, ShieldAlert, Mail } from "lucide-react";
import { api, apiError } from "../lib/api";
import { PageHeader } from "../components/common";
import RichEditor from "../components/RichEditor";
import { Switch } from "../components/ui/switch";

const TEMPLATES = [
  { name: "Executive HR Salary Review", subject: "Confidential: Q3 Salary Review Document", body: "<p>Hi,</p><p>The HR team has completed the Q3 salary review. Please review your updated compensation summary using the secure link below before Friday.</p><p>Regards,<br/>Human Resources</p>" },
  { name: "IT Password Reset", subject: "Action Required: Password Expiry Notice", body: "<p>Dear user,</p><p>Your account password will expire in 24 hours. To avoid losing access, please verify and update your credentials via the secure portal below.</p><p>IT Service Desk</p>" },
  { name: "Urgent Cloud Storage Access", subject: "You have 3 documents shared with you", body: "<p>Hello,</p><p>Three files were shared with you on the corporate cloud drive. Access expires soon — open the shared folder using the link below.</p>" },
  { name: "Office 365 Re-authentication", subject: "Your Office 365 session needs re-authentication", body: "<p>Hi,</p><p>We detected a new sign-in to your Office 365 account. Please re-authenticate to keep your mailbox active using the link below.</p>" },
];

const TRACK = [
  { key: "open", label: "Email Open Tracking" },
  { key: "click", label: "Link Click Tracking" },
  { key: "landing", label: "Landing Page Tracking" },
  { key: "form", label: "Form Tracking" },
  { key: "form_submit", label: "Form Submission Tracking" },
];

export default function CreateSimulation() {
  const navigate = useNavigate();
  const [senders, setSenders] = useState([]);
  const [landings, setLandings] = useState([]);
  const [forms, setForms] = useState([]);

  const [emails, setEmails] = useState("");
  const [senderId, setSenderId] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("<p>Compose your awareness email…</p>");
  const [destUrl, setDestUrl] = useState("https://security-awareness-platform-vtor.vercel.app/awareness");
  const [tracking, setTracking] = useState({ open: true, click: true, landing: true, form: true, form_submit: true });
  const [simEnabled, setSimEnabled] = useState(false);
  const [simFrom, setSimFrom] = useState("");
  const [simName, setSimName] = useState("");
  const [landingId, setLandingId] = useState("");
  const [formId, setFormId] = useState("");
  const [mode, setMode] = useState("sandbox");
  const [scheduledAt, setScheduledAt] = useState("");
  const [testEmail, setTestEmail] = useState("");
  const [testStatus, setTestStatus] = useState("");
  const [createdId, setCreatedId] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/senders").then((r) => { setSenders(r.data); const a = r.data.find((s) => s.status === "ACTIVE"); if (a) setSenderId(a.id); });
    api.get("/landing-pages").then((r) => setLandings(r.data));
    api.get("/forms").then((r) => setForms(r.data));
  }, []);

  const payload = () => ({
    recipient_emails: emails.split(/[\n,;]+/).map((e) => e.trim()).filter(Boolean),
    sender_id: senderId || null,
    subject, body_html: body, destination_url: destUrl,
    tracking, sender_sim: { enabled: simEnabled, from_email: simFrom, display_name: simName },
    landing_page_id: landingId || null, form_id: formId || null,
    mode, scheduled_at: scheduledAt || null,
  });

  const ensureCreated = async () => {
    if (createdId) {
      await api.put(`/simulations/${createdId}`, payload());
      return createdId;
    }
    const { data } = await api.post("/simulations", payload());
    setCreatedId(data.id);
    return data.id;
  };

  const doSaveDraft = async () => {
    setBusy(true);
    try { await ensureCreated(); toast.success("Simulation saved"); }
    catch (e) { toast.error(apiError(e)); }
    finally { setBusy(false); }
  };

  const doTest = async () => {
    if (!testEmail) return toast.error("Enter a test recipient email");
    setBusy(true); setTestStatus("QUEUED");
    try {
      const id = await ensureCreated();
      const { data } = await api.post(`/simulations/${id}/test`, { email: testEmail });
      setTestStatus(data.status);
      if (data.status === "FAILED") toast.error(data.error || "Test failed");
      else toast.success(data.note || "Test sent");
    } catch (e) { setTestStatus("FAILED"); toast.error(apiError(e)); }
    finally { setBusy(false); }
  };

  const doSend = async () => {
    setBusy(true);
    try {
      const id = await ensureCreated();
      const { data } = await api.post(`/simulations/${id}/send`);
      if (data.provider_error) toast.warning(data.provider_error);
      toast.success(`Sent to ${data.sent} recipient(s) (${data.mode})`);
      navigate(`/history/${id}`);
    } catch (e) { toast.error(apiError(e)); }
    finally { setBusy(false); }
  };

  const senderObj = senders.find((s) => s.id === senderId);
  const fromDisplay = simEnabled && simName ? simName : (senderObj?.name || "TALBROS Security Awareness Center");
  const fromEmail = simEnabled && simFrom ? simFrom : (senderObj?.email || "security-awareness@talbros.test");

  const inputCls = "w-full h-10 px-3 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60";
  const labelCls = "text-xs font-semibold uppercase tracking-wider text-muted-foreground";

  return (
    <div data-testid="create-simulation-page">
      <PageHeader title="Create Simulation" subtitle="Automatically generated identifier · no campaign name required">
        <button onClick={doSaveDraft} disabled={busy} data-testid="save-draft-btn" className="h-9 px-4 rounded-md border border-border text-sm font-medium flex items-center gap-2 hover:bg-muted"><Save className="h-4 w-4" />Save Draft</button>
      </PageHeader>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: form */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-card border border-border rounded-lg p-5 space-y-4">
            <h3 className="font-head font-semibold text-sm">Audience & Sender</h3>
            <div>
              <label className={labelCls}>To Email Addresses</label>
              <textarea data-testid="sim-emails-input" value={emails} onChange={(e) => setEmails(e.target.value)} placeholder={"employee1@example.test\nemployee2@example.test"} className="mt-1.5 w-full min-h-[90px] p-3 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60 font-mono-t" />
              <p className="text-xs text-muted-foreground mt-1">One per line or comma-separated. Each recipient gets a unique tracking token.</p>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>From Sender</label>
                <select data-testid="sim-sender-select" value={senderId} onChange={(e) => setSenderId(e.target.value)} className={`mt-1.5 ${inputCls}`}>
                  <option value="">Select authorized sender</option>
                  {senders.map((s) => <option key={s.id} value={s.id} disabled={s.status !== "ACTIVE"}>{s.name} — {s.email} {s.status !== "ACTIVE" ? "(disabled)" : ""}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Mode</label>
                <select data-testid="sim-mode-select" value={mode} onChange={(e) => setMode(e.target.value)} className={`mt-1.5 ${inputCls}`}>
                  <option value="sandbox">Test / Sandbox (simulate)</option>
                  <option value="live">Live (authorized provider)</option>
                </select>
              </div>
            </div>
          </div>

          <div className="bg-card border border-border rounded-lg p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-head font-semibold text-sm">Email Content</h3>
              <div className="flex gap-1.5 flex-wrap">
                {TEMPLATES.map((t) => (
                  <button key={t.name} type="button" onClick={() => { setSubject(t.subject); setBody(t.body); }} className="text-[11px] px-2 py-1 rounded border border-border hover:bg-muted text-muted-foreground">{t.name}</button>
                ))}
              </div>
            </div>
            <div>
              <label className={labelCls}>Subject</label>
              <input data-testid="sim-subject-input" value={subject} onChange={(e) => setSubject(e.target.value)} className={`mt-1.5 ${inputCls}`} placeholder="Email subject line" />
            </div>
            <div>
              <label className={labelCls}>Email Body</label>
              <div className="mt-1.5"><RichEditor value={body} onChange={setBody} testid="sim-body-editor" /></div>
            </div>
            <div>
              <label className={labelCls}>Destination URL</label>
              <input data-testid="sim-dest-input" value={destUrl} onChange={(e) => setDestUrl(e.target.value)} className={`mt-1.5 ${inputCls} font-mono-t`} placeholder="https://…" />
            </div>
          </div>

          <div className="bg-card border border-border rounded-lg p-5">
            <h3 className="font-head font-semibold text-sm mb-4">Tracking Options</h3>
            <div className="grid sm:grid-cols-2 gap-3">
              {TRACK.map((t) => (
                <label key={t.key} className="flex items-center justify-between p-3 rounded-md border border-border">
                  <span className="text-sm">{t.label}</span>
                  <Switch data-testid={`track-${t.key}`} checked={tracking[t.key]} onCheckedChange={(v) => setTracking({ ...tracking, [t.key]: v })} />
                </label>
              ))}
            </div>
          </div>

          <div className="bg-card border border-border rounded-lg p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-amber-400" />
                <h3 className="font-head font-semibold text-sm">Sender Identity Simulation</h3>
              </div>
              <Switch data-testid="sim-identity-toggle" checked={simEnabled} onCheckedChange={setSimEnabled} />
            </div>
            {simEnabled && (
              <>
                <div className="rounded-md bg-amber-500/10 border border-amber-500/20 p-3 text-xs text-amber-300">
                  Simulated identities are for preview & sandbox only. Live delivery always uses the authorized sender (SPF/DKIM/DMARC are never bypassed).
                </div>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div><label className={labelCls}>Simulated From Email</label><input data-testid="sim-from-email" value={simFrom} onChange={(e) => setSimFrom(e.target.value)} className={`mt-1.5 ${inputCls} font-mono-t`} placeholder="ceo@example.test" /></div>
                  <div><label className={labelCls}>Simulated Display Name</label><input data-testid="sim-display-name" value={simName} onChange={(e) => setSimName(e.target.value)} className={`mt-1.5 ${inputCls}`} placeholder="Chief Executive Officer" /></div>
                </div>
              </>
            )}
          </div>

          <div className="bg-card border border-border rounded-lg p-5 space-y-4">
            <h3 className="font-head font-semibold text-sm">Landing Page & Awareness Form</h3>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>Landing Page</label>
                <select data-testid="sim-landing-select" value={landingId} onChange={(e) => setLandingId(e.target.value)} className={`mt-1.5 ${inputCls}`}>
                  <option value="">None</option>
                  {landings.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              </div>
              <div>
                <label className={labelCls}>Awareness Form</label>
                <select data-testid="sim-form-select" value={formId} onChange={(e) => setFormId(e.target.value)} className={`mt-1.5 ${inputCls}`}>
                  <option value="">None</option>
                  {forms.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* Right: preview + actions */}
        <div className="space-y-6">
          <div className="bg-card border border-border rounded-lg overflow-hidden sticky top-20">
            <div className="px-4 py-2.5 bg-amber-500/10 border-b border-amber-500/20 flex items-center gap-2">
              <Eye className="h-4 w-4 text-amber-400" />
              <span className="font-mono-t text-[11px] text-amber-300">SECURITY AWARENESS SIMULATION — PREVIEW</span>
            </div>
            <div className="p-4 text-sm" data-testid="email-preview">
              <div className="pb-3 border-b border-border space-y-1">
                <div className="flex gap-2"><span className="text-muted-foreground w-14 text-xs">From</span><span className="font-medium">{fromDisplay} <span className="text-muted-foreground font-mono-t text-xs">&lt;{fromEmail}&gt;</span></span></div>
                <div className="flex gap-2"><span className="text-muted-foreground w-14 text-xs">To</span><span className="font-mono-t text-xs">{emails.split(/[\n,;]+/).map((e) => e.trim()).filter(Boolean)[0] || "recipient@example.test"}</span></div>
                <div className="flex gap-2"><span className="text-muted-foreground w-14 text-xs">Subject</span><span className="font-semibold">{subject || "(no subject)"}</span></div>
              </div>
              <div className="pt-3 prose-sm [&_a]:text-primary [&_a]:underline" dangerouslySetInnerHTML={{ __html: body }} />
              {tracking.click && <div className="mt-3"><span className="inline-block bg-primary text-primary-foreground text-xs px-3 py-2 rounded-md">Open Secure Document</span></div>}
            </div>
          </div>

          <div className="bg-card border border-border rounded-lg p-5 space-y-3">
            <h3 className="font-head font-semibold text-sm flex items-center gap-2"><TestTube2 className="h-4 w-4 text-cyan-400" />Send Test</h3>
            <input data-testid="test-email-input" value={testEmail} onChange={(e) => setTestEmail(e.target.value)} placeholder="test-user@example.test" className={inputCls} />
            <div className="flex items-center gap-2">
              <button onClick={doTest} disabled={busy} data-testid="send-test-btn" className="h-9 px-4 rounded-md border border-border text-sm font-medium flex items-center gap-2 hover:bg-muted"><Mail className="h-4 w-4" />Send Test</button>
              {testStatus && <span className={`font-mono-t text-[11px] px-2 py-0.5 rounded-full border ${testStatus === "SENT" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : testStatus === "FAILED" ? "bg-rose-500/10 text-rose-400 border-rose-500/20" : "bg-slate-500/10 text-slate-400 border-slate-500/20"}`}>{testStatus}</span>}
            </div>
          </div>

          <div className="bg-card border border-border rounded-lg p-5 space-y-3">
            <h3 className="font-head font-semibold text-sm">Launch</h3>
            <div>
              <label className={labelCls}>Schedule (optional)</label>
              <input data-testid="schedule-input" type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)} className={`mt-1.5 ${inputCls}`} />
            </div>
            <button onClick={doSend} disabled={busy} data-testid="send-now-btn" className="w-full h-11 rounded-md bg-primary text-primary-foreground font-semibold text-sm flex items-center justify-center gap-2 hover:opacity-90 disabled:opacity-60">
              {scheduledAt ? <Calendar className="h-4 w-4" /> : <Rocket className="h-4 w-4" />}{scheduledAt ? "Schedule & Send" : "Send Now"}
            </button>
            <p className="text-xs text-muted-foreground">Each recipient receives an independent, cryptographically-random tracking token.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
