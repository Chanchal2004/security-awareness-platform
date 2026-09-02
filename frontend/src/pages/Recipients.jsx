import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { UserPlus, Upload, Trash2, Pencil, Search, Users } from "lucide-react";
import { api, apiError } from "../lib/api";
import { PageHeader, Loading, EmptyState } from "../components/common";
import { Switch } from "../components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";

export default function Recipients() {
  const [params] = useSearchParams();
  const [recips, setRecips] = useState(null);
  const [depts, setDepts] = useState([]);
  const [search, setSearch] = useState(params.get("search") || "");
  const [deptFilter, setDeptFilter] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [csvOpen, setCsvOpen] = useState(false);
  const [editItem, setEditItem] = useState(null);

  const load = useCallback(() => {
    const q = new URLSearchParams();
    if (search) q.set("search", search);
    if (deptFilter) q.set("department", deptFilter);
    api.get(`/recipients?${q}`).then((r) => setRecips(r.data)).catch(() => setRecips([]));
  }, [search, deptFilter]);

  useEffect(() => { api.get("/departments").then((r) => setDepts(r.data)); }, []);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  const toggleEnabled = async (r) => {
    try { await api.put(`/recipients/${r.id}`, { ...r, enabled: !r.enabled }); load(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete ${r.email}?`)) return;
    try { await api.delete(`/recipients/${r.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  const inputCls = "w-full h-10 px-3 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60";

  return (
    <div data-testid="recipients-page">
      <PageHeader title="Recipients" subtitle="Managed independently from simulations · department optional">
        <button onClick={() => setCsvOpen(true)} data-testid="csv-import-btn" className="h-9 px-4 rounded-md border border-border text-sm font-medium flex items-center gap-2 hover:bg-muted"><Upload className="h-4 w-4" />CSV Import</button>
        <button onClick={() => setBulkOpen(true)} data-testid="bulk-add-btn" className="h-9 px-4 rounded-md border border-border text-sm font-medium flex items-center gap-2 hover:bg-muted"><Users className="h-4 w-4" />Bulk Add</button>
        <button onClick={() => setAddOpen(true)} data-testid="add-recipient-btn" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold flex items-center gap-2"><UserPlus className="h-4 w-4" />Add Recipient</button>
      </PageHeader>

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input data-testid="search-input-recipients" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by email…" className={`${inputCls} pl-9`} />
        </div>
        <select data-testid="dept-filter" value={deptFilter} onChange={(e) => setDeptFilter(e.target.value)} className="h-10 px-3 rounded-md bg-background border border-border text-sm">
          <option value="">All Departments</option>
          {depts.map((d) => <option key={d.id} value={d.name}>{d.name}</option>)}
          <option value="__none__">No Department</option>
        </select>
      </div>

      {recips === null ? <Loading /> : recips.length === 0 ? <EmptyState subtitle="No recipients found. Add one or import a CSV." /> : (
        <div className="bg-card border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
              <th className="py-3 px-4">Email</th><th className="py-3 px-4">Display Name</th><th className="py-3 px-4">Department</th><th className="py-3 px-4">Enabled</th><th className="py-3 px-4">Actions</th>
            </tr></thead>
            <tbody>
              {recips.map((r) => (
                <tr key={r.id} data-testid={`recipient-${r.email}`} className="border-b border-border/50 hover:bg-muted/40">
                  <td className="py-2.5 px-4 font-mono-t text-xs">{r.email}</td>
                  <td className="py-2.5 px-4">{r.display_name || <span className="text-muted-foreground">—</span>}</td>
                  <td className="py-2.5 px-4">{r.department || <span className="text-muted-foreground">No Department</span>}</td>
                  <td className="py-2.5 px-4"><Switch checked={r.enabled} onCheckedChange={() => toggleEnabled(r)} data-testid={`toggle-${r.email}`} /></td>
                  <td className="py-2.5 px-4"><div className="flex gap-1">
                    <button onClick={() => setEditItem(r)} data-testid={`edit-${r.email}`} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center"><Pencil className="h-3.5 w-3.5" /></button>
                    <button onClick={() => remove(r)} data-testid={`delete-${r.email}`} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center text-rose-400"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <RecipientDialog open={addOpen} onClose={() => setAddOpen(false)} depts={depts} onSaved={load} />
      {editItem && <RecipientDialog open onClose={() => setEditItem(null)} depts={depts} item={editItem} onSaved={load} />}
      <BulkDialog open={bulkOpen} onClose={() => setBulkOpen(false)} depts={depts} onSaved={load} />
      <CsvDialog open={csvOpen} onClose={() => setCsvOpen(false)} onSaved={load} />
    </div>
  );
}

function RecipientDialog({ open, onClose, depts, item, onSaved }) {
  const [email, setEmail] = useState(item?.email || "");
  const [name, setName] = useState(item?.display_name || "");
  const [dept, setDept] = useState(item?.department || "");
  const inputCls = "w-full h-10 px-3 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60";
  const save = async () => {
    try {
      const body = { email, display_name: name, department: dept, enabled: item?.enabled ?? true };
      if (item) await api.put(`/recipients/${item.id}`, body); else await api.post("/recipients", body);
      toast.success("Saved"); onSaved(); onClose();
    } catch (e) { toast.error(apiError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{item ? "Edit" : "Add"} Recipient</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><label className="text-xs text-muted-foreground">Email Address *</label><input data-testid="recipient-email-input" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} /></div>
          <div><label className="text-xs text-muted-foreground">Display Name (optional)</label><input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} /></div>
          <div><label className="text-xs text-muted-foreground">Department (optional)</label>
            <select value={dept} onChange={(e) => setDept(e.target.value)} className={inputCls}><option value="">No Department</option>{depts.map((d) => <option key={d.id} value={d.name}>{d.name}</option>)}</select>
          </div>
        </div>
        <DialogFooter><button onClick={save} data-testid="save-recipient-btn" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold">Save</button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function BulkDialog({ open, onClose, depts, onSaved }) {
  const [text, setText] = useState("");
  const [dept, setDept] = useState("");
  const save = async () => {
    try {
      const emails = text.split(/[\n,;]+/).map((e) => e.trim()).filter(Boolean);
      const { data } = await api.post("/recipients/bulk", { emails, department: dept });
      toast.success(`Imported ${data.imported} · ${data.duplicates} dupes · ${data.invalid} invalid`);
      onSaved(); onClose(); setText("");
    } catch (e) { toast.error(apiError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Bulk Add Recipients</DialogTitle></DialogHeader>
        <textarea data-testid="bulk-emails-input" value={text} onChange={(e) => setText(e.target.value)} placeholder={"employee1@example.test\nemployee2@example.test"} className="w-full min-h-[140px] p-3 rounded-md bg-background border border-border text-sm font-mono-t outline-none focus:border-primary/60" />
        <select value={dept} onChange={(e) => setDept(e.target.value)} className="w-full h-10 px-3 rounded-md bg-background border border-border text-sm"><option value="">No Department</option>{depts.map((d) => <option key={d.id} value={d.name}>{d.name}</option>)}</select>
        <DialogFooter><button onClick={save} data-testid="save-bulk-btn" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold">Import</button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CsvDialog({ open, onClose, onSaved }) {
  const [content, setContent] = useState("");
  const [preview, setPreview] = useState(null);
  const doPreview = async () => {
    try { const { data } = await api.post("/recipients/import-preview", { content }); setPreview(data); }
    catch (e) { toast.error(apiError(e)); }
  };
  const confirm = async () => {
    try { const { data } = await api.post("/recipients/import-confirm", { rows: preview.valid }); toast.success(`Imported ${data.imported}`); onSaved(); onClose(); setContent(""); setPreview(null); }
    catch (e) { toast.error(apiError(e)); }
  };
  const onFile = (e) => {
    const f = e.target.files?.[0]; if (!f) return;
    const reader = new FileReader(); reader.onload = () => setContent(reader.result); reader.readAsText(f);
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { onClose(); setPreview(null); } }}>
      <DialogContent className="max-w-xl">
        <DialogHeader><DialogTitle>CSV Import</DialogTitle></DialogHeader>
        <p className="text-xs text-muted-foreground">Format: <code className="font-mono-t">email,department</code> (department optional). Header row supported.</p>
        <input type="file" accept=".csv,text/csv" onChange={onFile} data-testid="csv-file-input" className="text-sm" />
        <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder={"email,department\nemployee1@example.test,Finance\nemployee2@example.test,"} className="w-full min-h-[120px] p-3 rounded-md bg-background border border-border text-xs font-mono-t outline-none focus:border-primary/60" />
        {preview && (
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-md bg-emerald-500/10 border border-emerald-500/20 p-2"><div className="font-mono-t text-lg text-emerald-400">{preview.summary.valid}</div><div className="text-[10px] uppercase text-muted-foreground">Valid</div></div>
            <div className="rounded-md bg-amber-500/10 border border-amber-500/20 p-2"><div className="font-mono-t text-lg text-amber-400">{preview.summary.duplicates}</div><div className="text-[10px] uppercase text-muted-foreground">Duplicates</div></div>
            <div className="rounded-md bg-rose-500/10 border border-rose-500/20 p-2"><div className="font-mono-t text-lg text-rose-400">{preview.summary.invalid}</div><div className="text-[10px] uppercase text-muted-foreground">Invalid</div></div>
          </div>
        )}
        <DialogFooter>
          {!preview ? <button onClick={doPreview} data-testid="csv-preview-btn" className="h-9 px-4 rounded-md border border-border text-sm font-medium">Preview</button>
            : <button onClick={confirm} data-testid="csv-confirm-btn" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold">Import {preview.summary.valid} recipients</button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
