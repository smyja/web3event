from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import json
import logging
import time
import requests
import os
import re

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define cities and tags
web3event_cities = ["ny--new-york", "ca--san-francisco", "gb--london"]
web3event_tags = [
    "token", "blockchain", "crypto", "cryptocurrency", "nft",
    "dao", "defi", "dapp", "dex", "depin",
    "Ethereum", 
    "gaming"
]

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.set_capability("goog:loggingPrefs", {'performance': 'ALL'})
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def capture_network_requests(url, driver):
    logging.info(f"Navigating to {url}")
    driver.get(url)
    logging.info("Waiting for 10 seconds to allow data to arrive")
    time.sleep(10)
    
    logging.info("Retrieving performance logs")
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
            logging.error(f"Error processing log entry: {e}")
    
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

    # Extract image
    event_detail_info['image'] = event.get('image', {}).get('url', '')
    
    # Extract title
    event_detail_info['title'] = event.get('name', '')
    
    # Extract summary
    event_detail_info['summary'] = event.get('summary', '')
    
    # Extract organizers
    primary_organizer = event.get('primary_organizer', {})
    event_detail_info['organizers'] = [primary_organizer.get('name', '')] if primary_organizer else []
    
    # Extract time
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
    
    # Extract address
    primary_venue = event.get('primary_venue', {})
    address = primary_venue.get('address', {})
    event_detail_info['addr'] = {
        'street_addr': address.get('address_1', ''),
        'local_addr': f"{address.get('city', '')}, {address.get('region', '')}"
    }
    
    # Extract description (not available in this JSON structure, leaving it empty)
    event_detail_info['description'] = ''
    
    # Extract ticket information and isFree status
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

    # Add href (URL) to the event_detail_info
    event_detail_info['href'] = event.get('url', '')

    return event_detail_info

def main():
    driver = setup_driver()
    all_events = []

    # Get only the first city from the list
    city = web3event_cities[0]
    logging.info(f"Searching events for {city} (first city in the list)")

    try:
        for tag in web3event_tags:
            logging.info(f"Searching events in {city} with tag {tag}")
            page = 1
            events_found = True

            while events_found:
                url = f"https://www.eventbrite.com/d/{city}/{tag}/?page={page}"
                logging.info(f"Scraping page {page} for tag {tag}")
                
                captured_requests = capture_network_requests(url, driver)
                event_ids = extract_event_ids(captured_requests)

                if event_ids:
                    event_data = fetch_event_data(event_ids)
                    if event_data and 'events' in event_data and event_data['events']:
                        new_events = event_data['events']
                        all_events.extend(new_events)
                        logging.info(f"Found {len(new_events)} events on page {page}")
                        page += 1
                    else:
                        logging.info(f"No events found on page {page}. Stopping search for tag {tag}.")
                        events_found = False
                else:
                    logging.info(f"No event IDs found on page {page}. Stopping search for tag {tag}.")
                    events_found = False

                time.sleep(2)  # Add a delay between requests to avoid rate limiting

            logging.info(f"Finished searching for tag {tag}. Total pages scraped: {page - 1}")

        logging.info(f"Total events found in {city}: {len(all_events)}")

    except Exception as e:
        logging.error(f"An error occurred during scraping: {e}")

    finally:
        driver.quit()
        logging.info("Browser closed")

    # Create a directory to store the event data
    os.makedirs("event_data", exist_ok=True)

    # Save all event data to a single file
    all_events_file = f"event_data/all_events_{city.replace('--', '_')}.json"
    save_to_file({"events": all_events}, all_events_file)
    logging.info(f"All event data saved to {all_events_file}")

    # Process the event data to extract detailed information
    processed_events = []
    for event in all_events:
        processed_event = extract_event_detailinfo(event)
        processed_events.append(processed_event)
    
    # Save processed events to a new file
    processed_events_file = f"event_data/processed_events_detailed_{city.replace('--', '_')}.json"
    save_to_file(processed_events, processed_events_file)
    logging.info(f"Processed and saved detailed information for {len(processed_events)} events to {processed_events_file}")

if __name__ == "__main__":
    main()