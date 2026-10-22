import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { installFakeApi } from '@/test/fakeApi';
import { renderApp } from '@/test/renderApp';

describe('a customer', () => {
  it('sees their own case as being reviewed, never the unsent draft', async () => {
    const api = installFakeApi();
    api.signUp('CUS-02394', 'secret1');
    const { user } = renderApp('/my-cases', { as: 'CUS-02394' });
    expect(await screen.findByRole('heading', { name: 'My cases (1)' })).toBeInTheDocument();
    expect(screen.getByText('Being reviewed')).toBeInTheDocument();
    await user.click(screen.getByText('CMP-P1'));
    expect(await screen.findByText("Our team is reviewing your case. We'll reply here.")).toBeInTheDocument();
    expect(screen.queryByText('Draft reply for CMP-P1')).not.toBeInTheDocument();
    expect(screen.queryByText('CMP-P3')).not.toBeInTheDocument();
  });

  it('is invited to file a complaint when they have none', async () => {
    const api = installFakeApi();
    api.signUp('CUS-00996', 'secret1');
    renderApp('/my-cases', { as: 'CUS-00996' });
    expect(await screen.findByText('You have no complaints with us')).toBeInTheDocument();
    expect(screen.getByText('Use New complaint to tell us what went wrong.')).toBeInTheDocument();
  });
});
