import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileCheck2, Plus, Trash2, Pencil, GripVertical, ArrowUp, ArrowDown } from "lucide-react";
import { api, apiError } from "../lib/api";
import { PageHeader, Loading, EmptyState } from "../components/common";
import { Switch } from "../components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";

const FIELD_TYPES = ["text", "email", "phone", "textarea"];
const uid = () => Math.random().toString(36).slice(2);

export default function Forms() {
  const [forms, setForms] = useState(null);
  const [item, setItem] = useState(null);
  const [open, setOpen] = useState(false);
  const load = () => api.get("/forms").then((r) => setForms(r.data)).catch(() => setForms([]));
  useEffect(() => { load(); }, []);
  const remove = async (id) => { if (!window.confirm("Delete form?")) return; try { await api.delete(`/forms/${id}`); load(); } catch (e) { toast.error(apiError(e)); } };

  return (
    <div data-testid="forms-page">
      <PageHeader title="Awareness Forms" subtitle="Controlled awareness exercises · never collects credentials">
        <button onClick={() => { setItem(null); setOpen(true); }} data-testid="add-form-btn" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold flex items-center gap-2"><Plus className="h-4 w-4" />New Form</button>
      </PageHeader>
      <div className="rounded-md bg-rose-500/10 border border-rose-500/20 p-3 text-xs text-rose-300 mb-4">
        Forms may not request passwords, OTP/MFA codes, banking or card details, or any authentication secret. Such fields are rejected server-side.
      </div>
      {forms === null ? <Loading /> : forms.length === 0 ? <EmptyState subtitle="No forms yet." icon={FileCheck2} /> : (
        <div className="grid sm:grid-cols-2 gap-3">
          {forms.map((fm) => (
            <div key={fm.id} data-testid={`form-${fm.id}`} className="bg-card border border-border rounded-lg p-4">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2.5"><FileCheck2 className="h-4 w-4 text-primary" /><div className="font-semibold text-sm">{fm.name}</div></div>
                <div className="flex gap-1">
                  <button onClick={() => { setItem(fm); setOpen(true); }} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center"><Pencil className="h-3.5 w-3.5" /></button>
                  <button onClick={() => remove(fm.id)} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center text-rose-400"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
              </div>
              <div className="text-xs text-muted-foreground mt-2">{fm.fields.length} field(s): {fm.fields.map((x) => x.label).join(", ")}</div>
            </div>
          ))}
        </div>
      )}
      {open && <FormDialog item={item} onClose={() => setOpen(false)} onSaved={load} />}
    </div>
  );
}

function FormDialog({ item, onClose, onSaved }) {
  const [name, setName] = useState(item?.name || "");
  const [fields, setFields] = useState(item?.fields?.length ? item.fields : [{ id: uid(), label: "Full Name", type: "text", required: true }]);
  const inputCls = "w-full h-9 px-2.5 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60";
  const upd = (i, k, v) => setFields(fields.map((f, idx) => idx === i ? { ...f, [k]: v } : f));
  const move = (i, d) => { const j = i + d; if (j < 0 || j >= fields.length) return; const c = [...fields]; [c[i], c[j]] = [c[j], c[i]]; setFields(c); };
  const save = async () => {
    try { const body = { name, fields }; if (item) await api.put(`/forms/${item.id}`, body); else await api.post("/forms", body); toast.success("Saved"); onSaved(); onClose(); }
    catch (e) { toast.error(apiError(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>{item ? "Edit" : "New"} Form</DialogTitle></DialogHeader>
        <div className="space-y-3 max-h-[60vh] overflow-auto">
          <div><label className="text-xs text-muted-foreground">Form Name</label><input data-testid="form-name-input" value={name} onChange={(e) => setName(e.target.value)} className="w-full h-10 px-3 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60" /></div>
          <div className="space-y-2">
            {fields.map((f, i) => (
              <div key={f.id} className="flex items-center gap-2 p-2 rounded-md border border-border">
                <GripVertical className="h-4 w-4 text-muted-foreground shrink-0" />
                <input value={f.label} onChange={(e) => upd(i, "label", e.target.value)} className={inputCls} placeholder="Field label" />
                <select value={f.type} onChange={(e) => upd(i, "type", e.target.value)} className="h-9 px-2 rounded-md bg-background border border-border text-xs">{FIELD_TYPES.map((t) => <option key={t}>{t}</option>)}</select>
                <label className="flex items-center gap-1 text-[11px] text-muted-foreground shrink-0"><Switch checked={f.required} onCheckedChange={(v) => upd(i, "required", v)} />Req</label>
                <button onClick={() => move(i, -1)} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center"><ArrowUp className="h-3 w-3" /></button>
                <button onClick={() => move(i, 1)} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center"><ArrowDown className="h-3 w-3" /></button>
                <button onClick={() => setFields(fields.filter((_, idx) => idx !== i))} className="h-7 w-7 rounded hover:bg-muted flex items-center justify-center text-rose-400"><Trash2 className="h-3 w-3" /></button>
              </div>
            ))}
          </div>
          <button onClick={() => setFields([...fields, { id: uid(), label: "", type: "text", required: false }])} data-testid="add-field-btn" className="text-xs text-primary flex items-center gap-1"><Plus className="h-3.5 w-3.5" />Add field</button>
        </div>
        <DialogFooter><button onClick={save} data-testid="save-form-btn" className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold">Save</button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
