import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { installFakeApi, makeCase } from '@/test/fakeApi';
import { renderApp } from '@/test/renderApp';

import { readable } from '../lib/audit';

const cases = () => [
  makeCase('CMP-A', { audit: [
    { ts: '2026-10-22 10:00:00', actor: 'agent', action: 'decided', detail: '{"route": "HUMAN_APPROVAL"}' },
    { ts: '2026-10-22 11:00:00', actor: 'officer1', action: 'rejected', detail: 'wrong transaction' },
  ] }),
  makeCase('CMP-B', { route: 'FRAUD_TEAM', status: 'FRAUD_QUEUE', audit: [
    { ts: '2026-10-22 10:05:00', actor: 'agent', action: 'decided', detail: '{}' },
    { ts: '2026-10-22 12:00:00', actor: 'fraud1', action: 'holding_reply_sent', detail: 'as drafted' },
  ] }),
];

const rows = () => within(screen.getByRole('table', { name: 'Audit log, newest first' })).getAllByRole('row').slice(1);

describe('audit log', () => {
  it("lists people's actions across every case, newest first", async () => {
    installFakeApi(cases());
    renderApp('/audit', { as: 'manager1' });
    expect(await screen.findByRole('heading', { name: 'Audit log' })).toBeInTheDocument();
    await screen.findByRole('table', { name: 'Audit log, newest first' });
    // people only by default: the agent's own entries are left out
    expect(rows().map((r) => within(r).getAllByRole('cell')[2].textContent)).toEqual(['fraud1', 'officer1']);
  });

  it('shows the agent too when "people only" is switched off, and opens a case', async () => {
    installFakeApi(cases());
    const { user } = renderApp('/audit', { as: 'manager1' });
    await screen.findByRole('table', { name: 'Audit log, newest first' });
    await user.click(screen.getByRole('switch', { name: /People only/ }));
    expect(await screen.findAllByRole('cell', { name: 'agent' })).toHaveLength(2);
    await user.click(screen.getByRole('cell', { name: 'wrong transaction' }));
    expect(await screen.findByRole('article', { name: 'Case CMP-A' })).toBeInTheDocument();
  });

  it('filters by case', async () => {
    installFakeApi(cases());
    const { user } = renderApp('/audit', { as: 'manager1' });
    await screen.findByRole('table', { name: 'Audit log, newest first' });
    await user.type(screen.getByRole('searchbox', { name: 'Case' }), 'CMP-B');
    expect(await screen.findByText('1 entry')).toBeInTheDocument();
    expect(within(rows()[0]).getAllByRole('cell')[1]).toHaveTextContent('CMP-B');
  });

  it('is for the manager only', async () => {
    installFakeApi(cases());
    const { router } = renderApp('/audit', { as: 'officer1' });
    expect(await screen.findByRole('heading', { name: /Approval queue/ })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/approval');
  });

  it('turns JSON details into one readable line', () => {
    expect(readable('{"action": "reject", "actor": "officer1", "reason": "duplicate", "reply_text": "long"}'))
      .toBe('action: reject · actor: officer1 · reason: duplicate');
    expect(readable('as drafted')).toBe('as drafted');
  });
});
