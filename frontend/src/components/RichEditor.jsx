import { useRef, useEffect } from "react";
import { Bold, Italic, Heading, Link2, Type } from "lucide-react";

export default function RichEditor({ value, onChange, testid = "email-body-editor" }) {
  const ref = useRef(null);

  // Write incoming HTML into the node only when it differs from the live DOM
  // (initial mount + template inserts). This never runs on our own keystrokes,
  // so the caret is preserved.
  useEffect(() => {
    if (ref.current && value !== ref.current.innerHTML) {
      ref.current.innerHTML = value || "";
    }
  }, [value]);

  const cmd = (command, arg) => {
    ref.current?.focus();
    document.execCommand(command, false, arg);
    if (ref.current) onChange(ref.current.innerHTML);
  };

  const insertLink = () => {
    const url = window.prompt("Link URL (https://…)");
    if (url) cmd("createLink", url);
  };

  const Btn = ({ onClick, icon: Icon, label }) => (
    <button
      type="button"
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      title={label}
      data-testid={`editor-${label.toLowerCase().replace(/\s/g, "-")}`}
      className="h-8 w-8 flex items-center justify-center rounded hover:bg-muted text-muted-foreground hover:text-foreground"
    >
      <Icon className="h-4 w-4" />
    </button>
  );

  return (
    <div className="border border-border rounded-md overflow-hidden bg-background">
      <div className="flex items-center gap-0.5 border-b border-border px-1.5 py-1 bg-muted/40">
        <Btn onClick={() => cmd("bold")} icon={Bold} label="Bold" />
        <Btn onClick={() => cmd("italic")} icon={Italic} label="Italic" />
        <Btn onClick={() => cmd("formatBlock", "<h2>")} icon={Heading} label="Heading" />
        <Btn onClick={() => cmd("formatBlock", "<p>")} icon={Type} label="Paragraph" />
        <Btn onClick={insertLink} icon={Link2} label="Link" />
      </div>
      <div
        ref={ref}
        data-testid={testid}
        contentEditable
        suppressContentEditableWarning
        onInput={(e) => onChange(e.currentTarget.innerHTML)}
        className="min-h-[220px] max-h-[420px] overflow-auto p-4 text-sm leading-relaxed outline-none prose-sm [&_h2]:text-lg [&_h2]:font-bold [&_a]:text-primary [&_a]:underline"
      />
    </div>
  );
}
