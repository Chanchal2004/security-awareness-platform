import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, BarChart3, FileText, Users, Building2, Activity } from "lucide-react";
import { api, apiError } from "../lib/api";
import { PageHeader, Loading, EmptyState } from "../components/common";

const REPORTS = [
  { key: "simulation-summary", label: "Simulation Summary", icon: BarChart3, desc: "Per-simulation totals and status" },
  { key: "recipient", label: "Recipient Report", icon: Users, desc: "Full per-recipient tracking detail" },
  { key: "department", label: "Department Report", icon: Building2, desc: "Aggregated department analytics" },
  { key: "event", label: "Event Report", icon: Activity, desc: "Every recorded tracking event" },
];

export default function Reports() {
  const [sims, setSims] = useState([]);
  const [simId, setSimId] = useState("");
  const [depts, setDepts] = useState(null);

  useEffect(() => {
    api.get("/simulations").then((r) => setSims(r.data));
    api.get("/analytics/departments").then((r) => setDepts(r.data)).catch(() => setDepts([]));
  }, []);

  const download = async (key) => {
    try {
      const url = (key === "recipient" || key === "event") && simId ? `/reports/${key}?simulation_id=${simId}` : `/reports/${key}`;
      const res = await api.get(url, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(res.data);
      a.download = `${key}_report.csv`;
      a.click();
      toast.success("Report exported");
    } catch (e) { toast.error(apiError(e)); }
  };

  return (
    <div data-testid="reports-page">
      <PageHeader title="Reports" subtitle="Export awareness data as CSV" />
      <div className="mb-5 max-w-sm">
        <label className="text-xs text-muted-foreground">Scope (recipient & event reports)</label>
        <select data-testid="report-sim-select" value={simId} onChange={(e) => setSimId(e.target.value)} className="mt-1.5 w-full h-10 px-3 rounded-md bg-background border border-border text-sm">
          <option value="">All simulations</option>
          {sims.map((s) => <option key={s.id} value={s.id}>{s.sim_id} — {s.subject}</option>)}
        </select>
      </div>
      <div className="grid sm:grid-cols-2 gap-3 mb-8">
        {REPORTS.map((r) => (
          <div key={r.key} className="bg-card border border-border rounded-lg p-4 flex items-center justify-between">
            <div className="flex items-center gap-3"><r.icon className="h-5 w-5 text-primary" /><div><div className="font-semibold text-sm">{r.label}</div><div className="text-xs text-muted-foreground">{r.desc}</div></div></div>
            <button onClick={() => download(r.key)} data-testid={`export-${r.key}`} className="h-9 px-3 rounded-md border border-border text-sm font-medium flex items-center gap-2 hover:bg-muted"><Download className="h-4 w-4" />CSV</button>
          </div>
        ))}
      </div>

      <h3 className="font-head font-semibold text-sm mb-3">Department Analytics</h3>
      {depts === null ? <Loading /> : depts.length === 0 ? <EmptyState subtitle="No department data." icon={FileText} /> : (
        <div className="bg-card border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
              <th className="py-3 px-4">Department</th><th className="py-3 px-4">Recipients</th><th className="py-3 px-4">Sent</th><th className="py-3 px-4">Delivered</th>
              <th className="py-3 px-4">Opens</th><th className="py-3 px-4">Clicks</th><th className="py-3 px-4">Form Start</th><th className="py-3 px-4">Form Submit</th><th className="py-3 px-4">Click Rate</th>
            </tr></thead>
            <tbody>
              {depts.map((d) => (
                <tr key={d.department} className="border-b border-border/50 hover:bg-muted/40">
                  <td className="py-2.5 px-4 font-semibold">{d.department}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.recipients}</td><td className="py-2.5 px-4 font-mono-t">{d.sent}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.delivered}</td><td className="py-2.5 px-4 font-mono-t">{d.opened}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.clicked}</td><td className="py-2.5 px-4 font-mono-t">{d.form_started}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.form_submitted}</td><td className="py-2.5 px-4 font-mono-t text-primary">{d.click_rate}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
