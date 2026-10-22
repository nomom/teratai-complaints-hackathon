import { Flag } from 'lucide-react';
import { useState } from 'react';

import { useFlash } from '@/app/providers/FlashProvider';
import { Alert, Button, Popover, TextField } from '@/components/ui';

import { useFlag } from '../hooks';

/** Spot-check: question a case whose reply already went out. Audited for follow-up; changes nothing. */
export function FlagForReview({ caseId }: { caseId: string }) {
  const { flash } = useFlash();
  const flag = useFlag();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');

  async function submit() {
    try {
      await flag.mutateAsync({ id: caseId, note });       // see ReplyActions: survives the panel re-rendering
    } catch {
      return;                                            // flag.error is shown in the popover
    }
    setOpen(false);
    setNote('');
    flash('success', `${caseId} flagged for review.`);
  }

  return (
    <Popover open={open} onOpenChange={setOpen} trigger={<Button icon={Flag}>Flag for review</Button>}>
      {flag.isError && <Alert tone="warning">{flag.error.message}</Alert>}
      <TextField label="What looks wrong?" placeholder="e.g. wrong transaction refunded, reply tone" value={note}
        onChange={(e) => setNote(e.target.value)} autoFocus />
      <Button variant="primary" icon={Flag} onClick={submit} loading={flag.isPending} disabled={!note.trim()}>
        Flag
      </Button>
    </Popover>
  );
}
