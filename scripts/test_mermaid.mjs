import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('./check_mermaid.mjs', import.meta.url));

test('validates Mermaid blocks in generated pages and reports invalid diagrams', async () => {
  const site = await mkdtemp(path.join(tmpdir(), 'mermaid-check-'));
  try {
    await mkdir(path.join(site, 'architecture'));
    const page = path.join(site, 'architecture', 'index.html');
    await writeFile(page, '<pre><code class="language-mermaid">flowchart LR\nA --&gt; B</code></pre>');
    let result = spawnSync(process.execPath, [script, site], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Validated 1 Mermaid diagrams/);

    await writeFile(page, '<pre><code class="language-mermaid">flowchart LR\nA --&gt;</code></pre>');
    result = spawnSync(process.execPath, [script, site], { encoding: 'utf8' });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /architecture[\\/]index\.html: Mermaid diagram 1/);
  } finally {
    await rm(site, { recursive: true, force: true });
  }
});
