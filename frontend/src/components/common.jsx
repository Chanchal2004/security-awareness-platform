import { Loader2, Inbox, ShieldCheck } from "lucide-react";

export function PageHeader({ title, subtitle, children, testid }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between mb-6" data-testid={testid}>
      <div>
        <h1 className="font-head text-2xl sm:text-3xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      {children && <div className="flex items-center gap-2 flex-wrap">{children}</div>}
    </div>
  );
}

export function Loading({ label = "Loading…" }) {
  return (
    <div className="flex items-center justify-center py-20 text-muted-foreground" data-testid="loading-state">
      <Loader2 className="h-5 w-5 animate-spin mr-2" /> {label}
    </div>
  );
}

export function EmptyState({ title = "NO DATA AVAILABLE", subtitle, icon: Icon = Inbox, action, testid }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center border border-dashed border-border rounded-lg" data-testid={testid || "empty-state"}>
      <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center mb-3">
        <Icon className="h-6 w-6 text-muted-foreground" />
      </div>
      <p className="font-head font-semibold text-sm tracking-wide">{title}</p>
      {subtitle && <p className="text-xs text-muted-foreground mt-1 max-w-sm">{subtitle}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

const BADGE = {
  ACTIVE: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  RUNNING: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  COMPLETED: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
  SCHEDULED: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  DRAFT: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  PENDING: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  PAUSED: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  CANCELLED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  DISABLED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  FAILED: "bg-rose-500/10 text-rose-400 border-rose-500/20",
  SENT: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  SANDBOX_SENT: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  DELIVERED: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
};

export function StatusBadge({ status }) {
  const cls = BADGE[status] || "bg-slate-500/10 text-slate-400 border-slate-500/20";
  return (
    <span className={`inline-flex items-center font-mono-t text-[11px] px-2.5 py-0.5 rounded-full border ${cls}`}>
      {status}
    </span>
  );
}

export function YesNo({ value }) {
  return value ? (
    <span className="inline-flex items-center gap-1 text-emerald-400 font-mono-t text-xs"><ShieldCheck className="h-3 w-3" />YES</span>
  ) : (
    <span className="text-muted-foreground font-mono-t text-xs">NO</span>
  );
}
