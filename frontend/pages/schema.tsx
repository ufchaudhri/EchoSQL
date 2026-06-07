import useSWR from 'swr'
import { fetcher } from '../lib/api'

export default function Schema() {
  const { data, error } = useSWR('/schema', fetcher)
  if (error) return <div>Error loading schema</div>
  if (!data) return <div>Loading...</div>
  return (
    <main style={{ padding: 24 }}>
      <h1>Database Schema</h1>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </main>
  )
}
