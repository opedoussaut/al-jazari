import { useEffect, useState } from "react";
import { api, type Health } from "./api";
import AskPage from "./pages/AskPage";
import RobotsPage from "./pages/RobotsPage";
import OntologyPage from "./pages/OntologyPage";
import ComparePage from "./pages/ComparePage";

const PAGES = [
  { id: "ask", label: "Ask JAZARI" },
  { id: "robots", label: "Explore Robots" },
  { id: "ontology", label: "Explore Ontologies" },
  { id: "compare", label: "Compare Robots" },
] as const;
type PageId = (typeof PAGES)[number]["id"];

function currentPage(): PageId {
  const h = window.location.hash.replace("#/", "").split("?")[0];
  return (PAGES.find((p) => p.id === h)?.id ?? "ask") as PageId;
}

export default function App() {
  const [page, setPage] = useState<PageId>(currentPage());
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    const onHash = () => setPage(currentPage());
    window.addEventListener("hashchange", onHash);
    api.health().then(setHealth).catch((e) => setHealthError(String(e.message ?? e)));
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <div className="flex h-full flex-col">
      <header className="sticky top-0 z-20 border-b border-line bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-5">
          <a href="#/ask" className="flex items-center gap-2">
            <img src="/favicon.svg" alt="" className="h-7 w-7" />
            <span className="text-[17px] font-semibold tracking-tight">JAZARI</span>
            <span className="hidden text-sm text-ink-mute md:inline">Your Robotics AI Expert</span>
          </a>
          <nav className="flex flex-1 gap-1 overflow-x-auto">
            {PAGES.map((p) => (
              <a key={p.id} href={`#/${p.id}`}
                 className={`whitespace-nowrap rounded-full px-3 py-1.5 text-sm transition ${
                   page === p.id ? "bg-navy-soft font-medium text-navy" : "text-ink-soft hover:bg-mist"}`}>
                {p.label}
              </a>
            ))}
          </nav>
          <StatusDot health={health} error={healthError} />
        </div>
      </header>
      <main className="flex-1">
        {page === "ask" && <AskPage health={health} />}
        {page === "robots" && <RobotsPage />}
        {page === "ontology" && <OntologyPage />}
        {page === "compare" && <ComparePage />}
      </main>
    </div>
  );
}

function StatusDot({ health, error }: { health: Health | null; error: string | null }) {
  const llmOk = health?.llm.reachable && health.llm.model_installed;
  const color = error ? "bg-red-500" : !health ? "bg-gray-300" : llmOk ? "bg-emerald-500" : "bg-amber-500";
  const title = error
    ? `Backend unreachable: ${error}`
    : !health ? "Connecting…"
    : `${health.graph.triples.toLocaleString()} triples · ${health.graph.knowledge_graphs.length} robot graph(s) · ` +
      (llmOk ? `LLM ${health.llm.model}` : `LLM unavailable (${health.llm.model}) - deterministic answers only`);
  return (
    <div className="flex items-center gap-2 text-xs text-ink-mute" title={title}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      <span className="hidden lg:inline">{health ? (llmOk ? health.llm.model : "no LLM") : error ? "offline" : "…"}</span>
    </div>
  );
}
