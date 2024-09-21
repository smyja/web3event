import { MantineProvider } from '@mantine/core';
import { LogTerminal } from './components/LogTerminal';
import { theme } from './theme';
import '@mantine/core/styles.css';
export default function App() {
  return (
    <MantineProvider   theme={theme}>
      <LogTerminal />
    </MantineProvider>
  );
}