import { useQueryClient } from '@tanstack/react-query';
import { Send } from 'lucide-react';
import { useState, type FormEvent } from 'react';

import { Alert, Button, Card, PageHeader, Spinner, TextArea, TextField } from '@/components/ui';
import { CustomerStatusBadge } from '@/features/cases/components/Badges';
import * as casesApi from '@/features/cases/api';
import { caseKeys } from '@/features/cases/hooks';
import { waitForWorker } from '@/features/cases/lib/waitForWorker';
import type { CustomerCase } from '@/features/cases/types';

import { Thread } from '../components/Thread';
import styles from '../components/customer.module.css';

type Step =
  | { kind: 'idle' }
  | { kind: 'sending' }
  | { kind: 'waiting'; id: string }
  | { kind: 'done'; id: string; caseItem: CustomerCase | null }
  | { kind: 'error'; message: string };

/** Filed under the customer's own ID, from the app; dated 30 Sep 2026, the last day of the bank's data (API side). */
export function NewComplaintPage() {
  const queryClient = useQueryClient();
  const [subject, setSubject] = useState('');
  const [text, setText] = useState('');
  const [step, setStep] = useState<Step>({ kind: 'idle' });

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    setStep({ kind: 'sending' });
    try {
      const { complaint_id: id } = await casesApi.fileOwnComplaint(text, subject);
      setStep({ kind: 'waiting', id });
      const caseItem = await waitForWorker(() => casesApi.getOwnCase(id));
      await queryClient.invalidateQueries({ queryKey: caseKeys.all });
      setStep({ kind: 'done', id, caseItem });
      setText('');
      setSubject('');
    } catch (e) {
      setStep({ kind: 'error', message: e instanceof Error ? e.message : 'Something went wrong.' });
    }
  }

  return (
    <>
      <PageHeader title="Tell us what went wrong" subtitle="We read every message. Write in English or Bahasa Melayu." />
      <Card className={styles.formCard}>
        <form onSubmit={submit}>
          <TextField label="Subject (optional)" value={subject} onChange={(e) => setSubject(e.target.value)} />
          <TextArea label="What happened? Include the amount, the date and the merchant if you know them." rows={6}
            value={text} onChange={(e) => setText(e.target.value)} />
          <Button type="submit" variant="primary" icon={Send}
            loading={step.kind === 'sending' || step.kind === 'waiting'} disabled={!text.trim()}>
            Send
          </Button>
        </form>
      </Card>
      {step.kind === 'waiting' && <Spinner label={`Received as ${step.id}. Checking your case...`} />}
      {step.kind === 'error' && <Alert tone="error">{step.message}</Alert>}
      {step.kind === 'done' && (
        <>
          <Alert tone="success">{`Thanks, we've received your complaint (${step.id}).`}</Alert>
          {step.caseItem ? (
            <Card>
              <p className={styles.meta}>
                <strong>{step.caseItem.complaint_id}</strong> <CustomerStatusBadge status={step.caseItem.status} />
              </p>
              <Thread caseItem={step.caseItem} />
            </Card>
          ) : (
            <Alert tone="info">We'll reply under My cases.</Alert>
          )}
        </>
      )}
    </>
  );
}
