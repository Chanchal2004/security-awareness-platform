import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Save, Trash2, Clock } from "lucide-react";
import { api, apiError } from "../lib/api";
import { PageHeader, Loading } from "../components/common";

export default function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [expired, setExpired] = useState(null);

  const load = () => {
    api.get("/settings").then((r) => setSettings(r.data)).catch(() => setSettings(false));
    api.get("/settings/expired-simulations").then((r) => setExpired(r.data)).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    try { await api.put("/settings", { retention_days: settings.retention_days, default_mode: settings.default_mode }); toast.success("Settings saved"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const purge = async () => {
    if (!window.confirm(`Delete ${expired?.count} expired simulation(s) and all their data?`)) return;
    try { const { data } = await api.delete("/settings/expired-simulations"); toast.success(`Deleted ${data.deleted}`); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  if (settings === null) return <Loading />;
  const inputCls = "w-full h-10 px-3 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60";

  return (
    <div data-testid="settings-page" className="max-w-2xl">
      <PageHeader title="Settings" subtitle="Data retention & platform defaults" />
      <div className="bg-card border border-border rounded-lg p-5 space-y-4">
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Data Retention</label>
          <select data-testid="retention-select" value={settings.retention_days} onChange={(e) => setSettings({ ...settings, retention_days: Number(e.target.value) })} className={`mt-1.5 ${inputCls}`}>
            {[30, 90, 180, 365].map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
          <p className="text-xs text-muted-foreground mt-1">Simulations older than this are flagged as expired and can be deleted.</p>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Default Send Mode</label>
          <select data-testid="default-mode-select" value={settings.default_mode} onChange={(e) => setSettings({ ...settings, default_mode: e.target.value })} className={`mt-1.5 ${inputCls}`}>
            <option value="sandbox">Sandbox</option><option value="live">Live</option>
          </select>
        </div>
        <button onClick={save} data-testid="save-settings-btn" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold flex items-center gap-2"><Save className="h-4 w-4" />Save Settings</button>
      </div>

      <div className="bg-card border border-border rounded-lg p-5 mt-6">
        <div className="flex items-center gap-2 mb-3"><Clock className="h-4 w-4 text-amber-400" /><h3 className="font-head font-semibold text-sm">Expired Data</h3></div>
        {expired === null ? <Loading /> : (
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground"><span className="font-mono-t text-foreground">{expired.count}</span> simulation(s) older than {expired.retention_days} days.</p>
            <button onClick={purge} disabled={!expired.count} data-testid="purge-expired-btn" className="h-9 px-4 rounded-md border border-rose-500/30 bg-rose-500/10 text-rose-300 text-sm font-medium flex items-center gap-2 disabled:opacity-50"><Trash2 className="h-4 w-4" />Delete Expired</button>
          </div>
        )}
      </div>

      <div className="bg-card border border-border rounded-lg p-5 mt-6 text-xs text-muted-foreground space-y-1">
        <p className="font-semibold text-foreground text-sm mb-1">Privacy & Security</p>
        <p>· Only data necessary for the authorized awareness exercise is collected.</p>
        <p>· Awareness forms never collect passwords, OTP/MFA codes, or payment/banking secrets.</p>
        <p>· Tracking tokens are cryptographically random; internal database IDs are never exposed in tracking URLs.</p>
        <p>· All administrative actions are captured in Audit Logs.</p>
      </div>
    </div>
  );
}
