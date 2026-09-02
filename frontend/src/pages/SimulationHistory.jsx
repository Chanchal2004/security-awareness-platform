import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Play, Pause, XCircle, Send } from "lucide-react";
import { api, apiError, fmtDate } from "../lib/api";
import { PageHeader, Loading, EmptyState, StatusBadge } from "../components/common";

export default function SimulationHistory() {
  const [sims, setSims] = useState(null);
  const [status, setStatus] = useState("");

  const load = () => api.get("/simulations").then((r) => setSims(r.data)).catch(() => setSims([]));
  useEffect(() => { load(); }, []);

  const setSimStatus = async (id, s) => {
    try { await api.put(`/simulations/${id}/status`, { status: s }); toast.success(`Status → ${s}`); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  if (sims === null) return <Loading />;
  const filtered = status ? sims.filter((s) => s.status === status) : sims;

  return (
    <div data-testid="simulation-history-page">
      <PageHeader title="Simulation History" subtitle="All phishing awareness simulations">
        <select data-testid="status-filter" value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 px-3 rounded-md bg-background border border-border text-sm">
          <option value="">All Statuses</option>
          {["DRAFT", "SCHEDULED", "RUNNING", "COMPLETED", "PAUSED", "CANCELLED"].map((s) => <option key={s}>{s}</option>)}
        </select>
        <Link to="/create-simulation" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold flex items-center gap-2"><Send className="h-4 w-4" />New</Link>
      </PageHeader>

      {filtered.length === 0 ? (
        <EmptyState subtitle="No simulations yet." />
      ) : (
        <div className="bg-card border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
                <th className="py-3 px-4">Simulation ID</th><th className="py-3 px-4">Created</th><th className="py-3 px-4">Sender</th>
                <th className="py-3 px-4">Subject</th><th className="py-3 px-4">Recipients</th><th className="py-3 px-4">Mode</th>
                <th className="py-3 px-4">Status</th><th className="py-3 px-4">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.id} data-testid={`sim-row-${s.sim_id}`} className="border-b border-border/50 hover:bg-muted/40">
                  <td className="py-3 px-4 font-mono-t text-xs"><Link to={`/history/${s.id}`} className="text-primary hover:underline">{s.sim_id}</Link></td>
                  <td className="py-3 px-4 text-xs text-muted-foreground">{fmtDate(s.created_at)}</td>
                  <td className="py-3 px-4 text-xs">{s.sender_email || "—"}</td>
                  <td className="py-3 px-4 truncate max-w-[240px]">{s.subject}</td>
                  <td className="py-3 px-4 font-mono-t">{s.recipient_count}</td>
                  <td className="py-3 px-4"><span className="font-mono-t text-[11px] text-muted-foreground uppercase">{s.mode}</span></td>
                  <td className="py-3 px-4"><StatusBadge status={s.status} /></td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-1">
                      <button title="Resume/Run" onClick={() => setSimStatus(s.id, "RUNNING")} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center text-emerald-400"><Play className="h-3.5 w-3.5" /></button>
                      <button title="Pause" onClick={() => setSimStatus(s.id, "PAUSED")} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center text-amber-400"><Pause className="h-3.5 w-3.5" /></button>
                      <button title="Cancel" onClick={() => setSimStatus(s.id, "CANCELLED")} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center text-rose-400"><XCircle className="h-3.5 w-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
