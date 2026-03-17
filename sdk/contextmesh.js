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
  constructor(message, statusCode) {
    super(message);
    this.name = "ContextMeshError";
    this.statusCode = statusCode;
  }
}

export class Mesh {
  constructor(apiKey, baseUrl) {
    if (!apiKey) throw new ContextMeshError("apiKey is required. Get one at https://contextmesh.dev", 0);
    this.key     = apiKey;
    this.base    = (baseUrl || DEFAULT_BASE).replace(/\/$/, "");
    this.headers = {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    };
  }

  async _fetch(method, path, body, params) {
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
  async remember(text, opts = {}) {
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
  async query(q, opts = {}) {
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
  async forget(entryId) {
    await this._fetch("DELETE", `/forget/${entryId}`);
    return true;
  }

  /**
   * Browse stored entries.
   */
  async list(opts = {}) {
    const params = {
      limit:  String(opts.limit  ?? 50),
      offset: String(opts.offset ?? 0),
    };
    if (opts.tag) params.tag_filter = opts.tag;
    return this._fetch("GET", "/list", undefined, params);
  }

  /**
   * Check plan usage for this month.
   */
  async usage() {
    return this._fetch("GET", "/usage");
  }

  /**
   * Bulk store multiple items.
   */
  async rememberMany(items) {
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
