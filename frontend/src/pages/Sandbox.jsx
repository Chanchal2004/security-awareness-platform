import { useEffect, useState } from "react";
import { toast } from "sonner";
import { TestTube2, Zap, Play } from "lucide-react";
import { api, apiError, fmtDate } from "../lib/api";
import { PageHeader, Loading, EmptyState, StatusBadge } from "../components/common";

const EVENTS = ["EMAIL_SENT", "EMAIL_DELIVERED", "EMAIL_OPENED", "LINK_CLICKED", "LANDING_PAGE_VISITED", "FORM_STARTED", "FORM_SUBMITTED"];

export default function Sandbox() {
  const [sims, setSims] = useState([]);
  const [simId, setSimId] = useState("");
  const [recips, setRecips] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/simulations").then((r) => { const sb = r.data.filter((s) => s.mode === "sandbox"); setSims(sb); if (sb[0]) setSimId(sb[0].id); });
  }, []);
  useEffect(() => { if (simId) loadRecips(); }, [simId]);

  const loadRecips = () => api.get(`/simulations/${simId}/recipients`).then((r) => setRecips(r.data));

  const fire = async (recipientId, eventType) => {
    try { await api.post(`/simulations/${simId}/simulate-event`, { recipient_id: recipientId, event_type: eventType }); toast.success(`${eventType} recorded`); loadRecips(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const fireAll = async () => {
    setLoading(true);
    try { await api.post(`/simulations/${simId}/simulate-full`); toast.success("Full pipeline simulated"); loadRecips(); }
    catch (e) { toast.error(apiError(e)); } finally { setLoading(false); }
  };

  return (
    <div data-testid="sandbox-page">
      <PageHeader title="Test / Sandbox" subtitle="Verify the full tracking pipeline without sending external mail" />
      <div className="rounded-md bg-cyan-500/10 border border-cyan-500/20 p-3 text-xs text-cyan-200 mb-4">
        Sandbox records real tracking events (opens, clicks, landing, form) for a simulation without delivering any external email. Create a simulation in <strong>Sandbox</strong> mode, then trigger events here.
      </div>

      {sims.length === 0 ? (
        <EmptyState subtitle="No sandbox simulations yet. Create one with Mode = Test/Sandbox." icon={TestTube2} />
      ) : (
        <>
          <div className="flex flex-col sm:flex-row gap-3 mb-4">
            <select data-testid="sandbox-sim-select" value={simId} onChange={(e) => setSimId(e.target.value)} className="h-10 px-3 rounded-md bg-background border border-border text-sm flex-1">
              {sims.map((s) => <option key={s.id} value={s.id}>{s.sim_id} — {s.subject}</option>)}
            </select>
            <button onClick={fireAll} disabled={loading || !simId} data-testid="sandbox-simulate-all" className="h-10 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold flex items-center gap-2 disabled:opacity-60"><Zap className="h-4 w-4" />{loading ? "Working…" : "Simulate Full Pipeline"}</button>
          </div>

          {recips.length === 0 ? <EmptyState subtitle="No recipients on this simulation." /> : (
            <div className="space-y-3">
              {recips.map((r) => (
                <div key={r.id} data-testid={`sandbox-recip-${r.email}`} className="bg-card border border-border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="font-mono-t text-sm">{r.email}</div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <StatusBadge status={r.delivery_status} />
                      <span>opens {r.open_count} · clicks {r.click_count}</span>
                      {r.last_activity && <span>· {fmtDate(r.last_activity)}</span>}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {EVENTS.map((ev) => (
                      <button key={ev} onClick={() => fire(r.id, ev)} data-testid={`fire-${ev}-${r.email}`} className="text-[11px] px-2.5 py-1 rounded border border-border hover:bg-primary/10 hover:border-primary/40 text-muted-foreground hover:text-foreground flex items-center gap-1"><Play className="h-3 w-3" />{ev}</button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
