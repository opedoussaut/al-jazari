import { useEffect, useMemo, useState } from "react";
import { api, type Components, type QuantityRow, type RobotSummary, type TreeNode } from "../api";
import { EvidenceList } from "../components/Answer";

const CLASS_STYLE: Record<string, string> = {
  RevoluteJoint: "bg-navy-soft text-navy",
  FixedJoint: "bg-mist text-ink-soft",
  FloatingJoint: "bg-amber-50 text-amber-700",
  ContinuousJoint: "bg-sky-50 text-sky-700",
  PrismaticJoint: "bg-violet-50 text-violet-700",
};

export default function RobotsPage() {
  const [robots, setRobots] = useState<RobotSummary[]>([]);
  const [configId, setConfigId] = useState<string | null>(null);
  const [info, setInfo] = useState<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [comp, setComp] = useState<Components | null>(null);
  const [validation, setValidation] = useState<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.robots().then((r) => {
      setRobots(r);
      const first = r[0]?.configurations.find((c) => c.baseline) ?? r[0]?.configurations[0];
      if (first) setConfigId(first.id);
    }).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!configId) return;
    setComp(null);
    Promise.all([api.robot(configId), api.components(configId), api.validation(configId).catch(() => null)])
      .then(([i, c, v]) => { setInfo(i); setComp(c); setValidation(v); })
      .catch((e) => setError(e.message));
  }, [configId]);

  const quantities = useMemo(() => {
    const m: Record<string, QuantityRow[]> = {};
    comp?.joint_quantities.forEach((q) => (m[q.name] ??= []).push(q));
    return m;
  }, [comp]);

  const s = info?.joint_summary;

  return (
    <div className="mx-auto max-w-6xl px-5 py-8">
      <h1 className="text-3xl font-semibold tracking-tight">Explore Robots</h1>
      <p className="mt-1 text-ink-soft">Every value below is read from the knowledge graph and links to the exact source line.</p>
      {error && <div className="mt-4 text-sm text-red-700">{error}</div>}

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        {robots.map((r) => r.configurations.map((c) => (
          <button key={c.id} onClick={() => setConfigId(c.id)}
                  className={`card p-4 text-left transition ${configId === c.id ? "border-navy ring-1 ring-navy" : "hover:border-navy/30"}`}>
            <div className="label">{r.manufacturer} · {r.category}</div>
            <div className="mt-1 text-lg font-semibold">{r.name}</div>
            <div className="text-sm text-ink-soft">{c.label}</div>
            {!c.baseline && <div className="mt-1 text-[11px] text-ink-mute">additional variant</div>}
          </button>
        )))}
      </div>

      {info && comp && s && (
        <>
          <section className="mt-8 grid gap-4 md:grid-cols-4">
            <Stat label="Joints in graph" value={s.total_joints_in_graph} />
            <Stat label="Articulated DoF" value={s.articulated_dof}
                  hint={s.hand_or_finger_joints.count ? `${s.hand_or_finger_joints.count} in hands/grippers` : undefined} />
            <Stat label="Independent DoF" value={s.independent_dof}
                  hint={s.joint_couplings.length ? `${s.joint_couplings.length} joint coupling(s)` : undefined} />
            <Stat label="Actuators · sensors" value={`${new Set(comp.actuators.map((a) => a.name)).size} · ${comp.sensors.length}`} />
          </section>

          <section className="mt-4 card p-5">
            <div className="label">Configuration</div>
            <div className="mt-1 text-lg font-semibold">{info.info.configuration} <span className="font-mono text-sm text-ink-mute">{info.info.native_name}</span></div>
            <p className="mt-1 text-sm text-ink-soft">{info.info.selection_rationale}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-sm">
              {Object.entries(s.joints_by_class as Record<string, number>).map(([k, v]) => (
                <span key={k} className={`chip ${CLASS_STYLE[k] ?? "bg-mist"}`}>{v} {k}</span>
              ))}
              {Object.entries(s.joints_by_source_format as Record<string, Record<string, number>>).map(([f, v]) => (
                <span key={f} className="chip bg-mist text-ink-soft">{f.toUpperCase()}: {v.total} joints</span>
              ))}
            </div>
            {s.important_notes?.map((n: string) => <p key={n} className="mt-2 text-[13px] text-ink-soft">{n}</p>)}
            <div className="mt-4 border-t border-line pt-3">
              <div className="label mb-2">Sources</div>
              <EvidenceList evidence={info.evidence} messageId="robot" />
            </div>
          </section>

          <section className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
            <div className="card max-h-[640px] overflow-auto p-5">
              <div className="label mb-2">
                {comp.kinematics.trees.length > 1
                  ? `Kinematic trees · ${comp.kinematics.trees.length} roots`
                  : `Kinematic tree · root ${comp.kinematics.root}`}
              </div>
              {comp.kinematics.trees.map((t) => (
                <div key={t.link} className="mb-3"><Tree node={t} selected={selected} onSelect={setSelected} /></div>
              ))}
            </div>
            <div className="card max-h-[640px] overflow-auto p-0">
              <table className="w-full text-[13px]">
                <thead className="sticky top-0 bg-white">
                  <tr className="border-b border-line text-left text-ink-mute">
                    <th className="px-3 py-2 font-medium">Joint</th><th className="px-2 font-medium">Class</th>
                    <th className="px-2 font-medium">Parent → child</th><th className="px-2 font-medium">Limits (URDF/Xacro | MJCF)</th>
                    <th className="px-2 font-medium">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {comp.joints.map((j) => (
                    <tr key={j.name} id={`joint-${j.name}`} onClick={() => setSelected(j.name)}
                        className={`cursor-pointer border-b border-line/60 align-top ${selected === j.name ? "bg-navy-soft" : "hover:bg-mist"}`}>
                      <td className="px-3 py-1.5 font-mono">{j.name}{j.actuator && <span title="driven by an MJCF actuator" className="ml-1 text-navy">⚙</span>}</td>
                      <td className="px-2"><span className={`chip ${CLASS_STYLE[j.class] ?? "bg-mist"}`}>{j.class.replace("Joint", "")}</span></td>
                      <td className="px-2 text-ink-soft">{j.parent ?? "world"} → {j.child}</td>
                      <td className="px-2"><Limits rows={quantities[j.name] ?? []} /></td>
                      <td className="px-2"><Mentions mentions={j.mentions} rows={quantities[j.name] ?? []} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="mt-4 grid gap-4 md:grid-cols-2">
            <div className="card p-5">
              <div className="label mb-2">Sensors and cameras declared in the sources</div>
              <ul className="space-y-1 text-[13px]">
                {comp.sensors.map((x) => (
                  <li key={x.name}><a className="font-mono hover:text-navy hover:underline" href={`${x.fileUrl}#L${x.line}`} target="_blank" rel="noreferrer">{x.name}</a>
                    <span className="text-ink-mute"> · {x.type} on {x.link ?? (x.type === "camera" ? "world frame" : "—")}</span></li>
                ))}
              </ul>
              {comp.sensors.length === 0 && <p className="text-[13px] text-ink-mute">No sensor elements in these files.</p>}
              <p className="mt-3 text-[12px] text-ink-mute">Links named like sensors (e.g. d435_link) are coordinate frames, not sensor declarations, so they are not listed.</p>
            </div>
            <div className="card p-5">
              <div className="label mb-2">Source consistency (across formats)</div>
              {validation ? (
                <>
                  <div className="text-[13px]">SHACL: <b>{validation.shacl_conforms ? "conforms" : "violations"}</b> · structural errors: <b>{validation.errors.length}</b></div>
                  {validation.inconsistencies.length === 0 && (
                    <div className="mt-2 text-[13px] text-emerald-700">No disagreements between formats.</div>
                  )}
                  <ul className="mt-2 space-y-1 text-[13px]">
                    {validation.inconsistencies.map((i: string) => <li key={i} className="text-rose-700">{i}</li>)}
                  </ul>
                  <div className="mt-2 text-[12px] text-ink-mute">{validation.warnings.length} values stated in only one format.</div>
                </>
              ) : <div className="text-sm text-ink-mute">No validation report.</div>}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className="mt-1 text-3xl font-semibold tracking-tight text-navy">{value}</div>
      {hint && <div className="mt-0.5 text-[12px] text-ink-mute">{hint}</div>}
    </div>
  );
}

function Tree({ node, selected, onSelect, depth = 0 }: { node: TreeNode; selected: string | null; onSelect: (j: string) => void; depth?: number }) {
  return (
    <ul className={depth ? "ml-3 border-l border-line pl-3" : ""}>
      <li className="py-0.5 text-[13px]">
        {node.joint ? (
          <button onClick={() => { onSelect(node.joint!); document.getElementById(`joint-${node.joint}`)?.scrollIntoView({ block: "center", behavior: "smooth" }); }}
                  className={`rounded px-1 text-left ${selected === node.joint ? "bg-navy text-white" : "hover:bg-mist"}`}>
            <span className={node.class === "FixedJoint" ? "text-ink-mute" : "text-navy"}>{node.class === "FixedJoint" ? "▪" : "↻"}</span>{" "}
            <span className="font-mono">{node.joint}</span> <span className="text-ink-mute">→ {node.link}</span>
          </button>
        ) : (
          <span className="font-mono font-semibold">{node.link}</span>
        )}
        {node.children.map((c) => <Tree key={c.joint} node={c} selected={selected} onSelect={onSelect} depth={depth + 1} />)}
      </li>
    </ul>
  );
}

function fmt(v: number) { return Number.isInteger(v) ? String(v) : v.toFixed(3); }

// QUDT unit local names as stored in the graph -> display symbols
const UNIT: Record<string, string> = { RAD: "rad", M: "m", "N-M": "N·m", N: "N", "RAD-PER-SEC": "rad/s", "M-PER-SEC": "m/s" };

function Limits({ rows }: { rows: QuantityRow[] }) {
  if (!rows.length) return <span className="text-ink-mute">not stated</span>;
  const get = (p: string, f: string) => rows.find((r) => r.property === p && r.format === f);
  const line = (p: string, label: string) => {
    const u = get(p, "urdf") ?? get(p, "xacro"), m = get(p, "mjcf");
    if (!u && !m) return null;
    const differ = u && m && Math.abs(u.value - m.value) > 1e-4 * Math.max(1, Math.abs(u.value));
    const unit = (u ?? m)!.unit;
    return (
      <div key={p} className={differ ? "text-rose-700" : ""}>
        <span className="text-ink-mute">{label}</span> {u ? fmt(u.value) : "—"} | {m ? fmt(m.value) : "—"}{" "}
        <span className="text-ink-mute">{UNIT[unit] ?? unit}</span>
      </div>
    );
  };
  return (
    <div className="font-mono text-[12px] leading-5">
      {line("lowerLimit", "min")}{line("upperLimit", "max")}{line("effortLimit", "effort")}{line("velocityLimit", "vel")}
    </div>
  );
}

function Mentions({ mentions, rows }: { mentions: string; rows: QuantityRow[] }) {
  const urls: Record<string, string> = {};
  rows.forEach((r) => { urls[r.format] = r.fileUrl; });
  return (
    <div className="space-y-0.5 font-mono text-[11px]">
      {mentions.split(" | ").map((m) => {
        const [fmtType, line] = m.split("@L");
        const f = fmtType.split(":")[0];
        const url = urls[f];
        return url ? <a key={m} href={`${url}#L${line}`} target="_blank" rel="noreferrer" className="block text-navy hover:underline">{fmtType} L{line}</a>
                   : <div key={m} className="text-ink-mute">{fmtType} L{line}</div>;
      })}
    </div>
  );
}
