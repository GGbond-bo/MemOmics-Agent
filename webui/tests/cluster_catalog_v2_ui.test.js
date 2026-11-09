/* V2 key-install regressions are retired: V5 uses encrypted per-user passwords. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
assert.match(html, /MemOmics V5: server \/ node \/ user \/ matched-connection UI/);
assert.doesNotMatch(html, /install_key|装公钥|安装公钥|私钥|key_path|target_password|gateway_password|use_app_managed_key|route_mode|cw-mask/i);
assert.match(html, /id="cluster-cfg" style="display:grid;"/, 'server catalog is visible without a legacy configuration toggle');
assert.doesNotMatch(html, /id="cluster-catalog-tree"|id="cluster-catalog-detail"|id="cluster-server-cards"/);
console.log('cluster_catalog_v2_ui.test.js: PASS (V2 key-install surface retired by V5)');
