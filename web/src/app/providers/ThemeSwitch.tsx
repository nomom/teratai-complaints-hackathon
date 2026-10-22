import { Moon } from 'lucide-react';

import { Switch } from '@/components/ui';

import { useTheme } from './ThemeProvider';

export function ThemeSwitch() {
  const { theme, setTheme } = useTheme();
  return (
    <Switch label="Dark mode" icon={Moon} checked={theme === 'dark'}
      onCheckedChange={(dark) => setTheme(dark ? 'dark' : 'light')} />
  );
}
