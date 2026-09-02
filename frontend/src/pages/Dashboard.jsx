import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  Send, Users, Mail, MailCheck, Eye, MousePointerClick, FileCode, FileText, FileCheck2, Activity, TrendingUp,
} from "lucide-react";
import { api, fmtShort } from "../lib/api";
import { PageHeader, Loading, EmptyState, StatusBadge } from "../components/common";

const METRICS = [
  { key: "total_simulations", label: "Total Simulations", icon: Send, color: "text-indigo-400" },
  { key: "total_recipients", label: "Total Recipients", icon: Users, color: "text-cyan-400" },
  { key: "emails_sent", label: "Emails Sent", icon: Mail, color: "text-indigo-400" },
  { key: "emails_delivered", label: "Emails Delivered", icon: MailCheck, color: "text-emerald-400" },
  { key: "observed_opens", label: "Observed Opens", icon: Eye, color: "text-amber-400" },
  { key: "link_clicks", label: "Link Clicks", icon: MousePointerClick, color: "text-rose-400" },
  { key: "landing_page_visits", label: "Landing Page Visits", icon: FileCode, color: "text-cyan-400" },
  { key: "forms_started", label: "Forms Started", icon: FileText, color: "text-amber-400" },
  { key: "forms_submitted", label: "Forms Submitted", icon: FileCheck2, color: "text-rose-400" },
];

const RATES = [
  { key: "open_rate", label: "Open Rate" },
  { key: "click_rate", label: "Click Rate" },
  { key: "landing_rate", label: "Landing Page Rate" },
  { key: "form_start_rate", label: "Form Start Rate" },
  { key: "form_submission_rate", label: "Form Submission Rate" },
];

const TT = { contentStyle: { background: "hsl(221 39% 11%)", border: "1px solid hsl(213 30% 18%)", borderRadius: 8, fontSize: 12, color: "#F9FAFB" } };

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [depts, setDepts] = useState([]);

  useEffect(() => {
    api.get("/analytics/dashboard").then((r) => setData(r.data)).catch(() => setData(false));
    api.get("/analytics/departments").then((r) => setDepts(r.data)).catch(() => {});
  }, []);

  if (data === null) return <Loading />;
  const cards = data ? data.cards : {};
  const hasActivity = data?.activity?.length > 0;
  const deptWithData = depts.filter((d) => d.recipients > 0);

  return (
    <div data-testid="dashboard-page">
      <PageHeader
        title="TALBROS SECURITY AWARENESS CENTER"
        subtitle="Employee Phishing Awareness & Security Simulation Platform"
      >
        <Link to="/create-simulation" data-testid="create-simulation-button" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold flex items-center gap-2 hover:opacity-90">
          <Send className="h-4 w-4" /> Create Simulation
        </Link>
      </PageHeader>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
        {METRICS.map((m) => (
          <div key={m.key} data-testid={`metric-${m.key.replace(/_/g, "-")}`} className="bg-card border border-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{m.label}</span>
              <m.icon className={`h-4 w-4 ${m.color}`} />
            </div>
            <div className="font-mono-t text-3xl font-extrabold tracking-tight">{cards[m.key] ?? 0}</div>
          </div>
        ))}
      </div>

      {/* Rates */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        {RATES.map((r) => (
          <div key={r.key} className="bg-card border border-border rounded-lg p-4" data-testid={`rate-${r.key.replace(/_/g, "-")}`}>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">{r.label}</div>
            <div className="font-mono-t text-2xl font-bold text-primary">{data?.rates?.[r.key] ?? 0}%</div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 bg-card border border-border rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="h-4 w-4 text-primary" />
            <h3 className="font-head font-semibold text-sm">Activity Over Time</h3>
          </div>
          {hasActivity ? (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={data.activity}>
                <defs>
                  <linearGradient id="gOpens" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6366F1" stopOpacity={0.5} /><stop offset="100%" stopColor="#6366F1" stopOpacity={0} /></linearGradient>
                  <linearGradient id="gClicks" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#06B6D4" stopOpacity={0.5} /><stop offset="100%" stopColor="#06B6D4" stopOpacity={0} /></linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(213 30% 18%)" />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9CA3AF" }} />
                <YAxis tick={{ fontSize: 11, fill: "#9CA3AF" }} allowDecimals={false} />
                <Tooltip {...TT} />
                <Area type="monotone" dataKey="opens" stroke="#6366F1" fill="url(#gOpens)" strokeWidth={2} />
                <Area type="monotone" dataKey="clicks" stroke="#06B6D4" fill="url(#gClicks)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState subtitle="Run a simulation (or use Sandbox) to populate activity." />
          )}
        </div>

        <div className="lg:col-span-4 bg-card border border-border rounded-lg p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="h-4 w-4 text-cyan-400" />
            <h3 className="font-head font-semibold text-sm">Opens vs Clicks</h3>
          </div>
          {(cards.observed_opens || cards.link_clicks || cards.forms_submitted) ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={[
                { name: "Opens", value: data.opens_vs_clicks.opens, fill: "#6366F1" },
                { name: "Clicks", value: data.opens_vs_clicks.clicks, fill: "#06B6D4" },
                { name: "Submits", value: data.opens_vs_clicks.submits, fill: "#F43F5E" },
              ]}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(213 30% 18%)" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#9CA3AF" }} />
                <YAxis tick={{ fontSize: 11, fill: "#9CA3AF" }} allowDecimals={false} />
                <Tooltip {...TT} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {["#6366F1", "#06B6D4", "#F43F5E"].map((c, i) => <Cell key={i} fill={c} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState subtitle="No engagement data yet." />
          )}
        </div>

        <div className="lg:col-span-6 bg-card border border-border rounded-lg p-5">
          <h3 className="font-head font-semibold text-sm mb-4">Department Performance</h3>
          {deptWithData.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={deptWithData} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(213 30% 18%)" />
                <XAxis type="number" tick={{ fontSize: 11, fill: "#9CA3AF" }} allowDecimals={false} />
                <YAxis type="category" dataKey="department" tick={{ fontSize: 11, fill: "#9CA3AF" }} width={90} />
                <Tooltip {...TT} />
                <Bar dataKey="clicked" name="Clicks" fill="#F43F5E" radius={[0, 6, 6, 0]} />
                <Bar dataKey="opened" name="Opens" fill="#6366F1" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState subtitle="No department activity yet." />
          )}
        </div>

        <div className="lg:col-span-6 bg-card border border-border rounded-lg p-5">
          <h3 className="font-head font-semibold text-sm mb-4">Recent Activity</h3>
          {data?.recent_events?.length ? (
            <div className="space-y-2 max-h-[260px] overflow-auto">
              {data.recent_events.map((e) => (
                <div key={e.id} className="flex items-center justify-between text-sm py-1.5 border-b border-border/50 last:border-0">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono-t text-[11px] text-primary">{e.event_type}</span>
                    <span className="text-muted-foreground truncate">{e.recipient_email}</span>
                  </div>
                  <span className="text-xs text-muted-foreground shrink-0">{fmtShort(e.timestamp)}</span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState subtitle="Activity from simulations will appear here." icon={Activity} />
          )}
        </div>

        <div className="lg:col-span-12 bg-card border border-border rounded-lg p-5">
          <h3 className="font-head font-semibold text-sm mb-4">Recent Simulations</h3>
          {data?.recent_simulations?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
                    <th className="py-2 pr-4">Simulation ID</th>
                    <th className="py-2 pr-4">Subject</th>
                    <th className="py-2 pr-4">Recipients</th>
                    <th className="py-2 pr-4">Opens</th>
                    <th className="py-2 pr-4">Clicks</th>
                    <th className="py-2 pr-4">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_simulations.map((s) => (
                    <tr key={s.id} className="border-b border-border/50 hover:bg-muted/40">
                      <td className="py-2 pr-4 font-mono-t text-xs"><Link to={`/history/${s.id}`} className="text-primary hover:underline">{s.sim_id}</Link></td>
                      <td className="py-2 pr-4 truncate max-w-[280px]">{s.subject}</td>
                      <td className="py-2 pr-4 font-mono-t">{s.stats?.recipients ?? 0}</td>
                      <td className="py-2 pr-4 font-mono-t">{s.stats?.opened ?? 0}</td>
                      <td className="py-2 pr-4 font-mono-t">{s.stats?.clicked ?? 0}</td>
                      <td className="py-2 pr-4"><StatusBadge status={s.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState subtitle="Create your first simulation to get started." action={
              <Link to="/create-simulation" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold inline-flex items-center gap-2"><Send className="h-4 w-4" />Create Simulation</Link>
            } />
          )}
        </div>
      </div>
    </div>
  );
}
