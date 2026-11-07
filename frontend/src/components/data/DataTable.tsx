import { flexRender, tableFeatures, useTable, type ColumnDef } from '@tanstack/react-table'

import { Skeleton } from '../ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'

const features = tableFeatures({})
export type DataColumn<T extends object> = ColumnDef<typeof features, T, unknown>

interface DataTableProps<T extends object> {
  columns: DataColumn<T>[]
  data: T[]
  isLoading: boolean
  error?: unknown
  onRetry?: () => void
  emptyTitle: string
  emptyDescription?: string
  onRowClick?: (row: T) => void
  skeletonRows?: number
}

export function DataTable<T extends object>({
  columns,
  data,
  isLoading,
  error,
  onRetry,
  emptyTitle,
  emptyDescription,
  onRowClick,
  skeletonRows = 6,
}: DataTableProps<T>) {
  const table = useTable({ features, data, columns })

  if (error) {
    return <ErrorState error={error} onRetry={onRetry} />
  }

  if (isLoading) {
    return (
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id}>
              {group.headers.map((header) => (
                <TableHead key={header.id}>
                  {flexRender(header.column.columnDef.header, header.getContext())}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {Array.from({ length: skeletonRows }).map((_, rowIndex) => (
            <TableRow key={rowIndex}>
              {columns.map((_col, colIndex) => (
                <TableCell key={colIndex}>
                  <Skeleton className="h-4 w-full max-w-32" />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    )
  }

  if (data.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} />
  }

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((group) => (
          <TableRow key={group.id}>
            {group.headers.map((header) => (
              <TableHead key={header.id}>
                {flexRender(header.column.columnDef.header, header.getContext())}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow
            key={row.id}
            onClick={onRowClick ? () => onRowClick(row.original) : undefined}
            tabIndex={onRowClick ? 0 : undefined}
            onKeyDown={
              onRowClick
                ? (event) => {
                    if (
                      event.target === event.currentTarget &&
                      (event.key === 'Enter' || event.key === ' ')
                    ) {
                      event.preventDefault()
                      onRowClick(row.original)
                    }
                  }
                : undefined
            }
            className={
              onRowClick
                ? 'cursor-pointer focus-visible:outline-2 focus-visible:outline-accent focus-visible:-outline-offset-2'
                : undefined
            }
          >
            {row.getAllCells().map((cell) => (
              <TableCell key={cell.id}>
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
