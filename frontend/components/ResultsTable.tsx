export default function ResultsTable({ data, sql, error }: any) {
  if (error) return <div style={{ color: 'red' }}>Error: {String(error)}</div>
  if (!data) return <div>No results</div>
  return (
    <div style={{ marginTop: 16 }}>
      <details>
        <summary>Generated SQL</summary>
        <pre>{sql}</pre>
      </details>
      <table border={1} cellPadding={6} style={{ marginTop: 12 }}>
        <thead>
          <tr>
            {Object.keys(data[0] || {}).map((k) => (
              <th key={k}>{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row: any, i: number) => (
            <tr key={i}>
              {Object.values(row).map((v: any, j: number) => (
                <td key={j}>{String(v)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
