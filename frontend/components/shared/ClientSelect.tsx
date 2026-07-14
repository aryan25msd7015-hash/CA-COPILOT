import { Client } from '@/types';

export default function ClientSelect({ clients, value, onChange }: {
  clients: Client[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={event => onChange(event.target.value)}
      className="rounded-lg border bg-white px-3 py-2 text-sm"
    >
      <option value="">Select client</option>
      {clients.map(client => <option key={client.id} value={client.id}>{client.name}</option>)}
    </select>
  );
}
