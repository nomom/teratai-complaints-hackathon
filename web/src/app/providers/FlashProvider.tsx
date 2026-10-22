import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

import { Alert, type AlertTone } from '@/components/ui';

interface FlashMessage {
  tone: AlertTone;
  text: string;
  id: number;
}

interface FlashContextValue {
  flash: (tone: AlertTone, text: string) => void;
  clear: () => void;
}

const FlashContext = createContext<FlashContextValue | null>(null);
const MessageContext = createContext<FlashMessage | null>(null);

/** One confirmation at a time ("CMP-00244 approved and the reply was sent."), shown until dismissed or replaced. */
export function FlashProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<FlashMessage | null>(null);
  const flash = useCallback((tone: AlertTone, text: string) => setMessage({ tone, text, id: Date.now() }), []);
  const clear = useCallback(() => setMessage(null), []);
  const value = useMemo(() => ({ flash, clear }), [flash, clear]);
  return (
    <FlashContext.Provider value={value}>
      <MessageContext.Provider value={message}>{children}</MessageContext.Provider>
    </FlashContext.Provider>
  );
}

export function useFlash(): FlashContextValue {
  const context = useContext(FlashContext);
  if (!context) throw new Error('useFlash must be used inside FlashProvider');
  return context;
}

/** Where the current message is drawn: top of the page content, and on the sign-in page. */
export function FlashOutlet() {
  const message = useContext(MessageContext);
  const { clear } = useFlash();
  if (!message) return null;
  return (
    <Alert key={message.id} tone={message.tone} onDismiss={clear}>
      {message.text}
    </Alert>
  );
}
