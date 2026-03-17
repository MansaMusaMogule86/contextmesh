/**
 * ContextMesh JavaScript/TypeScript SDK
 * npm install contextmesh
 *
 * Quick start:
 *   import { Mesh } from "contextmesh";
 *   const mesh = new Mesh("cm_live_your_key");
 *   await mesh.remember("prod DB is postgres 15 on AWS us-east-1");
 *   const results = await mesh.query("what do we know about our database?");
 */

const DEFAULT_BASE = "https://api.contextmesh.dev";

export class ContextMeshError extends Error {
  constructor(message, public statusCode) {
    super(message);
    this.name = "ContextMeshError";
  }
}

export class Mesh {
  private key: string;
  private base: string;
  private headers: Record<string, string>;

  constructor(apiKey: string, baseUrl: string = DEFAULT_BASE) {
    if (!apiKey) throw new ContextMeshError("apiKey is required. Get one at https://contextmesh.dev", 0);
    this.key     = apiKey;
    this.base    = baseUrl.replace(/\/$/, "");
    this.headers = {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    };
  }

  private async _fetch(method: string, path: string, body?: object, params?: Record<string, string>): Promise<any> {
    let url = `${this.base}${path}`;
    if (params) {
      const qs = new URLSearchParams(params).toString();
      if (qs) url += `?${qs}`;
    }
    const res = await fetch(url, {
      method,
      headers: this.headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) throw new ContextMeshError("Invalid API key.", 401);
    if (res.status === 429) {
      const data = await res.json().catch(() => ({}));
      throw new ContextMeshError(`Rate/quota limit exceeded. ${data.detail ?? ""}`, 429);
    }
    if (!res.ok) {
      const text = await res.text();
      throw new ContextMeshError(`API error ${res.status}: ${text}`, res.status);
    }
    return res.json();
  }

  /**
   * Store context. Returns the entry ID.
   * @example
   * const id = await mesh.remember("API rate limit is 1000 req/min");
   * const id = await mesh.remember("Use camelCase for JS", { tags: ["conventions"] });
   */
  async remember(
    text: string,
    opts: { tags?: string[]; sourceAgent?: string; confidence?: number } = {}
  ): Promise<string> {
    const result = await this._fetch("POST", "/remember", {
      text,
      tags:         opts.tags        ?? [],
      source_agent: opts.sourceAgent ?? null,
      confidence:   opts.confidence  ?? 1.0,
    });
    return result.id;
  }

  /**
   * Semantic search. Returns ranked list of context entries.
   * @example
   * const hits = await mesh.query("what do we know about our database?");
   * hits.forEach(h => console.log(h.text, h.score));
   */
  async query(
    q: string,
    opts: { topK?: number; tag?: string; minScore?: number } = {}
  ): Promise<Array<{ id: string; text: string; score: number; tags: string[]; source_agent: string | null; created_at: number }>> {
    const result = await this._fetch("POST", "/query", {
      q,
      top_k:      opts.topK     ?? 5,
      tag_filter: opts.tag      ?? null,
      min_score:  opts.minScore ?? 0.3,
    });
    return result.results;
  }

  /**
   * Delete a context entry by ID.
   */
  async forget(entryId: string): Promise<boolean> {
    await this._fetch("DELETE", `/forget/${entryId}`);
    return true;
  }

  /**
   * Browse stored entries.
   */
  async list(opts: { limit?: number; offset?: number; tag?: string } = {}): Promise<{
    total: number;
    entries: Array<{ id: string; text: string; tags: string[]; created_at: number }>;
  }> {
    const params: Record<string, string> = {
      limit:  String(opts.limit  ?? 50),
      offset: String(opts.offset ?? 0),
    };
    if (opts.tag) params.tag_filter = opts.tag;
    return this._fetch("GET", "/list", undefined, params);
  }

  /**
   * Check plan usage for this month.
   */
  async usage(): Promise<{
    plan: string;
    queries_used: number;
    queries_limit: number;
    entries_stored: number;
    entries_limit: number;
  }> {
    return this._fetch("GET", "/usage");
  }

  /**
   * Bulk store multiple items.
   */
  async rememberMany(
    items: Array<string | { text: string; tags?: string[]; sourceAgent?: string }>
  ): Promise<string[]> {
    return Promise.all(
      items.map(item =>
        typeof item === "string" ? this.remember(item) : this.remember(item.text, item)
      )
    );
  }
}

// CommonJS compat
module.exports = { Mesh, ContextMeshError };
module.exports.default = { Mesh, ContextMeshError };
