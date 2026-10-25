import { useEffect, useMemo, useState } from "react";
import { api, type OntologyTerm } from "../api";

const ORIGIN_STYLE: Record<string, string> = {
  cora: "bg-navy-soft text-navy", corax: "bg-sky-50 text-sky-700", rparts: "bg-emerald-50 text-emerald-700",
  pos: "bg-amber-50 text-amber-700", sumo: "bg-mist text-ink-soft", jz: "bg-violet-50 text-violet-700",
};
const prefix = (id: string) => id.split(":")[0];

export default function OntologyPage() {
  const [classes, setClasses] = useState<OntologyTerm[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<OntologyTerm[] | null>(null);
  const [selected, setSelected] = useState("cora:Robot");
  const [detail, setDetail] = useState<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.classes().then(setClasses).catch((e) => setError(e.message)); }, []);
  useEffect(() => { api.term(selected).then(setDetail).catch((e) => setError(e.message)); }, [selected]);
  useEffect(() => {
    if (!query.trim()) { setResults(null); return; }
    const t = setTimeout(() => api.classes(query).then(setResults), 200);
    return () => clearTimeout(t);
  }, [query]);

  const { roots, children } = useMemo(() => {
    const ids = new Set(classes.map((c) => c.id));
    const children: Record<string, string[]> = {};
    const roots: string[] = [];
    classes.forEach((c) => {
      const ps = c.parents.filter((p) => ids.has(p));
      if (!ps.length) roots.push(c.id);
      ps.forEach((p) => (children[p] ??= []).push(c.id));
    });
    return { roots: roots.sort(), children };
  }, [classes]);

  return (
    <div className="mx-auto grid max-w-6xl gap-6 px-5 py-8 lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside>
        <h1 className="text-3xl font-semibold tracking-tight">Ontologies</h1>
        <p className="mt-1 text-sm text-ink-soft">IEEE 1872-2015 (CORA, CORAX, RPARTS, POS) via IEEE1872-owl, and the JAZARI extension.</p>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search classes and properties…"
               className="mt-4 w-full rounded-xl border border-line bg-mist px-3 py-2 text-sm outline-none focus:border-navy/40 focus:bg-white" />
        <div className="card mt-3 max-h-[70vh] overflow-auto p-3 text-[13px]">
          {results ? (
            results.length ? results.map((t) => <TermLink key={t.id} id={t.id} kind={t.kind} onClick={setSelected} active={selected === t.id} />)
                           : <div className="text-ink-mute">No match.</div>
          ) : (
            roots.map((r) => <Node key={r} id={r} children={children} selected={selected} onSelect={setSelected} depth={0} />)
          )}
        </div>
      </aside>

      <section>
        {error && <div className="text-sm text-red-700">{error}</div>}
        {detail && (
          <div className="card p-6">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`chip ${ORIGIN_STYLE[prefix(detail.id)]}`}>{prefix(detail.id)}</span>
              <span className="chip bg-mist text-ink-soft">{detail.kind}</span>
            </div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">{detail.label} <span className="font-mono text-base font-normal text-ink-mute">{detail.id}</span></h2>
            <div className="text-sm text-ink-mute">{detail.origin}</div>
            <div className="mt-4">
              {detail.definition ? (
                <>
                  <p className="text-[15px]">{detail.definition}</p>
                  <div className="mt-1 text-[12px] text-ink-mute">{detail.definition_source}</div>
                </>
              ) : (
                <p className="text-[14px] text-ink-soft">No natural-language definition in the OWL file. {detail.copyright_note}</p>
              )}
            </div>
            {detail.kind === "class" ? (
              <div className="mt-6 grid gap-6 md:grid-cols-2">
                <Field label="Direct superclasses" ids={detail.direct_superclasses} onSelect={setSelected} />
                <Field label="Direct subclasses" ids={detail.direct_subclasses} onSelect={setSelected} />
                <Field label="All superclasses (inferred)" ids={detail.all_superclasses_inferred} onSelect={setSelected} />
                <div>
                  <div className="label mb-1">Knowledge-graph instances</div>
                  <div className="text-2xl font-semibold text-navy">{detail.knowledge_graph_instances}</div>
                  <ul className="mt-1 text-[13px] text-ink-soft">{detail.instance_examples.map((x: string) => <li key={x} className="font-mono">{x}</li>)}</ul>
                </div>
                <div className="md:col-span-2">
                  <div className="label mb-1">Properties</div>
                  {detail.properties.length ? (
                    <table className="w-full text-[13px]">
                      <thead><tr className="text-left text-ink-mute"><th className="py-1 font-medium">Property</th><th className="font-medium">This class is</th><th className="font-medium">Other end</th><th className="font-medium">IEEE 1872 axiom</th></tr></thead>
                      <tbody>
                        {detail.properties.map((p: any, i: number) => ( // eslint-disable-line @typescript-eslint/no-explicit-any
                          <tr key={i} className="border-t border-line/70">
                            <td className="py-1"><button className="font-mono text-navy hover:underline" onClick={() => setSelected(p.property)}>{p.property}</button></td>
                            <td>{p.class_is}</td>
                            <td className="font-mono">{p.other_end ?? "—"}</td>
                            <td className="font-mono">{p.ieee_1872_axiom ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : <div className="text-[13px] text-ink-mute">None declared.</div>}
                </div>
                {detail.mappings.length > 0 && (
                  <div className="md:col-span-2">
                    <div className="label mb-1">Alignments</div>
                    <ul className="text-[13px]">{detail.mappings.map((m: any) => <li key={m.target} className="font-mono">{m.relation} {m.target}</li>)/* eslint-disable-line @typescript-eslint/no-explicit-any */}</ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-6 grid gap-6 md:grid-cols-3">
                <Field label="Parent properties" ids={detail.parent_properties} onSelect={setSelected} />
                <Field label="Domain" ids={detail.domain} onSelect={setSelected} />
                <Field label="Range" ids={detail.range} onSelect={setSelected} />
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function Node({ id, children, selected, onSelect, depth }: { id: string; children: Record<string, string[]>; selected: string; onSelect: (id: string) => void; depth: number }) {
  const [open, setOpen] = useState(depth < 2);
  const kids = children[id] ?? [];
  return (
    <div style={{ marginLeft: depth ? 12 : 0 }}>
      <div className="flex items-center gap-1">
        <button className="w-4 text-ink-mute" onClick={() => setOpen(!open)}>{kids.length ? (open ? "▾" : "▸") : ""}</button>
        <TermLink id={id} onClick={onSelect} active={selected === id} />
      </div>
      {open && kids.sort().map((k) => <Node key={k} id={k} children={children} selected={selected} onSelect={onSelect} depth={depth + 1} />)}
    </div>
  );
}

function TermLink({ id, kind, onClick, active }: { id: string; kind?: string; onClick: (id: string) => void; active: boolean }) {
  return (
    <button onClick={() => onClick(id)} className={`my-0.5 flex items-center gap-1.5 rounded px-1 text-left ${active ? "bg-navy text-white" : "hover:bg-mist"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${active ? "bg-white" : ORIGIN_STYLE[prefix(id)]?.split(" ")[0] ?? "bg-mist"} ring-1 ring-black/10`} />
      <span className="font-mono">{id}</span>{kind === "property" && <span className="text-[10px] opacity-60">prop</span>}
    </button>
  );
}

function Field({ label, ids, onSelect }: { label: string; ids: string[]; onSelect: (id: string) => void }) {
  return (
    <div>
      <div className="label mb-1">{label}</div>
      {ids?.length ? (
        <div className="flex flex-wrap gap-1">
          {ids.map((i) => <button key={i} onClick={() => onSelect(i)} className={`chip font-mono ${ORIGIN_STYLE[prefix(i)] ?? "bg-mist"} hover:ring-1 hover:ring-navy`}>{i}</button>)}
        </div>
      ) : <div className="text-[13px] text-ink-mute">None</div>}
    </div>
  );
}
