import useSWR from 'swr'
import { fetcher } from '../lib/api'

export default function Admin() {
  const { data } = useSWR('/health', fetcher)
  return (
    <main style={{ padding: 24 }}>
      <h1>Admin / Health</h1>
      <pre>{JSON.stringify(data || { status: 'unknown' }, null, 2)}</pre>
    </main>
  )
}
