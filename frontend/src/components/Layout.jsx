import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Send, History, Users, Building2, FileCode, FileCheck2,
  BarChart3, Mail, TestTube2, ShieldAlert, Settings, Shield, Sun, Moon,
  LogOut, Search, Bell, ChevronDown, Menu,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator,
} from "./ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle } from "./ui/sheet";

const NAV = [
  { label: "Dashboard", icon: LayoutDashboard, path: "/", id: "dashboard" },
  { label: "Create Simulation", icon: Send, path: "/create-simulation", id: "create-simulation" },
  { label: "Simulation History", icon: History, path: "/history", id: "simulation-history" },
  { label: "Recipients", icon: Users, path: "/recipients", id: "recipients" },
  { label: "Departments", icon: Building2, path: "/departments", id: "departments" },
  { label: "Landing Pages", icon: FileCode, path: "/landing-pages", id: "landing-pages" },
  { label: "Awareness Forms", icon: FileCheck2, path: "/awareness-forms", id: "awareness-forms" },
  { label: "Reports", icon: BarChart3, path: "/reports", id: "reports" },
  { label: "Email Senders", icon: Mail, path: "/email-senders", id: "email-senders" },
  { label: "Test / Sandbox", icon: TestTube2, path: "/sandbox", id: "sandbox" },
  { label: "Audit Logs", icon: ShieldAlert, path: "/audit-logs", id: "audit-logs" },
  { label: "Settings", icon: Settings, path: "/settings", id: "settings" },
];

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2 py-3 mb-4">
      <div className="h-9 w-9 rounded-lg bg-primary/15 border border-primary/30 flex items-center justify-center">
        <Shield className="h-5 w-5 text-primary" />
      </div>
      <div>
        <div className="font-head font-bold text-sm leading-tight tracking-tight">TALBROS</div>
        <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Security Awareness</div>
      </div>
    </div>
  );
}

function NavItems({ onNavigate }) {
  return (
    <nav className="space-y-0.5">
      {NAV.map((item) => (
        <NavLink
          key={item.id}
          to={item.path}
          end={item.path === "/"}
          onClick={onNavigate}
          data-testid={`sidebar-link-${item.id}`}
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
              isActive
                ? "bg-primary/15 text-primary font-semibold"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
            }`
          }
        >
          <item.icon className="h-4 w-4 shrink-0" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

export default function Layout() {
  const { user, logout, theme, toggleTheme } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [drawer, setDrawer] = useState(false);

  const onSearch = (e) => {
    e.preventDefault();
    if (q.trim()) navigate(`/recipients?search=${encodeURIComponent(q.trim())}`);
  };

  return (
    <div className="min-h-screen flex bg-background text-foreground">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-64 flex-col justify-between border-r border-border bg-slate-950/60 backdrop-blur-md p-4 fixed inset-y-0 left-0 z-30">
        <div><Brand /><NavItems /></div>
        <div className="px-2 py-3 flex items-center gap-2 text-xs text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          Security Awareness Active
        </div>
      </aside>

      {/* Mobile drawer */}
      <Sheet open={drawer} onOpenChange={setDrawer}>
        <SheetContent side="left" className="w-72 p-4 border-border bg-slate-950/95" data-testid="mobile-nav-drawer">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Brand />
          <NavItems onNavigate={() => setDrawer(false)} />
        </SheetContent>
      </Sheet>

      {/* Main */}
      <div className="flex-1 md:ml-64 flex flex-col min-w-0">
        <header className="h-16 border-b border-border bg-background/80 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between sticky top-0 z-20 gap-3">
          <button onClick={() => setDrawer(true)} data-testid="mobile-menu-button" className="md:hidden h-9 w-9 rounded-md hover:bg-muted flex items-center justify-center shrink-0">
            <Menu className="h-5 w-5" />
          </button>
          <form onSubmit={onSearch} className="relative w-full max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              data-testid="global-search-input"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search recipients…"
              className="w-full h-9 pl-9 pr-3 rounded-md bg-muted/50 border border-border text-sm outline-none focus:border-primary/50"
            />
          </form>
          <div className="flex items-center gap-2 sm:gap-3 ml-auto">
            <span className="hidden sm:inline-flex items-center font-mono-t text-[11px] px-2.5 py-1 rounded-full border bg-cyan-500/10 text-cyan-400 border-cyan-500/20">
              SANDBOX / LIVE
            </span>
            <button onClick={toggleTheme} data-testid="theme-toggle-button" className="h-9 w-9 rounded-md hover:bg-muted flex items-center justify-center">
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button data-testid="user-menu-trigger" className="flex items-center gap-2 h-9 px-2 rounded-md hover:bg-muted">
                  <div className="h-7 w-7 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center text-xs font-semibold text-primary">
                    {(user?.name || "A")[0]}
                  </div>
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <div className="px-2 py-1.5">
                  <div className="text-sm font-semibold">{user?.name}</div>
                  <div className="text-xs text-muted-foreground truncate">{user?.email}</div>
                  <span className="mt-1 inline-block font-mono-t text-[10px] px-2 py-0.5 rounded-full border bg-primary/10 text-primary border-primary/20">
                    {(user?.role || "admin").toUpperCase()}
                  </span>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} data-testid="logout-btn" className="text-rose-400 focus:text-rose-400">
                  <LogOut className="h-4 w-4 mr-2" /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>
        <main className="flex-1 p-4 sm:p-6 max-w-[1600px] w-full mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
