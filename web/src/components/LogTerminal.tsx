import React, { useState, useRef, useEffect } from 'react';
import { Tabs, rem, Button, Select, MultiSelect, Text, Box } from '@mantine/core';
import { IconMessageCircle, IconSettings } from '@tabler/icons-react';

function LogTerminal() {
  const [logs, setLogs] = useState('');
  const [isScraping, setIsScraping] = useState(false);
  const [city, setCity] = useState('ny--new-york');
  const [tags, setTags] = useState([]);
  const [events, setEvents] = useState([]);
  const [activeTab, setActiveTab] = useState('input');
  const iconStyle = { width: rem(12), height: rem(12) };
  const logsRef = useRef(null);

  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [logs]);

  const startScraping = async () => {
    console.log("Starting scraping process");
    setIsScraping(true);
    setLogs('Processing...\n');
    setEvents([]);
    setActiveTab('logs');

    try {
      console.log(`Sending request to server for city: ${city}, tags: ${tags}`);
      const response = await fetch('http://localhost:8000/scrape', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          city: city,
          tags: tags.length > 0 ? tags : null,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      console.log("Response received, starting to read");

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');

      let buffer = '';
      let isJsonData = false;
      let jsonBuffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          console.log("Reader done");
          break;
        }
        
        const chunk = decoder.decode(value, { stream: true });
        console.log("Received chunk:", chunk);
        buffer += chunk;
        
        while (buffer.length > 0) {
          if (!isJsonData) {
            const newlineIndex = buffer.indexOf('\n');
            if (newlineIndex === -1) break;
            
            const line = buffer.slice(0, newlineIndex);
            buffer = buffer.slice(newlineIndex + 1);
            
            console.log("Processing line:", line);

            if (line.includes('BEGIN_JSON_DATA')) {
              console.log("JSON data start detected");
              isJsonData = true;
              continue;
            }

            setLogs(prevLogs => prevLogs + line + '\n');
          } else {
            const endIndex = buffer.indexOf('END_JSON_DATA');
            if (endIndex === -1) {
              jsonBuffer += buffer;
              buffer = '';
            } else {
              jsonBuffer += buffer.slice(0, endIndex);
              buffer = buffer.slice(endIndex + 'END_JSON_DATA'.length);
              isJsonData = false;
              
              console.log("JSON data end detected");
              try {
                console.log("Attempting to parse JSON, length:", jsonBuffer.length);
                const data = JSON.parse(jsonBuffer.trim());
                console.log("Parsed JSON data, events count:", data.events.length);
                setEvents(data.events);
                setLogs(prevLogs => prevLogs + 'Scraping completed. Events data received.\n');
                setActiveTab('input');
              } catch (error) {
                console.error('Error parsing JSON:', error);
                setLogs(prevLogs => prevLogs + `Error parsing JSON: ${error.message}\n`);
              }
              jsonBuffer = '';
            }
          }
        }
      }
    } catch (error) {
      console.error('Error during scraping:', error);
      setLogs(prevLogs => prevLogs + `Error: ${error.message}\n`);
    } finally {
      console.log("Scraping process finished");
      setIsScraping(false);
    }
  };

  console.log("Current events state:", events);

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Tabs value={activeTab} onChange={setActiveTab} style={{ flexShrink: 0 }}>
        <Tabs.List>
          <Tabs.Tab value="input" leftSection={<IconSettings style={iconStyle} />}>
            Scrape Input
          </Tabs.Tab>
          <Tabs.Tab value="logs" leftSection={<IconMessageCircle style={iconStyle} />}>
            Logs
          </Tabs.Tab>
        </Tabs.List>
      </Tabs>
      
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {activeTab === 'logs' && (
          <div
            ref={logsRef}
            style={{
              flex: 1,
              backgroundColor: '#222',
              color: '#fff',
              padding: '10px',
              overflowY: 'auto',
              fontFamily: 'monospace',
              whiteSpace: 'pre-wrap',
              wordWrap: 'break-word',
            }}
          >
            {logs}
          </div>
        )}
        
        {activeTab === 'input' && (
          <div style={{ padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', height: '100%' }}>
            <div style={{ marginBottom: '20px' }}>
              <Select
                label="City"
                placeholder="Select a city"
                value={city}
                onChange={setCity}
                data={[
                  { value: 'ny--new-york', label: 'New York' },
                  { value: 'ca--san-francisco', label: 'San Francisco' },
                  { value: 'gb--london', label: 'London' },
                ]}
                style={{ marginBottom: '10px' }}
              />
              <MultiSelect
                label="Tags"
                placeholder="Select or type tags"
                value={tags}
                onChange={setTags}
                data={[
                  'blockchain',
                  'nft',
                  'crypto',
                  'token',
                  'defi',
                  'Ethereum',
                  'Solana',
                  'DAO',
                  'gaming',
                  'GenAI',
                ]}
                getCreateLabel={(query) => `+ Create ${query}`}
                onCreate={(query) => {
                  const item = query.trim().toLowerCase();
                  if (item && !tags.includes(item)) {
                    setTags((prev) => [...prev, item]);
                  }
                  return item;
                }}
                searchable
                creatable
                style={{ marginBottom: '10px' }}
              />
              <Button onClick={startScraping} disabled={isScraping} fullWidth>
                {isScraping ? 'Scraping...' : 'Start Scraping'}
              </Button>
            </div>
            
            {events.length > 0 && (
              <div style={{ flex: 1, overflowY: 'auto' }}>
                <Text size="xl" w={700} mb="md">Scraped Events ({events.length})</Text>
                {events.map((event, index) => (
                  <Box key={index} mb="md" p="sm" style={{ border: '1px solid #ccc', borderRadius: '4px' }}>
                    <Text w={700}>{event.title}</Text>
                    <Text size="sm">{event.time}</Text>
                    <Text size="sm">{event.addr.street_addr}, {event.addr.local_addr}</Text>
                    <Text size="sm">Ticket: {event.ticket}</Text>
                    <Text size="sm" component="a" href={event.href} target="_blank" rel="noopener noreferrer">
                      Event Link
                    </Text>
                  </Box>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default LogTerminal;