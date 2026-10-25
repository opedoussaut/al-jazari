import { useEffect, useRef, useState } from "react";
import { api, type ChatResponse, type Health } from "../api";
import Answer, { EvidenceList } from "../components/Answer";

const EXAMPLES = [
  "How many joints are defined in the selected Unitree G1 configuration, and what are their types?",
  "Compare the arm architectures of Unitree G1 and Berkeley Humanoid Lite.",
  "What makes ALOHA 2 different from a humanoid robot?",
  "Which actuator models drive the Berkeley Humanoid Lite biped legs?",
  "What is a robot according to CORA?",
  "Which values disagree between the G1 URDF and MJCF files?",
];

type Turn = { id: string; question: string; response?: ChatResponse; error?: string };

export default function AskPage({ health }: { health: Health | null }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const sessionId = useRef<string | undefined>(undefined);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const id = String(Date.now());
    setTurns((t) => [...t, { id, question: q }]);
    setInput("");
    setBusy(true);
    try {
      const response = await api.chat(q, sessionId.current);
      sessionId.current = response.session_id;
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, response } : x)));
    } catch (e) {
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: String((e as Error).message) } : x)));
    } finally {
      setBusy(false);
    }
  }

  const context = [...turns].reverse().find((t) => t.response)?.response?.context;

  return (
    <div className="mx-auto flex h-[calc(100vh-3.5rem)] max-w-4xl flex-col px-5">
      <div className="flex-1 overflow-y-auto py-6">
        {turns.length === 0 ? (
          <Welcome onPick={ask} health={health} />
        ) : (
          <div className="space-y-8">
            {turns.map((t) => (
              <TurnView key={t.id} turn={t} />
            ))}
            {busy && <Thinking />}
          </div>
        )}
        <div ref={bottom} />
      </div>

      <div className="border-t border-line bg-white py-4">
        {context?.configuration && (
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-ink-mute">
            <span className="label">Context</span>
            <span className="chip bg-navy-soft text-navy">{context.configuration_label}</span>
            {context.source_revision && (
              <span className="font-mono">{context.source_revision.replace(/@(\w{7})\w+/, "@$1")}</span>
            )}
          </div>
        )}
        <form onSubmit={(e) => { e.preventDefault(); ask(input); }}
              className="flex items-end gap-2 rounded-2xl border border-line bg-mist p-2 focus-within:border-navy/40 focus-within:bg-white">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input); } }}
            rows={1}
            placeholder="Ask about robot architectures, joints, actuators, ontologies…"
            className="max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-ink-mute"
          />
          <button type="submit" disabled={busy || !input.trim()} className="btn-primary">Ask</button>
        </form>
      </div>
    </div>
  );
}

function Welcome({ onPick, health }: { onPick: (q: string) => void; health: Health | null }) {
  return (
    <div className="mx-auto max-w-2xl pt-10 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">Ask JAZARI</h1>
      <p className="mt-3 text-[17px] text-ink-soft">
        Robotics answers grounded in IEEE 1872 ontologies and a knowledge graph built from pinned robot
        descriptions, with the evidence behind every claim.
      </p>
      {health && (
        <p className="mt-2 text-xs text-ink-mute">
          {health.graph.knowledge_graphs.length} robot graph(s) · {health.graph.triples.toLocaleString()} triples ·{" "}
          {health.llm.reachable && health.llm.model_installed ? `model ${health.llm.model}` : "LLM offline: deterministic answers"}
        </p>
      )}
      <div className="mt-8 grid gap-2 text-left sm:grid-cols-2">
        {EXAMPLES.map((q) => (
          <button key={q} onClick={() => onPick(q)}
                  className="card px-4 py-3 text-left text-sm text-ink-soft transition hover:border-navy/30 hover:text-ink">
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function Thinking() {
  return (
    <div className="flex items-center gap-3 text-sm text-ink-mute">
      <span className="h-2 w-2 animate-pulse rounded-full bg-navy" />
      Planning queries, reading the knowledge graph, composing a grounded answer…
    </div>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  const r = turn.response;
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-navy px-4 py-2.5 text-[15px] text-white">{turn.question}</div>
      </div>
      {turn.error && <div className="card border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{turn.error}</div>}
      {r && (
        <div className="card px-5 py-4">
          <Answer text={r.answer} messageId={turn.id} />
          {r.verification.unsupported_numbers.length > 0 && (
            <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
              <b>Check:</b> {r.verification.note} ({r.verification.unsupported_numbers.join(", ")})
            </div>
          )}
          {r.verification.removed_citations.length > 0 && (
            <div className="mt-2 text-[12px] text-ink-mute">
              Removed citations with no matching evidence: {r.verification.removed_citations.join(", ")}
            </div>
          )}
          {r.warnings.map((w) => (
            <div key={w} className="mt-2 text-[12px] text-amber-700">{w}</div>
          ))}
          {r.evidence.length > 0 && (
            <div className="mt-4 border-t border-line pt-3">
              <div className="label mb-2">Evidence</div>
              <EvidenceList evidence={r.evidence} messageId={turn.id} />
            </div>
          )}
          <details className="mt-3 border-t border-line pt-3">
            <summary className="cursor-pointer select-none text-[13px] font-medium text-navy">
              How JAZARI answered · {r.trace.length} tool call(s) · {(r.latency_ms / 1000).toFixed(1)} s
            </summary>
            <div className="mt-3 space-y-3 text-[13px]">
              <div className="text-ink-mute">
                Planner: <b className="text-ink">{r.planner === "llm" ? `LLM (${r.model})` : "deterministic rules"}</b> ·
                Answer: <b className="text-ink">{r.composer === "llm" ? `LLM (${r.model})` : "template"}</b> ·
                Numbers verified against results: <b className="text-ink">{r.verification.numbers_checked}</b>
              </div>
              {r.trace.map((t, i) => (
                <div key={i} className="rounded-xl bg-mist p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="font-mono font-semibold">{t.tool}</code>
                    <span className="font-mono text-ink-mute">{JSON.stringify(t.arguments)}</span>
                    <span className={`chip ${t.ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
                      {t.ok ? `${t.row_count} rows` : "error"}
                    </span>
                    <span className="text-ink-mute">{t.duration_ms} ms</span>
                  </div>
                  {t.error && <div className="mt-1 text-red-700">{t.error}</div>}
                  {t.derivations.length > 0 && (
                    <ul className="mt-2 list-disc pl-5 text-ink-soft">
                      {t.derivations.map((d) => <li key={d}><span className="chip mr-1 bg-violet-50 text-violet-700">derived</span>{d}</li>)}
                    </ul>
                  )}
                  {t.queries.map((q, j) => (
                    <details key={j} className="mt-2">
                      <summary className="cursor-pointer text-ink-mute">SPARQL {q.split("\n")[0].replace("# ", "")}</summary>
                      <pre className="mt-1 overflow-x-auto rounded-lg bg-white p-2 font-mono text-[11px] leading-snug">{q}</pre>
                    </details>
                  ))}
                </div>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
