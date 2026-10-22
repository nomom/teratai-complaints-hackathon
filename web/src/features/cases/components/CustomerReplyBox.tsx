import { Send } from 'lucide-react';
import { useState } from 'react';

import { useQueryClient } from '@tanstack/react-query';

import { useFlash } from '@/app/providers/FlashProvider';
import { Alert, Button, TextArea } from '@/components/ui';

import * as casesApi from '../api';
import { caseKeys } from '../hooks';
import { waitForWorker } from '../lib/waitForWorker';

interface CustomerReplyBoxProps {
  caseId: string;
  updatedAt: string;
  label: string;
  doneText: string;
}

/** Answer the follow-up question, then wait for the worker to reprocess the case. Staff use it to play the customer. */
export function CustomerReplyBox({ caseId, updatedAt, label, doneText }: CustomerReplyBoxProps) {
  const queryClient = useQueryClient();
  const { flash } = useFlash();
  const [text, setText] = useState('');
  const [state, setState] = useState<'idle' | 'sending' | 'late' | 'error'>('idle');
  const [error, setError] = useState('');

  async function send() {
    setState('sending');
    try {
      await casesApi.sendCustomerReply(caseId, text);
      const after = await waitForWorker(() => casesApi.getOwnCase(caseId), updatedAt);
      await queryClient.invalidateQueries({ queryKey: caseKeys.all });
      if (after) {
        flash('success', doneText);
        setText('');
        setState('idle');
      } else {
        setState('late');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
      setState('error');
    }
  }

  return (
    <div>
      <TextArea label={label} rows={4} value={text} onChange={(e) => setText(e.target.value)} />
      {state === 'late' && <Alert tone="warning">Not processed yet. Is the worker (python -m app.worker) running?</Alert>}
      {state === 'error' && <Alert tone="error">{error}</Alert>}
      <Button variant="primary" icon={Send} onClick={send} loading={state === 'sending'} disabled={!text.trim()}>
        Send reply
      </Button>
    </div>
  );
}
