"use strict";

function setupCSVUploads() {
  const panel = document.getElementById('academic-csv-upload');
  if (!panel) return;
  for (const kind of ['modules', 'users']) {
    const form = document.getElementById(`csv-${kind}-form`);
    const file = form.elements.file;
    const previewButton = form.querySelector('button[type=submit]');
    const applyButton = document.getElementById(`csv-${kind}-apply`);
    const status = document.getElementById(`csv-${kind}-status`);
    const errors = document.getElementById(`csv-${kind}-errors`);
    const preview = document.getElementById(`csv-${kind}-preview`);
    let approvedFile = null, busy = false;
    function node(tag, text) {
      const item = document.createElement(tag);
      item.textContent = String(text ?? '');
      return item;
    }
    function invalidate() {
      approvedFile = null;
      applyButton.disabled = true;
      status.textContent = '';
      errors.replaceChildren();
      preview.hidden = true;
    }
    file.addEventListener('change', invalidate);
    function display(result) {
      errors.replaceChildren(...(result.errors || []).map(error => node('li', `Row ${error.row}: ${error.message}`)));
      const rows = result.preview || [];
      const columns = rows.length ? Object.keys(rows[0]) : [];
      document.getElementById(`csv-${kind}-columns`).replaceChildren(...columns.map(key => {
        const th = node('th', key.replace(/_/g, ' '));
        th.scope = 'col';
        return th;
      }));
      document.getElementById(`csv-${kind}-rows`).replaceChildren(...rows.map(record => {
        const row = document.createElement('tr');
        row.append(...columns.map(key => node('td', record[key])));
        return row;
      }));
      preview.hidden = !rows.length;
      if (!result.valid) {
        status.textContent = `${result.error_count} row error(s). No records were saved. Fix the file and preview again.`;
        if (result.error_count > 100) status.textContent += ' Showing the first 100 errors.';
      } else {
        const summary = Object.entries(result.summary).map(([key, count]) => `${key.replace(/_/g, ' ')}: ${count}`).join(' · ');
        status.textContent = `${result.applied ? 'Import complete.' : `${result.rows} row(s) validated. Ready to import.`} ${summary}`;
      }
    }
    async function upload(apply) {
      if (busy || !form.reportValidity()) return;
      const selected = file.files[0];
      if (apply && approvedFile !== selected) { invalidate(); return; }
      if (!selected || !selected.name.toLowerCase().endsWith('.csv') || selected.size > 1024 * 1024) {
        invalidate();
        status.textContent = 'Choose a CSV file up to 1 MB.';
        return;
      }
      busy = true;
      approvedFile = null;
      file.disabled = previewButton.disabled = applyButton.disabled = true;
      status.textContent = apply ? 'Importing CSV…' : 'Validating CSV…';
      try {
        const { csrf_token } = await requestJSON('/api/users/auth/csrf');
        const body = new FormData();
        body.append('file', selected);
        body.append('dry_run', apply ? 'false' : 'true');
        const response = await fetch(`/api/colleges/college/${encodeURIComponent(panel.dataset.collegeId)}/academic/import/${kind}`, {
          method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf_token }, body,
        });
        const result = await response.json().catch(() => ({}));
        if (response.status === 422) { display(result); return; }
        if (!response.ok) {
          const error = new Error(result.error || (response.status === 413 ? 'The file is too large.' : 'CSV upload failed. Preview again before retrying.'));
          error.status = response.status;
          throw error;
        }
        display(result);
        if (result.valid && !result.applied) approvedFile = selected;
        if (result.applied) document.dispatchEvent(new Event('academic-data-updated'));
      } catch (error) {
        errors.replaceChildren();
        preview.hidden = true;
        status.textContent = errorMessage(error);
        if (error.status === 401) window.location.replace('/login');
      } finally {
        busy = false;
        file.disabled = previewButton.disabled = false;
        applyButton.disabled = !approvedFile;
      }
    }
    form.addEventListener('submit', event => { event.preventDefault(); return upload(false); });
    applyButton.addEventListener('click', () => upload(true));
  }
}

setupCSVUploads();
