// Keep Mermaid sources readable if the CDN is unavailable.
document.addEventListener('DOMContentLoaded', () => {
  if (!window.mermaid) return;
  document.querySelectorAll('pre > code.language-mermaid').forEach(code => {
    const diagram = document.createElement('div');
    diagram.className = 'mermaid';
    diagram.tabIndex = 0;
    diagram.setAttribute('role', 'region');
    diagram.setAttribute('aria-label', 'Scrollable diagram');
    diagram.textContent = code.textContent;
    code.parentElement.replaceWith(diagram);
  });
  window.mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'neutral' });
  window.mermaid.run().then(() => {
    document.querySelectorAll('.mermaid svg').forEach(svg => {
      // Preserve the diagram's text size; wide diagrams scroll inside the page.
      svg.style.width = `${svg.viewBox.baseVal.width}px`;
      svg.style.maxWidth = 'none';
      svg.style.height = 'auto';
    });
  });
});
