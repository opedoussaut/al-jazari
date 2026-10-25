import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Evidence } from "../api";

// Turn "[E3]" markers into links to the evidence list entry of the same message.
export function linkEvidence(markdown: string, messageId: string): string {
  return markdown.replace(/\[(E\d+)\]/g, (_, id) => `[${id}](#ev-${messageId}-${id})`);
}

export default function Answer({ text, messageId }: { text: string; messageId: string }) {
  return (
    <div className="prose-jz">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith(`#ev-${messageId}-`)) {
              return (
                <a href={href}
                   onClick={(e) => {
                     e.preventDefault();
                     document.getElementById(href.slice(1))?.scrollIntoView({ behavior: "smooth", block: "center" });
                   }}
                   className="mx-0.5 inline-flex -translate-y-px items-center rounded-md bg-navy-soft px-1.5 text-[11px] font-semibold text-navy no-underline hover:bg-navy hover:text-white">
                  {children}
                </a>
              );
            }
            return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
          },
        }}
      >
        {linkEvidence(text, messageId)}
      </ReactMarkdown>
    </div>
  );
}

const TYPE_STYLE: Record<string, string> = {
  extracted: "bg-emerald-50 text-emerald-700",
  derived: "bg-violet-50 text-violet-700",
  inferred: "bg-sky-50 text-sky-700",
  document: "bg-amber-50 text-amber-700",
  ontology: "bg-navy-soft text-navy",
  validation: "bg-rose-50 text-rose-700",
};

export function EvidenceChip({ type }: { type: string }) {
  return <span className={`chip ${TYPE_STYLE[type] ?? "bg-mist text-ink-soft"}`}>{type}</span>;
}

export function EvidenceList({ evidence, messageId }: { evidence: Evidence[]; messageId: string }) {
  if (!evidence.length) return null;
  return (
    <ul className="space-y-1.5">
      {evidence.map((e, i) => (
        <li key={e.id || `${i}-${e.label}`} id={e.id ? `ev-${messageId}-${e.id}` : undefined}
            className="flex items-start gap-2 text-[13px] target:bg-navy-soft">
          <span className="mt-0.5 w-7 shrink-0 font-mono text-[11px] font-semibold text-navy">{e.id}</span>
          <EvidenceChip type={e.evidence_type} />
          <div className="min-w-0">
            {e.url ? (
              <a href={e.url} target="_blank" rel="noreferrer" className="font-medium text-ink hover:text-navy hover:underline">
                {e.label}
              </a>
            ) : (
              <span className="font-medium">{e.label}</span>
            )}
            {(e.source || e.detail) && (
              <div className="truncate text-[12px] text-ink-mute">{[e.source, e.detail].filter(Boolean).join(" · ")}</div>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
