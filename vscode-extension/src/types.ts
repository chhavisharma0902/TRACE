// Shapes of the backend responses (see backend/README.md). IDs look like "src/app.py::Flask.run".

export interface HealthInfo {
  status: 'ok' | 'degraded';
  mode: 'real' | 'mock' | 'unavailable';
  error: string | null;
  nodes: number | null;
  resolver_loaded: boolean;
  resolver_error: string | null;
  llm_configured: boolean;
}

export interface Recommendation {
  function_id: string;
  score: number;
  via_call: boolean;
  via_cochange: boolean;
}

export interface RecommendResponse {
  function_id: string | null;
  recommendations: Recommendation[];
}

export interface EgoEdge {
  source: string;
  target: string;
  edge_type: 'call' | 'cochange';
  count: number;
}

export interface EgoGraphResponse {
  center: string | null;
  nodes: string[];
  edges: EgoEdge[];
  truncated: boolean;
  total_nodes: number;
  total_edges: number;
}

export interface SuggestFixResponse {
  function_id: string;
  suggestion: string;
  auto_apply: false;
  model: string;
  related_functions: string[];
}

// What the sidebar webview renders.
export type BackendState =
  | { status: 'checking' }
  | { status: 'offline'; message: string }
  | {
      status: 'online';
      mode: HealthInfo['mode'];
      nodes: number | null;
      resolverLoaded: boolean;
      llmConfigured: boolean;
      warning?: string;
    };

export interface TargetInfo {
  filePath: string; // workspace-relative, forward slashes
  line: number; // 1-based, as the backend expects
  title: string; // friendly label
  subtitle: string;
}

export interface RecRow {
  id: string;
  title: string;
  subtitle: string;
  score: number;
  pct: number; // 0-100 for the score bar
  viaCall: boolean;
  viaCochange: boolean;
}

export interface GraphNode {
  id: string;
  label: string;
  file: string;
  isCenter: boolean;
}

export interface GraphEdge {
  from: string;
  to: string;
  type: 'call' | 'cochange';
  count: number;
}

export interface GraphData {
  center: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  totalNodes: number;
}

export interface SuggestionView {
  status: 'loading' | 'ready' | 'nochange' | 'advice' | 'error';
  functionId: string;
  title: string;
  subtitle: string;
  message?: string;
  explanation?: string;
  diff?: string;
  canApply?: boolean;
  cantApplyReason?: string;
}

export interface ViewState {
  backend: BackendState;
  target?: TargetInfo;
  rows?: RecRow[];
  loading?: boolean;
  suggestion?: SuggestionView;
  graph?: GraphData;
  graphNotice?: string;
  notice?: string; // friendly message instead of the table (outside a function, error, ...)
}
