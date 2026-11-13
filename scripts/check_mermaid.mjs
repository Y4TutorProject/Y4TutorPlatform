import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { JSDOM } from 'jsdom';

const site = process.argv[2];
if (!site) {
  console.error('Usage: node scripts/check_mermaid.mjs <site-directory>');
  process.exit(1);
}

const dom = new JSDOM('');
globalThis.window = dom.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });

const { default: mermaid } = await import('mermaid');
mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });

async function* htmlFiles(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const name = path.join(directory, entry.name);
    if (entry.isDirectory()) yield* htmlFiles(name);
    else if (entry.isFile() && name.endsWith('.html')) yield name;
  }
}

let count = 0;
let failed = false;
for await (const file of htmlFiles(site)) {
  const page = new JSDOM(await readFile(file, 'utf8'));
  const diagrams = page.window.document.querySelectorAll('pre > code.language-mermaid');
  for (const [index, diagram] of diagrams.entries()) {
    count++;
    try {
      await mermaid.parse(diagram.textContent);
    } catch (error) {
      failed = true;
      console.error(`${path.relative(site, file)}: Mermaid diagram ${index + 1}: ${error.message}`);
    }
  }
  page.window.close();
}

dom.window.close();
if (failed) process.exitCode = 1;
else console.log(`Validated ${count} Mermaid diagrams.`);
