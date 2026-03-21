/**
 * ContextMesh JS SDK — ESM module
 * import { Mesh } from "contextmesh"
 */

const DEFAULT_BASE = "https://contextmesh.dev";

export class ContextMeshError extends Error {
  constructor(message, statusCode) {
    super(message);
    this.name = "ContextMeshError";
    this.statusCode = statusCode;
  }
}

export class Mesh {
  #key;
  #base;
  #headers;

  constructor(apiKey, baseUrl = DEFAULT_BASE) {
    if (!apiKey) throw new ContextMeshError("apiKey is required. Get one at https://contextmesh.dev", 0);
    this.#key     = apiKey;
    this.#base    = baseUrl.replace(/\/$/, "");
    this.#headers = {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    };
  }

  async #fetch(method, path, body, params) {
    let url = `${this.#base}${path}`;
    if (params) {
      const qs = new URLSearchParams(params).toString();
      if (qs) url += `?${qs}`;
    }
    const res = await fetch(url, {
      method,
      headers: this.#headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 401) throw new ContextMeshError("Invalid API key.", 401);
    if (res.status === 429) {
      const data = await res.json().catch(() => ({}));
      throw new ContextMeshError(`Rate/quota limit exceeded. ${data.detail ?? ""}`, 429);
    }
    if (!res.ok) throw new ContextMeshError(`API error ${res.status}: ${await res.text()}`, res.status);
    return res.json();
  }

  /** Store context. Returns entry ID. */
  async remember(text, { tags = [], sourceAgent = null, confidence = 1.0 } = {}) {
    const r = await this.#fetch("POST", "/remember", { text, tags, source_agent: sourceAgent, confidence });
    return r.id;
  }

  /** Semantic search. Returns ranked results. */
  async query(q, { topK = 5, tag = null, minScore = 0.3 } = {}) {
    const r = await this.#fetch("POST", "/query", { q, top_k: topK, tag_filter: tag, min_score: minScore });
    return r.results;
  }

  /** Delete a context entry by ID. */
  async forget(entryId) {
    await this.#fetch("DELETE", `/forget/${entryId}`);
    return true;
  }

  /** Browse stored entries. */
  async list({ limit = 50, offset = 0, tag = null } = {}) {
    const params = { limit: String(limit), offset: String(offset) };
    if (tag) params.tag_filter = tag;
    return this.#fetch("GET", "/list", undefined, params);
  }

  /** Check plan usage. */
  async usage() {
    return this.#fetch("GET", "/usage");
  }

  /** Bulk store. */
  async rememberMany(items) {
    return Promise.all(
      items.map(item => typeof item === "string" ? this.remember(item) : this.remember(item.text, item))
    );
  }

  toString() { return `Mesh(key=...${this.#key.slice(-6)}, base=${this.#base})`; }
}

export default { Mesh, ContextMeshError };
