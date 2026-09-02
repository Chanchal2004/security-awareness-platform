import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Building2, Plus, Trash2, Pencil, Search } from "lucide-react";
import { api, apiError } from "../lib/api";
import { PageHeader, Loading, EmptyState } from "../components/common";

export default function Departments() {
  const [depts, setDepts] = useState(null);
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");
  const [editId, setEditId] = useState(null);
  const [editName, setEditName] = useState("");

  const load = () => api.get("/departments").then((r) => setDepts(r.data)).catch(() => setDepts([]));
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!name.trim()) return;
    try { await api.post("/departments", { name }); setName(""); toast.success("Department created"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const rename = async (id) => {
    try { await api.put(`/departments/${id}`, { name: editName }); setEditId(null); toast.success("Renamed"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };
  const remove = async (id) => {
    if (!window.confirm("Delete department? Recipients keep their data but lose this label.")) return;
    try { await api.delete(`/departments/${id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(apiError(e)); }
  };

  const inputCls = "h-10 px-3 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60";
  const filtered = (depts || []).filter((d) => d.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <div data-testid="departments-page">
      <PageHeader title="Departments" subtitle="Optional labels for recipients · fully editable" />
      <div className="flex flex-col sm:flex-row gap-3 mb-5">
        <input data-testid="new-dept-input" value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && create()} placeholder="New department name" className={`${inputCls} flex-1`} />
        <button onClick={create} data-testid="create-dept-btn" className="h-10 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold flex items-center gap-2"><Plus className="h-4 w-4" />Create Department</button>
      </div>
      <div className="relative mb-4 max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input data-testid="search-input-departments" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search departments…" className={`${inputCls} pl-9 w-full`} />
      </div>

      {depts === null ? <Loading /> : filtered.length === 0 ? <EmptyState subtitle="No departments yet. Create your own." icon={Building2} /> : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((d) => (
            <div key={d.id} data-testid={`dept-${d.name}`} className="bg-card border border-border rounded-lg p-4 flex items-center justify-between">
              {editId === d.id ? (
                <input data-testid={`dept-rename-input-${d.name}`} value={editName} onChange={(e) => setEditName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && rename(d.id)} className={`${inputCls} flex-1 mr-2`} autoFocus />
              ) : (
                <div className="flex items-center gap-2.5"><Building2 className="h-4 w-4 text-primary" /><div><div className="font-semibold text-sm">{d.name}</div><div className="text-xs text-muted-foreground">{d.recipient_count} recipients</div></div></div>
              )}
              <div className="flex gap-1">
                <button onClick={() => { setEditId(d.id); setEditName(d.name); }} data-testid={`dept-edit-btn-${d.name}`} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center"><Pencil className="h-3.5 w-3.5" /></button>
                <button onClick={() => remove(d.id)} data-testid={`dept-delete-btn-${d.name}`} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center text-rose-400"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
