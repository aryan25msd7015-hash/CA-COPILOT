'use client';
import { useMemo, useRef } from 'react';
import { AgGridReact } from 'ag-grid-react';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import HealthBadge from './HealthBadge';
import { Client } from '@/types';

interface ClientTableProps {
  clients: Client[];
  onClientClick?: (client: Client) => void;
}

export default function ClientTable({ clients, onClientClick }: ClientTableProps) {
  const gridRef = useRef(null);

  const columnDefs = useMemo<ColDef<Client>[]>(() => [
    {
      field: 'name',
      headerName: 'Client Name',
      flex: 2,
      sortable: true,
      filter: true,
    },
    {
      field: 'gstin',
      headerName: 'GSTIN',
      flex: 1.5,
      sortable: true,
      filter: true,
    },
    {
      field: 'health_score',
      headerName: 'Health Score',
      flex: 1.5,
      sortable: true,
      sort: 'asc',
      cellRenderer: (params: ICellRendererParams<Client, number>) => (
        <div className="flex items-center h-full">
          <HealthBadge score={params.value ?? 100} size="sm" />
        </div>
      ),
    },
    {
      field: 'industry',
      headerName: 'Industry',
      flex: 1,
      sortable: true,
      filter: true,
    },
    {
      field: 'whatsapp_number',
      headerName: 'WhatsApp',
      flex: 1,
    },
    {
      headerName: '',
      width: 90,
      cellRenderer: (params: ICellRendererParams<Client>) => (
        <button
          onClick={() => params.data && onClientClick?.(params.data)}
          className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-300 outline-none transition hover:text-cyan-200"
        >
          View →
        </button>
      ),
    },
  ], [onClientClick]);

  return (
    <div className="ag-theme-alpine apple-grid w-full" style={{ minHeight: 300 }} data-testid="client-table">
      <AgGridReact<Client>
        ref={gridRef}
        rowData={clients}
        columnDefs={columnDefs}
        defaultColDef={{ resizable: true }}
        domLayout="autoHeight"
        pagination
        paginationPageSize={20}
      />
    </div>
  );
}
