'use client';

import { useMemo } from 'react';
import { AgGridReact } from 'ag-grid-react';
import type { ColDef } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-alpine.css';

export default function DataGrid<T extends object>({
  rows,
  columns,
  pageSize = 20,
  pagination = true,
}: {
  rows: T[];
  columns: ColDef<T>[];
  pageSize?: number;
  pagination?: boolean;
}) {
  const defaultColDef = useMemo<ColDef<T>>(() => ({
    sortable: true,
    filter: true,
    resizable: true,
    flex: 1,
    minWidth: 120,
  }), []);

  return (
    <div className="ag-theme-alpine apple-grid w-full overflow-hidden rounded-2xl border border-slate-200/70 bg-white/80 shadow-sm" style={{ minHeight: 180 }}>
      <AgGridReact<T>
        rowData={rows}
        columnDefs={columns}
        defaultColDef={defaultColDef}
        domLayout="autoHeight"
        pagination={pagination}
        paginationPageSize={pageSize}
        overlayNoRowsTemplate="<span class='text-sm text-gray-500'>No records found.</span>"
      />
    </div>
  );
}
