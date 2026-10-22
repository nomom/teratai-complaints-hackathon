import { clsx } from 'clsx';

import { money, nice } from '@/lib/format';

import { slaLeft, slaText } from '../lib/sla';
import { STATUS } from '../lib/status';
import type { CaseRow } from '../types';
import styles from './QueueTable.module.css';

export type Column = 'priority' | 'case' | 'refund' | 'sla' | 'category' | 'outcome' | 'status' | 'checked' | 'updated';

const HEADERS: Record<Column, string> = {
  priority: 'Priority',
  case: 'Case',
  refund: 'Refund (RM)',
  sla: 'SLA',
  category: 'Category',
  outcome: 'Outcome',
  status: 'Status',
  checked: 'Reply checked',
  updated: 'Updated',
};

function cell(row: CaseRow, column: Column, now: Date) {
  switch (column) {
    case 'priority':
      return row.priority ?? '-';
    case 'case':
      return row.complaint_id;
    case 'refund':
      return row.refund_amount_myr === null ? '-' : money(row.refund_amount_myr).replace('RM ', '');
    case 'sla':
      return slaText(slaLeft(row, now));
    case 'category':
      return nice(row.category);
    case 'outcome':
      return nice(row.outcome);
    case 'status':
      return STATUS[row.status]?.label ?? row.status;
    case 'checked':
      return row.check_ok ? 'yes' : 'NO';
    case 'updated':
      return row.updated_at;
  }
}

interface QueueTableProps {
  rows: CaseRow[];
  columns: Column[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  caption: string;
}

/** Each row is one button-like control (Enter or Space opens the case); the open case is marked aria-selected. */
export function QueueTable({ rows, columns, selectedId, onSelect, caption }: QueueTableProps) {
  const now = new Date();
  return (
    <div className={styles.frame}>
      <table className={styles.table} aria-label={caption}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col" className={clsx(column === 'refund' && styles.number)}>
                {HEADERS[column]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const selected = row.complaint_id === selectedId;
            return (
              <tr key={row.complaint_id} className={clsx(styles.row, selected && styles.selected)}
                aria-selected={selected} tabIndex={0} onClick={() => onSelect(row.complaint_id)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onSelect(row.complaint_id);
                  }
                }}>
                {columns.map((column) => (
                  <td key={column} className={clsx(column === 'refund' && styles.number, column === 'case' && styles.id)}>
                    {cell(row, column, now)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
