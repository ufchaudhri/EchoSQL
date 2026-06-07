import useSWR from 'swr'
import { fetcher } from '../lib/api'

export default function QueryHistory() {
  const { data, error } = useSWR('/history', fetcher)
  if (error) return <div>Error loading history</div>
  if (!data) return <div>Loading...</div>
  return (
    <div>
      <ul>
        {data.map((h: any, i: number) => (
          <li key={i}><strong>{h.nl}</strong> → {h.sql}</li>
        ))}
      </ul>
    </div>
  )
}
