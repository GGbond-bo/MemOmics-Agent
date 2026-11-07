/* Keep all inline scripts parseable after the V5 catalog UI is added. */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map((match) => match[1]);
assert.ok(scripts.length >= 4, 'the delivered page retains at least four independently parseable inline scripts');
for (const [index, source] of scripts.entries()) {
  try { new Function(source); } catch (error) { throw new Error(`inline script ${index + 1} does not parse: ${error.message}`); }
}
assert.ok(scripts.some((source) => source.includes('MemOmics V5: server / node / user / matched-connection UI')), 'V5 schema-2 UI script is included in the parse set');
console.log(`inline_scripts_v4_parse.test.js: PASS (${scripts.length} inline scripts)`);
