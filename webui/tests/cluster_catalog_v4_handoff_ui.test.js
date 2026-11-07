/* V5 handoff: the accordion owns the catalog surface and legacy renderers are absent. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map((match) => match[1]);
const v5 = scripts.find((source) => source.includes('MemOmics V5: server / node / user / matched-connection UI'));
assert.ok(v5, 'V5 owns the catalog feature script');
assert.doesNotMatch(html, /MemOmics V4: server \/ node \/ user \/ matched-connection UI|cluster-catalog-editor|_mmCatalog(OpenForm|RenderDetail|TreeRow|Prompt)/);
assert.match(v5, /gateway_profile_id/, 'V5 supports a narrow gateway-account choice only when required');
assert.doesNotMatch(v5, /route_mode|target_password|gateway_password|key_path|use_app_managed_key/);
assert.match(html, /id="cluster-catalog-add-server"/);
assert.doesNotMatch(html, /id="cluster-catalog-add-server"[^>]*onclick=/, 'Add server has no inline handler');
assert.equal((html.match(/clusterCatalogCreateServerV5/g) || []).length, 1, 'only one V5 create-server entrypoint remains');
console.log('cluster_catalog_v4_handoff_ui.test.js: PASS (V5 owns the catalog handoff)');
