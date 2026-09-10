import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Download, BarChart3, FileText, Users, Building2, Activity,
  RefreshCw, Paperclip, ExternalLink
} from "lucide-react";
import { api, apiError } from "../lib/api";
import { PageHeader, Loading, EmptyState } from "../components/common";

const REPORTS = [
  { key: "simulation-summary", label: "Simulation Summary", icon: BarChart3, desc: "Per-simulation totals and status" },
  { key: "recipient", label: "Recipient Report", icon: Users, desc: "Full per-recipient tracking detail" },
  { key: "department", label: "Department Report", icon: Building2, desc: "Aggregated department analytics" },
  { key: "event", label: "Event Report", icon: Activity, desc: "Every recorded tracking event" },
];

function formatBytes(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Reports() {
  const [sims, setSims] = useState([]);
  const [simId, setSimId] = useState("");
  const [depts, setDepts] = useState(null);
  const [replies, setReplies] = useState([]);
  const [syncing, setSyncing] = useState(false);

  const loadReplies = async (scope = "") => {
    try {
      const url = scope ? `/replies?simulation_id=${scope}` : "/replies";
      const res = await api.get(url);
      setReplies(res.data || []);
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  useEffect(() => {
    api.get("/simulations").then((r) => setSims(r.data));
    api.get("/analytics/departments").then((r) => setDepts(r.data)).catch(() => setDepts([]));
    loadReplies();
  }, []);

  useEffect(() => {
    loadReplies(simId);
  }, [simId]);

  const syncReplies = async () => {
    setSyncing(true);
    try {
      const res = await api.post("/replies/sync");
      await loadReplies(simId);
      toast.success(
        `Reply sync complete: ${res.data.new_replies || 0} new reply(s), ${res.data.attachments || 0} attachment(s)`
      );
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setSyncing(false);
    }
  };

  const download = async (key) => {
    try {
      const url = (key === "recipient" || key === "event") && simId
        ? `/reports/${key}?simulation_id=${simId}`
        : `/reports/${key}`;
      const res = await api.get(url, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(res.data);
      a.download = `${key}_report.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast.success("Report exported");
    } catch (e) { toast.error(apiError(e)); }
  };

  const attachmentUrl = (fileId) =>
    `${api.defaults.baseURL || ""}/replies/attachments/${fileId}`;

  return (
    <div data-testid="reports-page">
      <PageHeader title="Reports" subtitle="Export awareness data as CSV" />

      <div className="mb-5 flex flex-col sm:flex-row gap-3 sm:items-end">
        <div className="max-w-sm flex-1">
          <label className="text-xs text-muted-foreground">Scope (recipient, event & replies)</label>
          <select
            data-testid="report-sim-select"
            value={simId}
            onChange={(e) => setSimId(e.target.value)}
            className="mt-1.5 w-full h-10 px-3 rounded-md bg-background border border-border text-sm"
          >
            <option value="">All simulations</option>
            {sims.map((s) => <option key={s.id} value={s.id}>{s.sim_id} — {s.subject}</option>)}
          </select>
        </div>

        <button
          onClick={syncReplies}
          disabled={syncing}
          className="h-10 px-4 rounded-md border border-border text-sm font-medium flex items-center gap-2 hover:bg-muted disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
          {syncing ? "Syncing…" : "Sync Email Replies"}
        </button>
      </div>

      <div className="grid sm:grid-cols-2 gap-3 mb-8">
        {REPORTS.map((r) => (
          <div key={r.key} className="bg-card border border-border rounded-lg p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <r.icon className="h-5 w-5 text-primary" />
              <div><div className="font-semibold text-sm">{r.label}</div><div className="text-xs text-muted-foreground">{r.desc}</div></div>
            </div>
            <button onClick={() => download(r.key)} data-testid={`export-${r.key}`} className="h-9 px-3 rounded-md border border-border text-sm font-medium flex items-center gap-2 hover:bg-muted">
              <Download className="h-4 w-4" />CSV
            </button>
          </div>
        ))}
      </div>

      <div className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="font-head font-semibold text-sm">Email Replies & Attachments</h3>
            <p className="text-xs text-muted-foreground mt-1">
              Replies received in the authorized Gmail mailbox for this simulation.
            </p>
          </div>
          <span className="text-xs text-muted-foreground">{replies.length} repl{replies.length === 1 ? "y" : "ies"}</span>
        </div>

        {replies.length === 0 ? (
          <EmptyState subtitle="No employee replies received yet. Click Sync Email Replies after a recipient replies." icon={FileText} />
        ) : (
          <div className="space-y-3">
            {replies.map((reply) => (
              <div key={reply.id || reply.message_id} className="bg-card border border-border rounded-lg p-4">
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                  <div>
                    <div className="font-semibold text-sm">{reply.recipient_email}</div>
                    <div className="text-xs text-muted-foreground">{reply.subject}</div>
                  </div>
                  <div className="text-xs text-muted-foreground">{reply.received_at}</div>
                </div>

                <div className="mt-3 rounded-md bg-muted/40 border border-border/50 p-3 text-sm whitespace-pre-wrap">
                  {reply.reply_text || <span className="text-muted-foreground italic">No text in reply</span>}
                </div>

                {reply.attachments?.length > 0 && (
                  <div className="mt-3">
                    <div className="text-xs font-semibold mb-2 flex items-center gap-1">
                      <Paperclip className="h-3.5 w-3.5" />
                      Attachments ({reply.attachments.length})
                    </div>
                    <div className="space-y-2">
                      {reply.attachments.map((file) => (
                        <div key={file.file_id} className="flex items-center justify-between gap-3 border border-border rounded-md px-3 py-2">
                          <div className="min-w-0">
                            <div className="text-sm truncate">{file.filename}</div>
                            <div className="text-[11px] text-muted-foreground">{file.mime_type} · {formatBytes(file.size)}</div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <a
                              href={attachmentUrl(file.file_id)}
                              target="_blank"
                              rel="noreferrer"
                              className="h-8 px-2.5 rounded-md border border-border text-xs flex items-center gap-1 hover:bg-muted"
                            >
                              <ExternalLink className="h-3.5 w-3.5" />View
                            </a>
                            <a
                              href={attachmentUrl(file.file_id)}
                              download={file.filename}
                              className="h-8 px-2.5 rounded-md border border-border text-xs flex items-center gap-1 hover:bg-muted"
                            >
                              <Download className="h-3.5 w-3.5" />Download
                            </a>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
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
