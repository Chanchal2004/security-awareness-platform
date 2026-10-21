import { useEffect, useRef } from "react";
import { Bold, Italic, Heading2, Pilcrow, Link2 } from "lucide-react";

const escapeHtml = (text = "") =>
  String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");

const plainTextToHtml = (text = "") =>
  String(text)
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => `<p>${line ? escapeHtml(line) : "<br>"}</p>`)
    .join("");

export default function RichEditor({ value = "", onChange, testid = "email-body-editor" }) {
  const editorRef = useRef(null);

  // Sync the editor when a template is selected or the parent value changes.
  // Explicit foreground color below keeps text visible in dark mode.
  useEffect(() => {
    const editor = editorRef.current;
    const next = value || "";
    if (editor && editor.innerHTML !== next) editor.innerHTML = next;
  }, [value]);

  const emitChange = () => {
    const editor = editorRef.current;
    if (editor && typeof onChange === "function") onChange(editor.innerHTML);
  };

  const runCommand = (command, argument = null) => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.focus();
    document.execCommand(command, false, argument);
    emitChange();
  };

  const handlePaste = (event) => {
    // Convert clipboard content to safe plain text while preserving line breaks.
    event.preventDefault();
    const clipboard = event.clipboardData;
    let text = clipboard?.getData("text/plain") || "";

    if (!text.trim()) {
      const html = clipboard?.getData("text/html") || "";
      if (html) {
        const parsed = new DOMParser().parseFromString(html, "text/html");
        text = parsed.body.innerText || parsed.body.textContent || "";
      }
    }
    if (!text) return;

    const editor = editorRef.current;
    if (!editor) return;
    editor.focus();
    document.execCommand("insertHTML", false, plainTextToHtml(text));
    emitChange();
  };

  const ToolbarButton = ({ label, icon: Icon, onClick }) => (
    <button
      type="button"
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
      title={label}
      aria-label={label}
      data-testid={`editor-${label.toLowerCase().replace(/\s+/g, "-")}`}
      className="h-8 w-8 flex items-center justify-center rounded hover:bg-muted text-muted-foreground hover:text-foreground"
    >
      <Icon className="h-4 w-4" />
    </button>
  );

  return (
    <div className="border border-border rounded-md overflow-hidden bg-background">
      <div className="flex items-center gap-0.5 border-b border-border px-1.5 py-1 bg-muted/40">
        <ToolbarButton label="Bold" icon={Bold} onClick={() => runCommand("bold")} />
        <ToolbarButton label="Italic" icon={Italic} onClick={() => runCommand("italic")} />
        <ToolbarButton label="Heading" icon={Heading2} onClick={() => runCommand("formatBlock", "<h2>")} />
        <ToolbarButton label="Paragraph" icon={Pilcrow} onClick={() => runCommand("formatBlock", "<p>")} />
        <ToolbarButton
          label="Link"
          icon={Link2}
          onClick={() => {
            const url = window.prompt("Link URL (https://…)");
            if (url && /^https?:\/\//i.test(url.trim())) runCommand("createLink", url.trim());
            else if (url) window.alert("Enter a valid URL beginning with http:// or https://");
          }}
        />
      </div>

      <div
        ref={editorRef}
        data-testid={testid}
        contentEditable
        suppressContentEditableWarning
        role="textbox"
        aria-label="Email body"
        aria-multiline="true"
        data-placeholder="Click here and paste or type your email content…"
        onInput={emitChange}
        onPaste={handlePaste}
        onBlur={emitChange}
        className="min-h-[220px] max-h-[420px] overflow-auto p-4 text-sm text-foreground leading-relaxed outline-none prose-sm [&_h2]:text-lg [&_h2]:font-bold [&_a]:text-primary [&_a]:underline [&_p]:my-0 [&_p]:mb-3"
        style={{ color: "hsl(var(--foreground))", caretColor: "hsl(var(--foreground))", whiteSpace: "normal", overflowWrap: "anywhere" }}
      />
      <style>{`
        [data-testid="${testid}"][contenteditable="true"]:empty::before {
          content: attr(data-placeholder);
          color: #8b95a7;
          pointer-events: none;
        }
        [data-testid="${testid}"][contenteditable="true"] p { margin-top: 0; margin-bottom: 0.75rem; }
      `}</style>
    </div>
  );
}
