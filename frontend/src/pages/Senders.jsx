import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, Plus, Trash2, Pencil } from "lucide-react";
import { api, apiError } from "../lib/api";
import {
  PageHeader,
  Loading,
  EmptyState,
  StatusBadge,
} from "../components/common";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../components/ui/dialog";

export default function Senders() {
  const [senders, setSenders] = useState(null);
  const [item, setItem] = useState(null);
  const [open, setOpen] = useState(false);

  const load = () =>
    api
      .get("/senders")
      .then((r) => setSenders(r.data))
      .catch(() => setSenders([]));

  useEffect(() => {
    load();
  }, []);

  const remove = async (id) => {
    if (!window.confirm("Delete sender?")) return;

    try {
      await api.delete(`/senders/${id}`);
      toast.success("Deleted");
      load();
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  return (
    <div data-testid="senders-page">
      <PageHeader
        title="Email Senders"
        subtitle="Configured authorized senders · credentials stay on the backend"
      >
        <button
          onClick={() => {
            setItem(null);
            setOpen(true);
          }}
          data-testid="add-sender-btn"
          className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold flex items-center gap-2"
        >
          <Plus className="h-4 w-4" />
          Add Sender
        </button>
      </PageHeader>

      <div className="rounded-md bg-muted/40 border border-border p-3 text-xs text-muted-foreground mb-4">
        Live delivery uses the configured authorized email provider. SMTP
        passwords, OAuth tokens and API keys are never exposed to the browser.
      </div>

      {senders === null ? (
        <Loading />
      ) : senders.length === 0 ? (
        <EmptyState
          subtitle="No senders configured."
          icon={Mail}
        />
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {senders.map((s) => (
            <div
              key={s.id}
              data-testid={`sender-${s.email}`}
              className="bg-card border border-border rounded-lg p-4"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2.5">
                  <Mail className="h-4 w-4 text-primary" />

                  <div>
                    <div className="font-semibold text-sm">
                      {s.name}
                    </div>

                    <div className="text-xs text-muted-foreground font-mono-t">
                      {s.email}
                    </div>
                  </div>
                </div>

                <StatusBadge status={s.status} />
              </div>

              <div className="text-xs text-muted-foreground mt-3">
                Provider: {s.provider}
              </div>

              <div className="flex gap-1 mt-3">
                <button
                  onClick={() => {
                    setItem(s);
                    setOpen(true);
                  }}
                  className="h-7 px-2 rounded hover:bg-muted flex items-center gap-1 text-xs"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </button>

                <button
                  onClick={() => remove(s.id)}
                  className="h-7 px-2 rounded hover:bg-muted flex items-center gap-1 text-xs text-rose-400"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {open && (
        <SenderDialog
          item={item}
          onClose={() => setOpen(false)}
          onSaved={load}
        />
      )}
    </div>
  );
}

function SenderDialog({ item, onClose, onSaved }) {
  const [name, setName] = useState(item?.name || "");
  const [email, setEmail] = useState(item?.email || "");
  const [provider, setProvider] = useState(item?.provider || "Resend");
  const [status, setStatus] = useState(item?.status || "ACTIVE");

  const inputCls =
    "w-full h-10 px-3 rounded-md bg-background border border-border text-sm outline-none focus:border-primary/60";

  const save = async () => {
    try {
      const body = {
        name,
        email,
        provider,
        status,
      };

      if (item) {
        await api.put(`/senders/${item.id}`, body);
      } else {
        await api.post("/senders", body);
      }

      toast.success("Saved");
      onSaved();
      onClose();
    } catch (e) {
      toast.error(apiError(e));
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {item ? "Edit" : "Add"} Sender
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground">
              Sender Name
            </label>

            <input
              data-testid="sender-name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputCls}
            />
          </div>

          <div>
            <label className="text-xs text-muted-foreground">
              Sender Email
            </label>

            <input
              data-testid="sender-email-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputCls}
            />
          </div>

          <div>
            <label className="text-xs text-muted-foreground">
              Provider
            </label>

            <input
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className={inputCls}
            />
          </div>

          <div>
            <label className="text-xs text-muted-foreground">
              Status
            </label>

            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className={inputCls}
            >
              <option value="ACTIVE">ACTIVE</option>
              <option value="DISABLED">DISABLED</option>
            </select>
          </div>
        </div>

        <DialogFooter>
          <button
            onClick={save}
            data-testid="save-sender-btn"
            className="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-semibold"
          >
            Save
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}