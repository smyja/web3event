from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
import aiohttp
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

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scraper")

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

async def fetch_event_data(event_ids):
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
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            response.raise_for_status()
            return await response.json()

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

async def scrape_events(city: str, tags: List[str]):
    driver = setup_driver()
    all_events = []
    try:
        for i, tag in enumerate(tags):
            log_message = f"Searching events in {city} with tag {tag}"
            logger.info(log_message)
            yield f"{log_message}\n"
            
            page = 1
            events_found = True
            while events_found:
                url = f"https://www.eventbrite.com/d/{city}/{tag}/?page={page}"
                log_message = f"Scraping page {page} for tag {tag}"
                logger.info(log_message)
                yield f"{log_message}\n"
                
                captured_requests = capture_network_requests(url, driver)
                event_ids = extract_event_ids(captured_requests)

                if event_ids:
                    event_data = await fetch_event_data(event_ids)
                    if event_data and 'events' in event_data and event_data['events']:
                        new_events = event_data['events']
                        all_events.extend(new_events)
                        log_message = f"Found {len(new_events)} events on page {page}"
                        logger.info(log_message)
                        yield f"{log_message}\n"
                        page += 1
                    else:
                        log_message = f"No events found on page {page}. Stopping search for tag {tag}."
                        logger.info(log_message)
                        yield f"{log_message}\n"
                        events_found = False
                else:
                    log_message = f"No event IDs found on page {page}. Stopping search for tag {tag}."
                    logger.info(log_message)
                    yield f"{log_message}\n"
                    events_found = False

                await asyncio.sleep(2)

            log_message = f"Finished searching for tag {tag}. Total pages scraped: {page - 1}"
            logger.info(log_message)
            yield f"{log_message}\n"

        log_message = f"Total events found in {city}: {len(all_events)}"
        logger.info(log_message)
        yield f"{log_message}\n"

        processed_events = [extract_event_detailinfo(event) for event in all_events]
        log_message = f"Processed {len(processed_events)} events."
        logger.info(log_message)
        yield f"{log_message}\n"

        # Use a special delimiter to indicate the start of JSON data
        yield "BEGIN_JSON_DATA\n"
        yield json.dumps({"events": processed_events})
        yield "\nEND_JSON_DATA"

    except Exception as e:
        error_message = f"An error occurred during scraping: {str(e)}"
        logger.error(error_message)
        yield f"{error_message}\n"
    finally:
        driver.quit()
        log_message = "Browser closed"
        logger.info(log_message)
        yield f"{log_message}\n"

@app.post("/scrape")
async def scrape(request: ScraperRequest):
    if request.city not in web3event_cities:
        return {"message": "Invalid city"}
    
    tags = request.tags if request.tags else web3event_tags

    return StreamingResponse(scrape_events(request.city, tags), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)