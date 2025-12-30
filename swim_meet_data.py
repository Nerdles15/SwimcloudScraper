# Based on v12 This version is 1.0.0.0 (john increment this if you make changes :))

# Added rate limiting
# Issue with headless mode where it isn't seeing the tables on the page without the physical page opening
# Issue where individual events are not parsed correctly, but relays are working fine

# Combined Brandon and John's changes

# Import everything needed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import requests
from bs4 import BeautifulSoup
import time
import pandas as pd
from urllib.parse import urljoin
import re
import random
from selenium.webdriver.common.by import By
import time


class SwimCloudScraper:
    def __init__(self, delay=1.0, rand_delay_min=8, rand_delay_max=14):
        """
        Initialize the scraper with a delay between requests.

        Args:
            delay: Seconds to wait between requests (default 1.0)
        """
        self.base_url = "https://www.swimcloud.com"
        self.delay = delay
        self.rand_delay_min = rand_delay_min
        self.rand_delay_max = rand_delay_max
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.team_name = None

        ## JN- changing selenium chrome to headless
        self._init_selenium()

    def _init_selenium(self):
        """Initialize Selenium with headless Chrome. Disable if you want to see for debugging porpoises"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        self.driver = webdriver.Chrome(options=chrome_options)
        print("Initializing headless Chrome for Selenium...")

    def find_all_available_sessions(self, url):
        """
        Find all available session links (files with .htm extension) on a meet page.

        Args:
            url: The URL of the meet index page

        Returns:
            list: List of dictionaries containing session info
        """
        self.driver.get(url)
        time.sleep(self.delay)

        # Find all links with .htm extension
        htm_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '.htm')]")

        sessions = []
        for link in htm_links:
            href = link.get_attribute('href')
            text = link.text.strip()

            # Skip if it's not a valid event link
            if not text or 'Latest Completed Event' in text:
                continue

            # Extract event number from text (e.g., "#1" -> "1")
            event_number = None
            if text.startswith('#'):
                event_number = text.split()[0].replace('#', '')

            # Determine session type
            session_type = None
            text_lower = text.lower()
            if 'prelims' in text_lower:
                session_type = 'Prelims'
            elif 'finals' in text_lower:
                session_type = 'Finals'
            elif 'swim-off' in text_lower or 'swim off' in text_lower:
                session_type = 'Swim-off'

            # Extract just the filename from href
            filename = href.split('/')[-1] if '/' in href else href

            # Build full URL if needed
            full_url = href if href.startswith('http') else f"{url.rsplit('/', 1)[0]}/{filename}"

            sessions.append({
                'event_number': event_number,
                'event_name': text,
                'session_type': session_type,
                'href': filename,
                'full_url': full_url
            })

        print(f"Found {len(sessions)} event sessions")
        return sessions

    def _extract_meet_name(self, page_text):
        """Extract meet name from page text."""
        lines = page_text.strip().split('\n')
        for i, line in enumerate(lines):
            if 'Championship' in line or 'Meet' in line:
                # Often the meet name is in the first few lines
                return line.strip()
        return "Unknown Meet"

    def _extract_event_info(self, page_text):
        """
        Extract event number and name from page text.
        Returns: (event_number, event_name, is_relay)
        """
        # Look for pattern like "Event 21  Men 400 Yard Freestyle Relay"
        event_pattern = r'Event\s+(\d+)\s+(.+?)(?:\n|$)'
        match = re.search(event_pattern, page_text)

        if match:
            event_number = match.group(1)
            event_name = match.group(2).strip()
            is_relay = 'Relay' in event_name
            return event_number, event_name, is_relay

        return None, None, False

    def _determine_relay_distances(self, event_name):
        """
        Determine the distances for each leg based on relay type.
        Returns list of distances (e.g., [50, 100, 150, 200] for 200 relay)
        """
        if '200' in event_name and 'Relay' in event_name:
            return [50, 100, 150, 200]
        elif '400' in event_name and 'Relay' in event_name:
            return [100, 200, 300, 400]
        elif '800' in event_name and 'Relay' in event_name:
            return [200, 400, 600, 800]
        else:
            # Default to 4 legs with unknown distances
            return [1, 2, 3, 4]

    def _parse_relay_results(self, page_text, meet_name, meet_url, event_number, event_name):
        """
        Parse relay event results from page text with individual swimmer splits.
        Returns: list of dictionaries with detailed split data
        """
        results = []

        # Split into lines
        lines = page_text.split('\n')

        # Find the start of results (after the header section)
        result_start = 0
        for i, line in enumerate(lines):
            if '==================================================================================' in line:
                result_start = i + 1
                break

        # Parse each team result
        i = result_start
        while i < len(lines):
            line = lines[i].strip()

            # Check if this is a result line (starts with rank number)
            rank_match = re.match(r'^\s*(\d+)\s+', line)
            if rank_match:
                swimmers = []  # List of (order, name) tuples
                splits_lines = []

                # Move to next line to start looking for swimmers
                i += 1

                # Next lines contain swimmer names
                # Pattern: "1) Caribe, Guilherme JR          2) r:0.23 Taylor, Lamar 5Y"
                while i < len(lines):
                    next_line = lines[i].strip()
                    # Swimmer lines start with numbers followed by )
                    if re.match(r'^\d+\)', next_line):
                        # Parse all swimmers in this line
                        # Split by pattern of digit followed by )
                        parts = re.split(r'(?=\d+\))', next_line)

                        for part in parts:
                            part = part.strip()
                            if not part:
                                continue

                            # Extract order number and name
                            # Pattern: "1) Caribe, Guilherme JR" or "2) r:0.23 Taylor, Lamar 5Y"
                            match = re.match(r'(\d+)\)\s*(?:r:[\d.+-]+\s*)?(.+)', part)
                            if match:
                                order = int(match.group(1))
                                name = match.group(2).strip()
                                swimmers.append((order, name))
                        i += 1
                    else:
                        break

                # Find the splits lines (contains the actual split times)
                # Lines start with "r:" or just have times
                while i < len(lines):
                    next_line = lines[i].strip()
                    if next_line.startswith('r:') or re.match(r'^\d+\.\d+', next_line):
                        splits_lines.append(next_line)
                        i += 1
                        # Continue reading lines that look like splits
                        while i < len(lines):
                            cont_line = lines[i].strip()
                            # Check if this is a continuation of splits (has time patterns)
                            if re.search(r'\d+:\d+\.\d+|\d+\.\d+', cont_line) and not re.match(r'^\d+\s+\S', cont_line):
                                splits_lines.append(cont_line)
                                i += 1
                            else:
                                break
                        break
                    i += 1

                # Combine all split lines into one string
                splits_text = ' '.join(splits_lines)

                # Parse splits from the combined splits text
                if splits_text and swimmers:
                    # Extract all time values
                    time_pattern = r'(\d+:\d+\.\d+|\d+\.\d+)'
                    all_times = re.findall(time_pattern, splits_text)

                    # Pattern explanation for 400 relay:
                    # r:+0.58  19.28  40.57 (40.57)  59.68 (19.11)  1:21.59 (41.02)  1:40.95 (19.36)  2:02.94 (41.35)  2:21.29 (18.35)  2:42.30 (39.36)
                    #
                    # Times in order: [0.58, 19.28, 40.57, 40.57, 59.68, 19.11, 1:21.59, 41.02, 1:40.95, 19.36, 2:02.94, 41.35, 2:21.29, 18.35, 2:42.30, 39.36]
                    #
                    # Leg 1: split=19.28 (idx 1), leg=40.57 (idx 2), cumulative=40.57 (idx 3)
                    # Leg 2: split=19.11 (idx 5), leg=41.02 (idx 7), cumulative=1:21.59 (idx 6)
                    # Leg 3: split=19.36 (idx 9), leg=41.35 (idx 11), cumulative=2:02.94 (idx 10)
                    # Leg 4: split=18.35 (idx 13), leg=39.36 (idx 15), cumulative=2:42.30 (idx 14)

                    leg_data = []
                    times_idx = 0

                    # Skip reaction time if present (r:+0.58 becomes 0.58)
                    if times_idx < len(all_times) and float(all_times[times_idx]) < 1.0:
                        times_idx += 1

                    # First leg: split, leg, cumulative (cumulative appears twice)
                    if times_idx + 2 < len(all_times):
                        split_time = all_times[times_idx]  # 19.28
                        leg_time = all_times[times_idx + 1]  # 40.57
                        cumulative = all_times[times_idx + 2]  # 40.57 (duplicate)
                        leg_data.append((split_time, leg_time, cumulative))
                        times_idx += 3

                    # Remaining legs follow pattern:
                    # intermediate_cumulative, split, cumulative, leg
                    # We want: split, leg, cumulative
                    while times_idx < len(all_times) and len(leg_data) < len(swimmers):
                        # Skip intermediate cumulative (e.g., 59.68)
                        times_idx += 1

                        if times_idx >= len(all_times):
                            break

                        # Get split time (e.g., 19.11)
                        split_time = all_times[times_idx]
                        times_idx += 1

                        if times_idx >= len(all_times):
                            break

                        # Get cumulative time (e.g., 1:21.59)
                        cumulative = all_times[times_idx]
                        times_idx += 1

                        if times_idx >= len(all_times):
                            break

                        # Get leg time (e.g., 41.02)
                        leg_time = all_times[times_idx]
                        times_idx += 1

                        leg_data.append((split_time, leg_time, cumulative))

                    # Create a result entry for each swimmer
                    for idx, (order, name) in enumerate(swimmers):
                        if idx < len(leg_data):
                            split_time, leg_time, cumulative = leg_data[idx]

                            results.append({
                                'meet_name': meet_name,
                                'meet_url': meet_url,
                                'event_number': event_number,
                                'event_name': event_name,
                                'is_relay': True,
                                'Name': name,
                                'Order': order,
                                'Split': split_time,
                                'Leg': leg_time,
                                'Cumulative': cumulative
                            })
            else:
                i += 1

        return results

    def _parse_individual_results(self, page_text, meet_name, meet_url, event_number, event_name):
        """
        Parse individual event results from page text.
        Returns: list of dictionaries with result data
        """
        results = []

        # Split into lines
        lines = page_text.split('\n')

        # Find the start of results
        result_start = 0
        for i, line in enumerate(lines):
            if '==================================================================================' in line:
                result_start = i + 1
                break

        # Parse each result
        i = result_start
        while i < len(lines):
            line = lines[i].strip()

            # Check if this is a result line (starts with rank number)
            rank_match = re.match(r'^\s*(\d+)\s+', line)
            if rank_match:
                parts = line.split()

                if len(parts) >= 3:
                    # Extract swimmer name
                    swimmer_name = None
                    for j in range(1, len(parts)):
                        if ',' in parts[j]:
                            # Name format is usually "Last, First"
                            swimmer_name = parts[j]
                            # Check if next part is part of name
                            if j + 1 < len(parts) and not parts[j + 1][0].isupper() or len(parts[j + 1]) <= 3:
                                swimmer_name += ' ' + parts[j + 1]
                            break

                    # Find the finals time
                    time_pattern = r'\d+:\d+\.\d+|\d+\.\d+'
                    finals_time = None

                    for part in reversed(parts):
                        if re.match(time_pattern, part):
                            finals_time = re.sub(r'[A-Z]', '', part)
                            break

                    if swimmer_name and finals_time:
                        results.append({
                            'meet_name': meet_name,
                            'meet_url': meet_url,
                            'event_number': event_number,
                            'event_name': event_name,
                            'is_relay': False,
                            'Name': swimmer_name,
                            'Order': None,
                            'Split': None,
                            'Leg': None,
                            'Cumulative': finals_time
                        })

            i += 1

        return results
    def parse_event_page(self, url, meet_name=None, meet_url=None):
        """
        Parse an event results page and extract all relevant data.

        Args:
            url: URL of the event page to parse
            meet_name: Optional meet name (will be extracted if not provided)
            meet_url: Optional meet URL (will use provided URL if not given)

        Returns:
            pandas.DataFrame: DataFrame with columns [meet_name, meet_url, event_number,
                             event_name, is_relay, Name, Distance, Split, Leg, Cumulative]
        """
        print(f"Parsing event page: {url}")

        self.driver.get(url)
        time.sleep(self.delay)

        # Get the page text from <pre> tag (results are typically in <pre> tags)
        try:
            pre_element = self.driver.find_element(By.TAG_NAME, 'pre')
            page_text = pre_element.text
        except Exception:
            # Fallback to body text if no <pre> tag
            page_text = self.driver.find_element(By.TAG_NAME, 'body').text

        # Extract meet name if not provided
        if not meet_name:
            meet_name = self._extract_meet_name(page_text)

        # Use the URL as meet_url if not provided
        if not meet_url:
            # Get the base URL (everything before the .htm file)
            meet_url = url.rsplit('/', 1)[0] + '/'

        # Extract event information
        event_number, event_name, is_relay = self._extract_event_info(page_text)

        if not event_number or not event_name:
            print(f"Could not extract event information from {url}")
            return pd.DataFrame()

        print(f"Event {event_number}: {event_name} (Relay: {is_relay})")

        # Parse results based on event type
        if is_relay:
            results = self._parse_relay_results(page_text, meet_name, meet_url,
                                                event_number, event_name)
        else:
            results = self._parse_individual_results(page_text, meet_name, meet_url,
                                                     event_number, event_name)

        print(f"Extracted {len(results)} results")

        # Convert to DataFrame
        df = pd.DataFrame(results)
        return df

    def scrape_entire_meet(self, index_url, output_file='meet_results.xlsx'):
        """
        Scrape all events from a meet and save to Excel.

        Args:
            index_url: URL of the meet index page
            output_file: Path to output Excel file
        """
        print(f"Starting scrape of meet: {index_url}")

        # Get all event sessions
        sessions = self.find_all_available_sessions(index_url)

        # Extract meet name from first page
        if sessions:
            first_event_url = sessions[0]['full_url']
            self.driver.get(first_event_url)
            time.sleep(self.delay)

            try:
                pre_element = self.driver.find_element(By.TAG_NAME, 'pre')
                page_text = pre_element.text
                meet_name = self._extract_meet_name(page_text)
            except:
                meet_name = "Unknown Meet"
        else:
            meet_name = "Unknown Meet"

        print(f"Meet name: {meet_name}")

        # Create or overwrite the Excel file
        all_results = []

        # Parse each event
        for i, session in enumerate(sessions):
            print(f"\nProcessing event {i + 1}/{len(sessions)}: {session['event_name']}")

            try:
                df = self.parse_event_page(session['full_url'],
                                           meet_name=meet_name,
                                           meet_url=index_url)

                if not df.empty:
                    all_results.append(df)

                # Be respectful with delays
                time.sleep(self.delay)

            except Exception as e:
                print(f"Error parsing {session['full_url']}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # Combine all results
        if all_results:
            final_df = pd.concat(all_results, ignore_index=True)

            # Save to Excel
            print(f"\nSaving {len(final_df)} total results to {output_file}")
            final_df.to_excel(output_file, sheet_name='All Results', index=False)
            print(f"Successfully saved to {output_file}")

            return final_df
        else:
            print("No results found!")
            return pd.DataFrame()

    def close(self):
        """Close the Selenium driver."""
        if hasattr(self, 'driver'):
            self.driver.quit()


if __name__ == "__main__":
    # Initialize scraper
    scraper = SwimCloudScraper(delay=1.0, rand_delay_min=8, rand_delay_max=14)

    try:
        # Example: Parse a single event
        event_url = "https://swimmeetresults.tech/NCAA-Division-I-Men-2025/250326lastevt.htm"
        df = scraper.parse_event_page(event_url,
                                      meet_name="2025 NCAA Division I Men's Swimming & Diving",
                                      meet_url="https://swimmeetresults.tech/NCAA-Division-I-Men-2025/")

        print("\nResults preview:")
        print(df.to_string())

        # Save single event
        df.to_excel('output_stuff\\single_event_results.xlsx', sheet_name='Event Results', index=False)
        print("\nSaved to output_stuff\\single_event_results.xlsx")

        # This should find all the meets that we can scrape. We will have to loop through it to scrape everything.
        # index_url = "https://swimmeetresults.tech/NCAA-Division-I-Men-2025/index.htm"
        # full_results = scraper.scrape_entire_meet(index_url, output_file='ncaa_meet_results.xlsx')

    finally:
        scraper.close()
