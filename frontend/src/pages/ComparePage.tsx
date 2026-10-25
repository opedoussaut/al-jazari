import { useEffect, useState } from "react";
import { api } from "../api";

export default function ComparePage() {
  const [data, setData] = useState<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // compare the baseline configuration of every robot in the knowledge graph
    api.robots()
      .then((robots) => api.compare(robots.map((r) => (r.configurations.find((c) => c.baseline) ?? r.configurations[0]).id)))
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-5 py-8">
      <h1 className="text-3xl font-semibold tracking-tight">Compare Robots</h1>
      <p className="mt-1 text-ink-soft">
        Baseline configuration of each robot, read from the knowledge graph. Missing values stay missing, and parts a robot category does not have are marked "not applicable", never filled in.
      </p>
      {error && <div className="mt-4 text-sm text-red-700">{error}</div>}
      {data && (
        <div className="card mt-6 overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-line text-left">
                <th className="w-48 px-4 py-3 font-medium text-ink-mute">Dimension</th>
                {data.columns.map((c: any) => ( // eslint-disable-line @typescript-eslint/no-explicit-any
                  <th key={c.requested} className="px-4 py-3">
                    <div className="font-semibold">{c.available ? c.configuration.robot : c.requested}</div>
                    <div className="font-normal text-ink-mute">{c.available ? c.configuration.label : c.reason}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.dimensions.map((d: string) => (
                <tr key={d} className="border-b border-line/60 align-top">
                  <td className="px-4 py-2 text-ink-soft">{d}</td>
                  {data.columns.map((c: any) => ( // eslint-disable-line @typescript-eslint/no-explicit-any
                    <td key={c.requested} className="px-4 py-2">
                      {c.available ? <Value v={c.values[d]} /> : <span className="text-ink-mute">not available</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-[12px] text-ink-mute">{data?.note}</p>
    </div>
  );
}

function Value({ v }: { v: unknown }) {
  if (v === null || v === undefined) return <span className="text-ink-mute">not stated in sources</span>;
  if (typeof v === "string" && v.startsWith("not applicable")) return <span className="italic text-ink-mute">{v}</span>;
  if (typeof v === "number" || typeof v === "string") return <span>{String(v)}</span>;
  if (Array.isArray(v)) {
    return (
      <ul className="space-y-0.5">
        {v.map((x, i) => (
          <li key={i} className="text-[12px]">
            {typeof x === "object" && x !== null && "movable_joints" in x
              ? `${(x as { length: number }).length} joints → ${(x as { end_link_of_chain: string }).end_link_of_chain}`
              : typeof x === "object" && x !== null && "file" in x
                ? `${(x as { file: string }).file} (${(x as { license: string }).license})`
                : JSON.stringify(x)}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <ul className="space-y-0.5 text-[12px]">
      {Object.entries(v as Record<string, unknown>).map(([k, x]) => <li key={k}><span className="text-ink-mute">{k}:</span> {typeof x === "object" ? JSON.stringify(x) : String(x)}</li>)}
    </ul>
  );
}
