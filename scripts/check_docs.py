"""Run the same documentation checks locally and in GitHub Actions."""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        for key in ('id', 'name'):
            if values.get(key):
                self.ids.add(values[key])
        if tag in {'a', 'link'} and values.get('href'):
            self.links.append(values['href'])
        if tag in {'img', 'script', 'source'} and values.get('src'):
            self.links.append(values['src'])


def check_sources() -> list[str]:
    errors = []
    paths = list((ROOT / 'docs').rglob('*.md'))
    paths += [ROOT / 'README.md', ROOT / '.github/pull_request_template.md', ROOT / 'mkdocs.yml']
    for path in paths:
        text = path.read_text(encoding='utf-8')
        if not text.endswith('\n') or text.endswith('\n\n'):
            errors.append(f'{path.relative_to(ROOT)}: use one newline at end of file')
        for number, line in enumerate(text.splitlines(), 1):
            if line != line.rstrip():
                errors.append(f'{path.relative_to(ROOT)}:{number}: trailing whitespace')
            if '\t' in line:
                errors.append(f'{path.relative_to(ROOT)}:{number}: use spaces instead of tabs')
    for path in [ROOT / 'mkdocs.yml', ROOT / 'docs/api/openapi.yaml',
                 ROOT / '.github/workflows/docs.yml']:
        yaml.safe_load(path.read_text())
    return errors


def check_site(site: Path) -> list[str]:
    """Check local files and anchors after MkDocs has rewritten Markdown links."""
    errors = []
    pages = {path.resolve(): Page(path.read_text()) for path in site.rglob('*.html')}
    site = site.resolve()
    config = yaml.safe_load((ROOT / 'mkdocs.yml').read_text())
    base = urlsplit(config.get('site_url', '')).path.rstrip('/')
    for path, page in pages.items():
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc or not url.path and not url.fragment:
                continue
            raw = unquote(url.path)
            if raw.startswith('/'):
                if base and (raw == base or raw.startswith(base + '/')):
                    raw = raw[len(base):]
                target = site / raw.lstrip('/')
            else:
                target = path.parent / raw if raw else path
            target = target.resolve()
            if not target.is_relative_to(site):
                errors.append(f'{path.relative_to(site)}: link escapes the site: {link}')
                continue
            if target.is_dir():
                target /= 'index.html'
            if not target.is_file():
                errors.append(f'{path.relative_to(site)}: missing link target: {link}')
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
                errors.append(f'{path.relative_to(site)}: missing anchor: {link}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-dir', type=Path, default=ROOT / 'site')
    args = parser.parse_args()
    errors = check_sources()
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    node = shutil.which('node')
    if node is None:
        print('Node.js is required for Mermaid validation; install Node.js and run npm ci.', file=sys.stderr)
        return 1
    for command in [
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'scripts', '-p', 'test_docs_checks.py'],
        [node, '--test', 'scripts/test_mermaid.mjs'],
        [sys.executable, '-m', 'pymarkdown', '--config', '.pymarkdown.json', 'scan', '-r', 'docs', 'README.md', '.github/pull_request_template.md'],
        [sys.executable, '-m', 'mkdocs', 'build', '--strict', '--site-dir', str(args.site_dir.resolve())],
        [node, 'scripts/check_mermaid.mjs', str(args.site_dir.resolve())],
    ]:
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    errors = check_site(args.site_dir)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('Documentation checks passed: formatting, Markdown, YAML, Mermaid, strict build, local links and anchors.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
