import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Rocket, Zap, Clock } from "lucide-react";
import { api, apiError, fmtDate } from "../lib/api";
import { Loading, EmptyState, StatusBadge, YesNo } from "../components/common";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "../components/ui/dialog";

const EVENT_COLORS = {
  EMAIL_SENT: "text-slate-400", EMAIL_DELIVERED: "text-emerald-400", EMAIL_OPENED: "text-amber-400",
  LINK_CLICKED: "text-rose-400", LANDING_PAGE_VISITED: "text-cyan-400",
  FORM_STARTED: "text-indigo-400", FORM_SUBMITTED: "text-rose-400",
};

export default function SimulationDetail() {
  const { id } = useParams();
  const [sim, setSim] = useState(null);
  const [recips, setRecips] = useState([]);
  const [timeline, setTimeline] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get(`/simulations/${id}`).then((r) => setSim(r.data)).catch(() => setSim(false));
    api.get(`/simulations/${id}/recipients`).then((r) => setRecips(r.data));
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const send = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/simulations/${id}/send`); if (data.provider_error) toast.warning(data.provider_error); toast.success(`Sent to ${data.sent} (${data.mode})`); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };
  const simulateAll = async () => {
    setBusy(true);
    try { await api.post(`/simulations/${id}/simulate-full`); toast.success("Sandbox pipeline simulated"); load(); }
    catch (e) { toast.error(apiError(e)); } finally { setBusy(false); }
  };
  const openTimeline = async (sr) => {
    setTimeline({ sr, events: null });
    const { data } = await api.get(`/simulations/${id}/recipients/${sr.id}/timeline`);
    setTimeline({ sr, events: data });
  };

  if (sim === null) return <Loading />;
  if (!sim) return <EmptyState title="Simulation not found" />;
  const st = sim.stats || {};

  const Stat = ({ label, value }) => (
    <div className="bg-card border border-border rounded-lg p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="font-mono-t text-xl font-bold">{value}</div>
    </div>
  );

  return (
    <div data-testid="simulation-detail-page">
      <Link to="/history" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-4"><ArrowLeft className="h-4 w-4" />Back to history</Link>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-head text-2xl font-bold tracking-tight font-mono-t">{sim.sim_id}</h1>
            <StatusBadge status={sim.status} />
            <span className="font-mono-t text-[11px] text-muted-foreground uppercase">{sim.mode}</span>
          </div>
          <p className="text-sm text-muted-foreground mt-1">{sim.subject}</p>
        </div>
        <div className="flex gap-2">
          {sim.mode === "sandbox" && <button onClick={simulateAll} disabled={busy} data-testid="simulate-pipeline-btn" className="h-9 px-4 rounded-md border border-cyan-500/30 bg-cyan-500/10 text-cyan-300 text-sm font-medium flex items-center gap-2"><Zap className="h-4 w-4" />Simulate Pipeline</button>}
          <button onClick={send} disabled={busy} data-testid="detail-send-btn" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold flex items-center gap-2"><Rocket className="h-4 w-4" />Send</button>
        </div>
      </div>

      <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-8 gap-3 mb-6">
        <Stat label="Recipients" value={st.recipients ?? 0} />
        <Stat label="Sent" value={st.sent ?? 0} />
        <Stat label="Delivered" value={st.delivered ?? 0} />
        <Stat label="Opens" value={st.opened ?? 0} />
        <Stat label="Clicks" value={st.clicked ?? 0} />
        <Stat label="Landing" value={st.landing ?? 0} />
        <Stat label="Form Start" value={st.form_started ?? 0} />
        <Stat label="Form Submit" value={st.form_submitted ?? 0} />
      </div>

      <div className="bg-card border border-border rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
              <th className="py-3 px-4">Email</th><th className="py-3 px-4">Dept</th><th className="py-3 px-4">Sent</th>
              <th className="py-3 px-4">Delivery</th><th className="py-3 px-4">Observed Open</th><th className="py-3 px-4">Opens</th>
              <th className="py-3 px-4">Clicked</th><th className="py-3 px-4">Clicks</th><th className="py-3 px-4">Landing</th>
              <th className="py-3 px-4">Form Start</th><th className="py-3 px-4">Form Submit</th><th className="py-3 px-4">Last Activity</th><th className="py-3 px-4"></th>
            </tr>
          </thead>
          <tbody>
            {recips.map((r) => (
              <tr key={r.id} data-testid={`recip-row-${r.email}`} className="border-b border-border/50 hover:bg-muted/40">
                <td className="py-2.5 px-4 font-mono-t text-xs">{r.email}</td>
                <td className="py-2.5 px-4 text-xs">{r.department || "—"}</td>
                <td className="py-2.5 px-4"><YesNo value={r.sent} /></td>
                <td className="py-2.5 px-4"><StatusBadge status={r.delivery_status} /></td>
                <td className="py-2.5 px-4"><YesNo value={r.open_count > 0} /></td>
                <td className="py-2.5 px-4 font-mono-t">{r.open_count}</td>
                <td className="py-2.5 px-4"><YesNo value={r.click_count > 0} /></td>
                <td className="py-2.5 px-4 font-mono-t">{r.click_count}</td>
                <td className="py-2.5 px-4"><YesNo value={r.landing_visited} /></td>
                <td className="py-2.5 px-4"><YesNo value={r.form_started} /></td>
                <td className="py-2.5 px-4"><YesNo value={r.form_submitted} /></td>
                <td className="py-2.5 px-4 text-xs text-muted-foreground">{r.last_activity ? fmtDate(r.last_activity) : "—"}</td>
                <td className="py-2.5 px-4"><button onClick={() => openTimeline(r)} data-testid={`timeline-btn-${r.email}`} className="text-xs text-primary hover:underline flex items-center gap-1"><Clock className="h-3 w-3" />Timeline</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        {recips.length === 0 && <div className="p-8"><EmptyState subtitle="No recipients." /></div>}
      </div>

      <Dialog open={!!timeline} onOpenChange={(o) => !o && setTimeline(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle className="font-mono-t text-sm">{timeline?.sr?.email}</DialogTitle></DialogHeader>
          {timeline?.events === null ? <Loading /> : timeline?.events?.length ? (
            <div className="space-y-3 max-h-[420px] overflow-auto py-2">
              {timeline.events.map((e, i) => (
                <div key={e.id} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <div className={`h-2.5 w-2.5 rounded-full bg-current ${EVENT_COLORS[e.event_type] || "text-slate-400"}`} />
                    {i < timeline.events.length - 1 && <div className="w-px flex-1 bg-border my-1" />}
                  </div>
                  <div className="pb-2">
                    <div className={`font-mono-t text-xs font-semibold ${EVENT_COLORS[e.event_type] || ""}`}>{e.event_type}</div>
                    <div className="text-xs text-muted-foreground">{fmtDate(e.timestamp)}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : <EmptyState title="NO EVENTS" subtitle="This recipient has no recorded events yet." />}
        </DialogContent>
      </Dialog>
    </div>
  );
}
