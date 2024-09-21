from fastapi import FastAPI, BackgroundTasks, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import asyncio
import json
import logging
import time
import requests
import os
import re

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for task statuses
tasks = {}

# Custom logger that streams logs
class StreamingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs = asyncio.Queue()

    def emit(self, record):
        log_entry = self.format(record)
        asyncio.create_task(self.logs.put({
            "timestamp": record.asctime,
            "level": record.levelname,
            "message": record.message
        }))

# Set up logging
logger = logging.getLogger("scraper")
logger.setLevel(logging.INFO)
streaming_handler = StreamingHandler()
streaming_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(streaming_handler)

# Define cities and tags
web3event_cities = ["ny--new-york", "ca--san-francisco", "gb--london"]
web3event_tags = [
    "token", "blockchain", "crypto", "cryptocurrency", "nft",
    "dao", "defi", "dapp", "dex", "depin",
    "Ethereum", "Solana",
    "gaming",
    "GenAI"
]

class ScraperRequest(BaseModel):
    city: str
    tags: Optional[List[str]] = None

class ScraperResponse(BaseModel):
    message: str
    task_id: str

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.set_capability("goog:loggingPrefs", {'performance': 'ALL'})
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def capture_network_requests(url, driver):
    logger.info(f"Navigating to {url}")
    driver.get(url)
    logger.info("Waiting for 10 seconds to allow data to arrive")
    time.sleep(10)
    
    logger.info("Retrieving performance logs")
    perf = driver.get_log('performance')
    
    v3_requests = []
    for entry in perf:
        try:
            message = json.loads(entry['message'])['message']
            if 'Network.requestWillBeSent' == message['method']:
                url = message['params']['request']['url']
                if "eventbrite" in url and "/v3/" in url:
                    v3_requests.append(message['params']['request'])
        except Exception as e:
            logger.error(f"Error processing log entry: {e}")
    
    return v3_requests

def extract_event_ids(requests):
    for req in requests:
        if 'api/v3/destination/events/' in req['url']:
            match = re.search(r'event_ids=([^&]+)', req['url'])
            if match:
                return match.group(1).split(',')
    return []

def fetch_event_data(event_ids):
    url = "https://www.eventbrite.com/api/v3/destination/events/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.90 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.eventbrite.com/",
        "X-Requested-With": "XMLHttpRequest",
    }
    params = {
        "event_ids": ",".join(event_ids),
        "expand": "event_sales_status,image,primary_venue,saves,ticket_availability,primary_organizer,public_collections",
        "page_size": len(event_ids)
    }
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

def save_to_file(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def extract_event_detailinfo(event):
    event_detail_info = {}

    event_detail_info['image'] = event.get('image', {}).get('url', '')
    event_detail_info['title'] = event.get('name', '')
    event_detail_info['summary'] = event.get('summary', '')
    
    primary_organizer = event.get('primary_organizer', {})
    event_detail_info['organizers'] = [primary_organizer.get('name', '')] if primary_organizer else []
    
    start_date = event.get('start_date', '')
    start_time = event.get('start_time', '')
    end_date = event.get('end_date', '')
    end_time = event.get('end_time', '')
    
    if start_date and start_time:
        start_datetime = f"{start_date} {start_time}"
        end_datetime = f"{end_date} {end_time}" if end_date and end_time else ''
        event_detail_info['time'] = f"{start_datetime} - {end_datetime}".strip()
    else:
        event_detail_info['time'] = ''
    
    primary_venue = event.get('primary_venue', {})
    address = primary_venue.get('address', {})
    event_detail_info['addr'] = {
        'street_addr': address.get('address_1', ''),
        'local_addr': f"{address.get('city', '')}, {address.get('region', '')}"
    }
    
    event_detail_info['description'] = ''
    
    ticket_availability = event.get('ticket_availability', {})
    if ticket_availability is None:
        ticket_availability = {}
    
    event_detail_info['isFree'] = ticket_availability.get('is_free', False)
    
    if ticket_availability.get('is_sold_out', False):
        event_detail_info['ticket'] = 'sold out'
    elif event_detail_info['isFree']:
        event_detail_info['ticket'] = 'Free'
    else:
        min_price = ticket_availability.get('minimum_ticket_price', {})
        max_price = ticket_availability.get('maximum_ticket_price', {})
        min_price_display = min_price.get('display', '') if min_price else ''
        max_price_display = max_price.get('display', '') if max_price else ''
        
        if min_price_display and max_price_display:
            if min_price_display == max_price_display:
                event_detail_info['ticket'] = min_price_display
            else:
                event_detail_info['ticket'] = f"{min_price_display} - {max_price_display}"
        else:
            event_detail_info['ticket'] = 'Price not available'

    event_detail_info['href'] = event.get('url', '')

    return event_detail_info

async def scrape_events(city: str, tags: List[str], task_id: str):
    tasks[task_id] = {"status": "in progress", "completion": 0}
    driver = setup_driver()
    all_events = []

    try:
        for i, tag in enumerate(tags):
            logger.info(f"Searching events in {city} with tag {tag}")
            page = 1
            events_found = True

            while events_found:
                url = f"https://www.eventbrite.com/d/{city}/{tag}/?page={page}"
                logger.info(f"Scraping page {page} for tag {tag}")
                
                captured_requests = capture_network_requests(url, driver)
                event_ids = extract_event_ids(captured_requests)

                if event_ids:
                    event_data = fetch_event_data(event_ids)
                    if event_data and 'events' in event_data and event_data['events']:
                        new_events = event_data['events']
                        all_events.extend(new_events)
                        logger.info(f"Found {len(new_events)} events on page {page}")
                        page += 1
                    else:
                        logger.info(f"No events found on page {page}. Stopping search for tag {tag}.")
                        events_found = False
                else:
                    logger.info(f"No event IDs found on page {page}. Stopping search for tag {tag}.")
                    events_found = False

                await asyncio.sleep(2)  # Add a delay between requests to avoid rate limiting

            logger.info(f"Finished searching for tag {tag}. Total pages scraped: {page - 1}")
            
            completion = int((i + 1) / len(tags) * 100)
            tasks[task_id]["completion"] = completion

        logger.info(f"Total events found in {city}: {len(all_events)}")

        os.makedirs("event_data", exist_ok=True)

        all_events_file = f"event_data/all_events_{city.replace('--', '_')}.json"
        save_to_file({"events": all_events}, all_events_file)
        logger.info(f"All event data saved to {all_events_file}")

        processed_events = []
        for event in all_events:
            processed_event = extract_event_detailinfo(event)
            processed_events.append(processed_event)
        
        processed_events_file = f"event_data/processed_events_detailed_{city.replace('--', '_')}.json"
        save_to_file(processed_events, processed_events_file)
        logger.info(f"Processed and saved detailed information for {len(processed_events)} events to {processed_events_file}")

        tasks[task_id]["status"] = "completed"

    except Exception as e:
        logger.error(f"An error occurred during scraping: {str(e)}")
        tasks[task_id]["status"] = "failed"

    finally:
        driver.quit()
        logger.info("Browser closed")

@app.post("/scrape", response_model=ScraperResponse)
async def scrape(request: ScraperRequest, background_tasks: BackgroundTasks):
    if request.city not in web3event_cities:
        return {"message": "Invalid city", "task_id": ""}
    
    tags = request.tags if request.tags else web3event_tags
    task_id = f"scrape_{request.city}_{int(time.time())}"
    
    background_tasks.add_task(scrape_events, request.city, tags, task_id)
    
    return {"message": "Scraping task started", "task_id": task_id}

@app.get("/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks:
        return {"status": "not found", "task_id": task_id}
    return tasks[task_id]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            log_entry = await streaming_handler.logs.get()
            await websocket.send_json({"log": log_entry})
    except Exception as e:
        print(f"WebSocket error: {str(e)}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)