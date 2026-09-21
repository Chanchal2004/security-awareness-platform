import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Download,
  BarChart3,
  FileText,
  Users,
  Building2,
  Activity,
  RefreshCw,
  Paperclip,
  ExternalLink,
  MessageSquare,
  X,
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
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function fileTypeLabel(file) {
  const name = file?.filename || "";
  const ext = name.includes(".") ? name.split(".").pop().toUpperCase() : "FILE";
  return ext;
}

export default function Reports() {
  const [sims, setSims] = useState([]);
  const [simId, setSimId] = useState("");
  const [depts, setDepts] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [recipientRows, setRecipientRows] = useState([]);
  const [loadingRecipients, setLoadingRecipients] = useState(true);
  const [selectedRecipient, setSelectedRecipient] = useState(null);

  const loadRecipientReport = async (scope = "") => {
    setLoadingRecipients(true);
    try {
      const url = scope
        ? `/reports/recipient-data?simulation_id=${encodeURIComponent(scope)}`
        : "/reports/recipient-data";
      const res = await api.get(url);
      setRecipientRows(res.data || []);
    } catch (e) {
      toast.error(apiError(e));
      setRecipientRows([]);
    } finally {
      setLoadingRecipients(false);
    }
  };

  useEffect(() => {
    api.get("/simulations").then((r) => setSims(r.data || []));
    api.get("/analytics/departments").then((r) => setDepts(r.data || [])).catch(() => setDepts([]));
    loadRecipientReport();
  }, []);

  useEffect(() => {
    loadRecipientReport(simId);
  }, [simId]);

  // Keep the Recipient Report near-real-time. The backend uses Gmail History API
  // after the first sync, so a 10-second poll stays lightweight and does not
  // repeatedly scan the inbox.
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await api.post("/replies/sync");
        if (!cancelled && (res.data?.new_replies || res.data?.attachments)) {
          await loadRecipientReport(simId);
        }
      } catch (_) {
        // Background polling must never interrupt the report UI.
      }
    };
    const timer = setInterval(poll, 10000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [simId]);

  const syncReplies = async () => {
    setSyncing(true);
    try {
      const res = await api.post("/replies/sync");
      await loadRecipientReport(simId);
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
      const isRecipient = key === "recipient";
      const url = isRecipient
        ? `/reports/recipient.xlsx${simId ? `?simulation_id=${encodeURIComponent(simId)}` : ""}`
        : ((key === "event") && simId
          ? `/reports/${key}?simulation_id=${encodeURIComponent(simId)}`
          : `/reports/${key}`);
      const res = await api.get(url, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(res.data);
      a.download = isRecipient ? "recipient_report.xlsx" : `${key}_report.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
      toast.success("Report exported");
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  const openAttachment = async (file) => {
    if (!file?.file_id) return;

    try {
      const res = await api.get(
        `/replies/attachments/${encodeURIComponent(file.file_id)}`,
        { responseType: "blob" }
      );

      const url = URL.createObjectURL(res.data);
      window.open(url, "_blank", "noopener,noreferrer");

      // Keep the blob URL alive long enough for the new tab to load it.
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  const downloadAttachment = async (file) => {
    if (!file?.file_id) return;

    try {
      const res = await api.get(
        `/replies/attachments/${encodeURIComponent(file.file_id)}`,
        { responseType: "blob" }
      );

      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.filename || "attachment";
      document.body.appendChild(a);
      a.click();
      a.remove();

      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      toast.error(apiError(e));
    }
  };

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
            {sims.map((s) => (
              <option key={s.id} value={s.id}>{s.sim_id} — {s.subject}</option>
            ))}
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
              <div>
                <div className="font-semibold text-sm">{r.label}</div>
                <div className="text-xs text-muted-foreground">{r.desc}</div>
              </div>
            </div>
            <button
              onClick={() => download(r.key)}
              data-testid={`export-${r.key}`}
              className="h-9 px-3 rounded-md border border-border text-sm font-medium flex items-center gap-2 hover:bg-muted"
            >
              <Download className="h-4 w-4" />CSV
            </button>
          </div>
        ))}
      </div>

      <div className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="font-head font-semibold text-sm">Recipient Report</h3>
            <p className="text-xs text-muted-foreground mt-1">
              Per-recipient tracking, replies and original attachments.
            </p>
          </div>
          <span className="text-xs text-muted-foreground">
            {recipientRows.length} recipient{recipientRows.length === 1 ? "" : "s"}
          </span>
        </div>

        {loadingRecipients ? (
          <Loading />
        ) : recipientRows.length === 0 ? (
          <EmptyState subtitle="No recipients found for this scope." icon={Users} />
        ) : (
          <div className="bg-card border border-border rounded-lg overflow-x-auto">
            <table className="w-full text-sm min-w-[1050px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
                  {!simId && <th className="py-3 px-4">Simulation</th>}
                  <th className="py-3 px-4">Recipient</th>
                  <th className="py-3 px-4">Department</th>
                  <th className="py-3 px-4">Sent</th>
                  <th className="py-3 px-4">Delivered</th>
                  <th className="py-3 px-4">Opens</th>
                  <th className="py-3 px-4">Clicks</th>
                  <th className="py-3 px-4">Reply</th>
                  <th className="py-3 px-4">Documents</th>
                </tr>
              </thead>
              <tbody>
                {recipientRows.map((row) => {
                  const replyCount = row.reply_count || 0;
                  const attachmentCount = row.attachment_count || 0;
                  const simulation = sims.find((s) => s.id === row.simulation_id);

                  return (
                    <tr key={row.id} className="border-b border-border/50 hover:bg-muted/40">
                      {!simId && (
                        <td className="py-3 px-4 font-mono text-xs">
                          {simulation?.sim_id || row.simulation_id || "—"}
                        </td>
                      )}
                      <td className="py-3 px-4 font-semibold">{row.recipient_email}</td>
                      <td className="py-3 px-4">{row.department || "—"}</td>
                      <td className="py-3 px-4">{row.sent ? "YES" : "NO"}</td>
                      <td className="py-3 px-4">{row.delivered || "—"}</td>
                      <td className="py-3 px-4 font-mono">{row.open_count || 0}</td>
                      <td className="py-3 px-4 font-mono">{row.click_count || 0}</td>
                      <td className="py-3 px-4">
                        {replyCount > 0 ? (
                          <button
                            onClick={() => setSelectedRecipient(row)}
                            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
                          >
                            <MessageSquare className="h-3.5 w-3.5" />
                            {replyCount} {replyCount === 1 ? "Reply" : "Replies"}
                          </button>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        {attachmentCount > 0 ? (
                          <button
                            onClick={() => setSelectedRecipient(row)}
                            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
                          >
                            <Paperclip className="h-3.5 w-3.5" />
                            {attachmentCount} {attachmentCount === 1 ? "File" : "Files"}
                          </button>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <h3 className="font-head font-semibold text-sm mb-3">Department Analytics</h3>
      {depts === null ? <Loading /> : depts.length === 0 ? <EmptyState subtitle="No department data." icon={FileText} /> : (
        <div className="bg-card border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
                <th className="py-3 px-4">Department</th>
                <th className="py-3 px-4">Recipients</th>
                <th className="py-3 px-4">Sent</th>
                <th className="py-3 px-4">Delivered</th>
                <th className="py-3 px-4">Opens</th>
                <th className="py-3 px-4">Clicks</th>
                <th className="py-3 px-4">Form Start</th>
                <th className="py-3 px-4">Form Submit</th>
                <th className="py-3 px-4">Click Rate</th>
              </tr>
            </thead>
            <tbody>
              {depts.map((d) => (
                <tr key={d.department} className="border-b border-border/50 hover:bg-muted/40">
                  <td className="py-2.5 px-4 font-semibold">{d.department}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.recipients}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.sent}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.delivered}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.opened}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.clicked}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.form_started}</td>
                  <td className="py-2.5 px-4 font-mono-t">{d.form_submitted}</td>
                  <td className="py-2.5 px-4 font-mono-t text-primary">{d.click_rate}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedRecipient && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setSelectedRecipient(null);
          }}
        >
          <div
            className="w-full max-w-3xl max-h-[90vh] overflow-hidden bg-card border border-border rounded-xl shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-label={`Replies and documents for ${selectedRecipient.recipient_email}`}
          >
            <div className="flex items-start justify-between gap-4 p-5 border-b border-border">
              <div className="min-w-0">
                <h3 className="font-head font-semibold text-base truncate">
                  {selectedRecipient.recipient_email}
                </h3>
                <p className="text-xs text-muted-foreground mt-1">
                  {selectedRecipient.reply_count || 0} replies · {selectedRecipient.attachment_count || 0} documents
                </p>
              </div>
              <button
                onClick={() => setSelectedRecipient(null)}
                className="h-8 w-8 shrink-0 rounded-md border border-border flex items-center justify-center hover:bg-muted"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="max-h-[calc(90vh-90px)] overflow-y-auto p-5 space-y-5">
              {(selectedRecipient.replies || []).map((reply, index) => (
                <div key={reply.id || index} className="rounded-lg border border-border p-4">
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-semibold text-sm truncate">
                        {reply.subject || "Email Reply"}
                      </div>
                    </div>
                    <div className="text-xs text-muted-foreground shrink-0">
                      {formatDate(reply.received_at)}
                    </div>
                  </div>

                  <div className="mt-3 rounded-md bg-muted/40 border border-border/50 p-3 text-sm whitespace-pre-wrap break-words">
                    {reply.reply_text || (
                      <span className="text-muted-foreground italic">No text in reply</span>
                    )}
                  </div>

                  {reply.attachments?.length > 0 && (
                    <div className="mt-4">
                      <div className="text-xs font-semibold mb-2 flex items-center gap-1">
                        <Paperclip className="h-3.5 w-3.5" />
                        Attachments ({reply.attachments.length})
                      </div>
                      <div className="space-y-2">
                        {reply.attachments.map((file) => (
                          <div
                            key={file.file_id}
                            className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border border-border rounded-md px-3 py-3"
                          >
                            <div className="min-w-0 flex items-center gap-3">
                              <div className="h-9 w-9 shrink-0 rounded-md border border-border flex items-center justify-center text-[10px] font-bold">
                                {fileTypeLabel(file)}
                              </div>
                              <div className="min-w-0">
                                <div className="text-sm font-medium truncate">{file.filename}</div>
                                <div className="text-[11px] text-muted-foreground">
                                  {fileTypeLabel(file)} · {formatBytes(file.size)}
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <button
                                onClick={() => openAttachment(file)}
                                className="h-8 px-2.5 rounded-md border border-border text-xs flex items-center gap-1 hover:bg-muted"
                              >
                                <ExternalLink className="h-3.5 w-3.5" />
                                View
                              </button>
                              <button
                                type="button"
                                onClick={() => downloadAttachment(file)}
                                className="h-8 px-2.5 rounded-md border border-border text-xs flex items-center gap-1 hover:bg-muted"
                              >
                                <Download className="h-3.5 w-3.5" />
                                Download
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {(!selectedRecipient.replies || selectedRecipient.replies.length === 0) && (
                <div className="text-sm text-muted-foreground text-center py-8">
                  No reply content available.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
