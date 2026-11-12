"""Regression checks for generated-site link validation."""
from pathlib import Path
import tempfile
import unittest

from check_docs import check_site


class SiteLinks(unittest.TestCase):
    def site(self, html):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / 'index.html').write_text(html)
        return root

    def test_relative_paths_and_encoded_anchors(self):
        root = self.site('<a href="guide/#a%20b">Guide</a><img src="image.svg">')
        (root / 'guide').mkdir()
        (root / 'guide/index.html').write_text('<h1 id="a b">Guide</h1>')
        (root / 'image.svg').write_text('<svg/>')
        self.assertEqual(check_site(root), [])

    def test_missing_file_fails(self):
        errors = check_site(self.site('<a href="missing/">Broken link</a>'))
        self.assertTrue(any('missing link target' in error for error in errors))

    def test_missing_anchor_fails(self):
        errors = check_site(self.site('<a href="#missing">Broken anchor</a>'))
        self.assertTrue(any('missing anchor' in error for error in errors))

    def test_missing_script_fails(self):
        errors = check_site(self.site('<script src="missing.js"></script>'))
        self.assertTrue(any('missing link target' in error for error in errors))

    def test_project_base_path(self):
        root = self.site('<a href="/Y4TutorPlatform/#home">Home</a><h1 id="home">Home</h1>')
        self.assertEqual(check_site(root), [])

    def test_external_links_are_not_fetched(self):
        root = self.site('<a href="https://example.invalid/no-network">External</a>')
        self.assertEqual(check_site(root), [])

    def test_link_cannot_escape_output_directory(self):
        errors = check_site(self.site('<a href="../outside.html">Outside</a>'))
        self.assertTrue(any('escapes the site' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
