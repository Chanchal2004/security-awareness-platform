import { useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { api, fmtDate } from "../lib/api";
import { PageHeader, Loading, EmptyState } from "../components/common";

const ACTIONS = ["", "LOGIN", "LOGOUT", "SIMULATION_CREATED", "SIMULATION_LAUNCHED", "SIMULATION_PAUSED",
  "SIMULATION_CANCELLED", "RECIPIENT_IMPORTED", "RECIPIENT_CREATED", "RECIPIENT_UPDATED", "RECIPIENT_DELETED",
  "SENDER_ADDED", "SENDER_UPDATED", "SENDER_DISABLED", "LANDING_PAGE_CREATED", "FORM_CREATED", "FORM_UPDATED",
  "REPORT_EXPORTED", "SETTINGS_CHANGED"];

export default function AuditLogs() {
  const [logs, setLogs] = useState(null);
  const [action, setAction] = useState("");
  useEffect(() => {
    const q = action ? `?action=${action}` : "";
    api.get(`/audit-logs${q}`).then((r) => setLogs(r.data)).catch(() => setLogs([]));
  }, [action]);

  return (
    <div data-testid="audit-logs-page">
      <PageHeader title="Audit Logs" subtitle="Every administrative action is recorded">
        <select data-testid="audit-action-filter" value={action} onChange={(e) => setAction(e.target.value)} className="h-9 px-3 rounded-md bg-background border border-border text-sm">
          {ACTIONS.map((a) => <option key={a} value={a}>{a || "All Actions"}</option>)}
        </select>
      </PageHeader>
      {logs === null ? <Loading /> : logs.length === 0 ? <EmptyState subtitle="No audit entries." icon={ShieldAlert} /> : (
        <div className="bg-card border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
              <th className="py-3 px-4">Timestamp</th><th className="py-3 px-4">Administrator</th><th className="py-3 px-4">Action</th><th className="py-3 px-4">Details</th>
            </tr></thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} className="border-b border-border/50 hover:bg-muted/40">
                  <td className="py-2.5 px-4 text-xs text-muted-foreground">{fmtDate(l.timestamp)}</td>
                  <td className="py-2.5 px-4 font-mono-t text-xs">{l.admin_email}</td>
                  <td className="py-2.5 px-4"><span className="font-mono-t text-[11px] px-2 py-0.5 rounded-full border bg-primary/10 text-primary border-primary/20">{l.action}</span></td>
                  <td className="py-2.5 px-4 text-xs text-muted-foreground">{l.details || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
