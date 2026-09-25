> **本仓库没有 MCP 客户端**：下文出现的 `search_papers` / `get_paper_by_id` / `get_citation` /
> `pubmed_lookup_mesh` / `lookup_mesh` 等 MCP 工具名，一律改用 `scripts/lit_bridge.py` 的对应子命令
> （`search` / `paper` / `cite` / `mesh`），零 key、纯标准库，见 `static/core/tools.md`。
# Workflow 3: MeSH Search Strategy

**Purpose:** Build precise PubMed queries from MeSH terms.

## Procedure

1. Use `pubmed_lookup_mesh` to explore terms related to the topic.
2. Show term hierarchy (broader / narrower / related).
3. Construct Boolean query: MeSH terms + keywords.
   See [Query Construction](../search-strategy.md#query-construction) for templates.
4. Optionally spell-check query with `pubmed_spell_check`.
5. Execute via `pubmed_search_articles`.

## Output

Final PubMed query string, result count, and top results.
