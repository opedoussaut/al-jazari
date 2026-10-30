// Typed client for the JAZARI API (/api/v1). Types mirror backend/jazari/intelligence/schemas.py.

export type EvidenceType = "extracted" | "derived" | "inferred" | "document" | "ontology" | "validation";

export interface Evidence {
  id: string;
  label: string;
  evidence_type: EvidenceType;
  url?: string | null;
  source?: string | null;
  detail?: string | null;
}

export interface TraceStep {
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  error?: string | null;
  query_name?: string | null;
  queries: string[];
  row_count: number;
  derivations: string[];
  duration_ms: number;
}

export interface ChatResponse {
  session_id: string;
  question: string;
  answer: string;
  planner: "llm" | "rules";
  composer: "llm" | "template";
  model?: string | null;
  context: { configuration?: string | null; configuration_label?: string | null; source_revision?: string | null; ontology_terms: string[] };
  trace: TraceStep[];
  evidence: Evidence[];
  verification: { numbers_checked: number; unsupported_numbers: string[]; removed_citations: string[]; note?: string | null };
  latency_ms: number;
  warnings: string[];
}

export interface Health {
  status: string;
  version: string;
  graph: { triples: number; reference_ontologies: string[]; jazari_ontology: string[]; knowledge_graphs: string[] };
  documents_indexed: number;
  llm: { reachable: boolean; url: string; model: string; model_installed?: boolean; version?: string; error?: string };
}

export interface RobotSummary {
  id: string;
  name: string;
  manufacturer: string;
  category: string;
  homepage?: string;
  configurations: { id: string; label: string; native_name: string; baseline: boolean }[];
}

export interface JointRow {
  joint: string; name: string; class: string; dof: number; parent: string | null; child: string;
  axis: string | null; mentions: string; actuator: string | null;
}

export interface QuantityRow {
  name: string; property: string; value: number; unit: string; format: string; line: number | null;
  attribute: string | null; evidence: string; fileUrl: string;
}

export interface TreeNode {
  link: string;
  joint?: string; class?: string; dof?: number; axis?: string | null; actuated?: boolean;
  children: TreeNode[];
}

export interface Components {
  configuration: { id: string; label: string; robot: string; uri: string };
  joints: JointRow[];
  joint_quantities: QuantityRow[];
  kinematics: { root: string; roots: string[]; tree: TreeNode; trees: TreeNode[]; chains: string[][] };
  links: { name: string; format: string; line: number; mass: number | null }[];
  actuators: { name: string; type: string; joint: string; format: string; line: number; fileUrl: string }[];
  sensors: { name: string; type: string; link: string | null; detail?: string | null; format: string; line: number; fileUrl: string }[];
}

export interface OntologyTerm {
  id: string; label: string; kind: string; origin: string; parents: string[]; has_definition: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  robots: () => request<RobotSummary[]>("/robots"),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  robot: (id: string) => request<any>(`/robots/${encodeURIComponent(id)}`),
  components: (id: string) => request<Components>(`/robots/${encodeURIComponent(id)}/components`),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  validation: (id: string) => request<any>(`/robots/${encodeURIComponent(id)}/validation`),
  classes: (q?: string) => request<OntologyTerm[]>(`/ontology/classes${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  term: (id: string) => request<any>(`/ontology/classes/${encodeURIComponent(id)}`),
  chat: (question: string, session_id?: string) =>
    request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify({ question, session_id }) }),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  compare: (configurations: string[]) => request<any>("/compare", { method: "POST", body: JSON.stringify({ configurations }) }),
};
