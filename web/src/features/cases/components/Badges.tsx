import { Badge } from '@/components/ui';

import { slaText } from '../lib/sla';
import { CUSTOMER_STATUS, PRIORITY, SLA_ICON, STATUS } from '../lib/status';
import type { CaseStatus } from '../types';

export function StatusBadge({ status }: { status: CaseStatus }) {
  const style = STATUS[status];
  return style ? (
    <Badge tone={style.tone} icon={style.icon}>
      {style.label}
    </Badge>
  ) : (
    <Badge tone="neutral">{status}</Badge>
  );
}

export function CustomerStatusBadge({ status }: { status: CaseStatus }) {
  const style = CUSTOMER_STATUS[status] ?? CUSTOMER_STATUS.PENDING_APPROVAL;
  return (
    <Badge tone={style.tone} icon={style.icon}>
      {style.label}
    </Badge>
  );
}

export function PriorityBadge({ priority }: { priority: string | null }) {
  const style = PRIORITY[priority ?? ''];
  return style ? (
    <Badge tone={style.tone} icon={style.icon}>
      {style.label}
    </Badge>
  ) : null;
}

export function SlaBadge({ left }: { left: number | null }) {
  const tone = left === null ? 'neutral' : left < 0 ? 'error' : left < 3600000 ? 'warning' : 'neutral';
  return (
    <Badge tone={tone} icon={SLA_ICON}>
      SLA {slaText(left)}
    </Badge>
  );
}
