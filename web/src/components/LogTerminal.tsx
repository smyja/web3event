import React, { useState, useEffect, useRef } from 'react';
import { Box, Text, ScrollArea, Title, useMantineTheme, Button, TextInput, Select, Group } from '@mantine/core';
import { Terminal } from 'tabler-icons-react';

interface Log {
  timestamp: string;
  level: string;
  message: string;
}

export const LogTerminal: React.FC = () => {
  const [logs, setLogs] = useState<Log[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [city, setCity] = useState('');
  const [tags, setTags] = useState('');
  const [taskId, setTaskId] = useState('');
  const [isScrapingStarted, setIsScrapingStarted] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const theme = useMantineTheme();
  const wsRef = useRef<WebSocket | null>(null);

  const connectWebSocket = () => {
    const ws = new WebSocket('ws://localhost:8000/ws');

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.log) {
        setLogs(prevLogs => [...prevLogs, data.log]);
      }
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
      setTimeout(connectWebSocket, 5000); // Try to reconnect after 5 seconds
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      ws.close();
    };

    wsRef.current = ws;
  };

  useEffect(() => {
    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTo({ top: scrollAreaRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [logs]);

  const handleStartScraping = async () => {
    try {
      setIsScrapingStarted(true);
      setLogs([]); // Clear previous logs
      const response = await fetch('http://localhost:8000/scrape', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          city,
          tags: tags.split(',').map(tag => tag.trim()),
        }),
      });
      const data = await response.json();
      setTaskId(data.task_id);
    } catch (error) {
      console.error('Error starting scraping:', error);
      setIsScrapingStarted(false);
    }
  };

  return (
    <Box style={{ height: '100vh', backgroundColor: theme.colors.dark[8], padding: theme.spacing.md }}>
<Box style={{ display: 'flex', alignItems: 'center', marginBottom: theme.spacing.md }}>
  <Terminal size={24} strokeWidth={2} color={theme.colors.blue[6]} />
  <Title order={3} ml="sm" c={theme.colors.gray[0]}>EventBrite Scraper Logs</Title>
  <Text ml="auto" c={isConnected ? theme.colors.green[6] : theme.colors.red[6]}>
    {isConnected ? 'Connected' : 'Disconnected'}
  </Text>
</Box>

      
      <Group justify='space-between' mb="md">
        <Select
          data={[
            { value: 'ny--new-york', label: 'New York' },
            { value: 'ca--san-francisco', label: 'San Francisco' },
            { value: 'gb--london', label: 'London' },
          ]}
          placeholder="Select a city"
          label="City"
          value={city}
          onChange={(value) => setCity(value || '')}
          style={{ flexGrow: 1 }}
        />
        <TextInput
          placeholder="Enter tags (comma-separated)"
          label="Tags"
          value={tags}
          onChange={(event) => setTags(event.currentTarget.value)}
          style={{ flexGrow: 2 }}
        />
        <Button
          onClick={handleStartScraping}
          disabled={!city || !tags || isScrapingStarted}
          style={{ alignSelf: 'flex-end' }}
        >
          Start Scraping
        </Button>
      </Group>
      
      {taskId && (
        <Text color={theme.colors.gray[3]} mb="md">
          Task ID: {taskId}
        </Text>
      )}
      
      <ScrollArea style={{ height: 'calc(100% - 150px)' }} ref={scrollAreaRef}>
        {logs.map((log, index) => (
          <Text key={index} style={{ fontFamily: 'monospace', fontSize: theme.fontSizes.sm, whiteSpace: 'pre-wrap' }}>
            <Text span c={theme.colors.gray[5]}>{log.timestamp}</Text>
            <Text span c={log.level === 'ERROR' ? theme.colors.red[6] : theme.colors.blue[6]}> - {log.level}</Text>
            <Text span c={theme.colors.gray[3]}> - {log.message}</Text>
          </Text>
        ))}
      </ScrollArea>
    </Box>
  );
};

export default LogTerminal;