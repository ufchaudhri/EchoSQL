document.getElementById('run-btn').addEventListener('click', async () => {
  const sql = document.getElementById('sql-input').value.trim();
  const outputEl = document.getElementById('output');
  if (!sql) { outputEl.textContent = 'Please enter SQL to run.'; return; }
  outputEl.textContent = 'Running...';
  try {
    const res = await fetch('/api/run-sql', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sql })
    });
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    outputEl.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    outputEl.textContent = 'Error: ' + err.message;
  }
});
