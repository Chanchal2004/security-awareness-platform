import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileCode, Plus, Trash2, Pencil } from "lucide-react";
import { api, apiError } from "../lib/api";
import { PageHeader, Loading, EmptyState } from "../components/common";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";

export default function LandingPages() {
  const [pages, setPages] = useState(null);
  const [item, setItem] = useState(null);
  const [open, setOpen] = useState(false);
  const load = () => api.get("/landing-pages").then((r) => setPages(r.data)).catch(() => setPages([]));
  useEffect(() => { load(); }, []);
  const remove = async (id) => { if (!window.confirm("Delete landing page?")) return; try { await api.delete(`/landing-pages/${id}`); load(); } catch (e) { toast.error(apiError(e)); } };

  return (
    <div data-testid="landing-pages-page">
      <PageHeader title="Landing Pages" subtitle="Awareness pages shown after a click">
        <button onClick={() => { setItem(null); setOpen(true); }} data-testid="add-landing-btn" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold flex items-center gap-2"><Plus className="h-4 w-4" />New Landing Page</button>
      </PageHeader>
      {pages === null ? <Loading /> : pages.length === 0 ? <EmptyState subtitle="No landing pages yet." icon={FileCode} /> : (
        <div className="grid sm:grid-cols-2 gap-3">
          {pages.map((p) => (
            <div key={p.id} data-testid={`landing-${p.id}`} className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2.5"><FileCode className="h-4 w-4 text-primary" /><div className="font-semibold text-sm">{p.name}</div></div>
                <div className="flex gap-1">
                  <button onClick={() => { setItem(p); setOpen(true); }} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center"><Pencil className="h-3.5 w-3.5" /></button>
                  <button onClick={() => remove(p.id)} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center text-rose-400"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
              </div>
              <div className="text-xs text-muted-foreground mt-2 font-head font-semibold">{p.title}</div>
              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{p.message}</p>
            </div>
          ))}
        </div>
      )}
      {open && <LandingDialog item={item} onClose={() => setOpen(false)} onSaved={load} />}
    </div>
  );
}

function LandingDialog({ item, onClose, onSaved }) {
  const [f, setF] = useState({
    name: item?.name || "", title: item?.title || "", message: item?.message || "",
    indicators: item?.indicators || "", reporting_instructions: item?.reporting_instructions || "",
  });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const inputCls = "w-full h-10 px-3 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60";
  const taCls = "w-full min-h-[70px] p-2.5 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60";
  const save = async () => {
    try { if (item) await api.put(`/landing-pages/${item.id}`, f); else await api.post("/landing-pages", f); toast.success("Saved"); onSaved(); onClose(); }
    catch (e) { toast.error(apiError(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>{item ? "Edit" : "New"} Landing Page</DialogTitle></DialogHeader>
        <div className="space-y-3 max-h-[60vh] overflow-auto">
          <div><label className="text-xs text-muted-foreground">Name</label><input data-testid="landing-name-input" value={f.name} onChange={set("name")} className={inputCls} /></div>
          <div><label className="text-xs text-muted-foreground">Title</label><input data-testid="landing-title-input" value={f.title} onChange={set("title")} className={inputCls} /></div>
          <div><label className="text-xs text-muted-foreground">Awareness Message</label><textarea value={f.message} onChange={set("message")} className={taCls} /></div>
          <div><label className="text-xs text-muted-foreground">Suspicious Indicators</label><textarea value={f.indicators} onChange={set("indicators")} className={taCls} /></div>
          <div><label className="text-xs text-muted-foreground">Reporting Instructions</label><textarea value={f.reporting_instructions} onChange={set("reporting_instructions")} className={taCls} /></div>
        </div>
        <DialogFooter><button onClick={save} data-testid="save-landing-btn" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold">Save</button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
