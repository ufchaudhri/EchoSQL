import { useState } from 'react'

export default function QueryInput({ onSubmit, loading }: any) {
  const [text, setText] = useState('')
  return (
    <div>
      <textarea
        rows={4}
        style={{ width: '100%' }}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Ask a question in natural language..."
      />
      <button onClick={() => onSubmit(text)} disabled={loading || !text}>
        {loading ? 'Running...' : 'Run'}
      </button>
    </div>
  )
}
