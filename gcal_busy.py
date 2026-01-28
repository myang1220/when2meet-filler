import datetime
import os.path
import json
import requests
import zoneinfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

SAVE_TIMES_URL = "https://www.when2meet.com/SaveTimes.php"

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "text/javascript, text/html, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.when2meet.com",
    "Referer": "",
    "Priority": "u=1, i",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.5 Safari/605.1.15"
    ),
    "X-Prototype-Version": "1.7.3",
    "X-Requested-With": "XMLHttpRequest",
    "Cookie": "",
}

DATA = {
    "person": "",
    "event": "",
    "availability": "",
    "ChangeToAvailable": "true",
}

def start_repl():
  """Start a REPL in terminal to request user input, then return respective output."""
  while True:
    try:
        user_input = input("Enter something (or 'exit' to quit): ")
        if user_input.lower() == 'exit':
            print("Exiting REPL.")
            break
        if user_input.startswith("get_events"):
            # check valid input, including a valid date format
            try:
                args = user_input[user_input.index("(")+1:user_input.index(")")].split(",")
                if len(args) != 2:
                    raise ValueError("Invalid number of arguments.")
                start_date = args[0].strip()
                end_date = args[1].strip()
                start_date = datetime.datetime.strptime(start_date, "%m/%d/%Y").replace(tzinfo=zoneinfo.ZoneInfo("America/New_York"))
                end_date = datetime.datetime.strptime(end_date, "%m/%d/%Y").replace(tzinfo=zoneinfo.ZoneInfo("America/New_York"))
                print(f"Fetching events from {start_date} to {end_date}...")
                get_events(start_date, end_date)
            except:
                print("Invalid input format. Please use: get_events(<MM/DD/YYYY>, <MM/DD/YYYY>)")
                continue
        if user_input.startswith("fill"):
            # check valid input, including a valid date format
            # input should be in the format "fill <MM/DD/YYYY> <MM/DD/YYYY> <HH>-<HH>"
            try:
                parts = user_input.split()
                if len(parts) != 4:
                    raise ValueError("Invalid number of arguments. Please use: fill <MM/DD/YYYY> <MM/DD/YYYY> <HH>-<HH>")
                start_date_str = parts[1]
                end_date_str = parts[2]
                hours = parts[3]

                start_date = datetime.datetime.strptime(start_date_str, "%m/%d/%Y").replace(tzinfo=zoneinfo.ZoneInfo("America/New_York"))
                end_date = datetime.datetime.strptime(end_date_str, "%m/%d/%Y").replace(tzinfo=zoneinfo.ZoneInfo("America/New_York"))
                start_hour, end_hour = map(int, hours.split("-"))
                times = [start_date, end_date, start_hour, end_hour]

                events = get_events(start_date, end_date)

                # remove events that fall outside the specified time ranges
                filtered_events = filter_events_by_time(events, start_hour, end_hour)
                print(f"Found {len(filtered_events)} events within the specified time range.")
                try:
                    user_input = input("Please provide the when2meet referer URL: ")
                    HEADERS["Referer"] = user_input.strip()
                    user_input = input("Please provide the when2meet cookie: ")
                    HEADERS["Cookie"] = user_input.strip()
                    user_input = input("Please provide the when2meet person ID: ")
                    DATA["person"] = user_input.strip()
                    user_input = input("Please provide the when2meet event ID: ")
                    DATA["event"] = user_input.strip()
                    post_request(filtered_events, times)
                    # convert_event_to_when2meet_format(filtered_events, times)
                except:
                    print("Failed to post to when2meet. Aborting post request.")
                    continue
            except:
                print("Invalid input format. Please use: fill <MM/DD/YYYY> <MM/DD/YYYY> <HH>-<HH>")
                continue

        else:
            print(f"You entered: {user_input}. The accepted inputs are: exit, get_events(<MM/DD/YYYY>, <MM/DD/YYYY>)")
    except EOFError:
        print("\nExiting REPL.")
        break

def convert_event_to_when2meet_format(events, times):
    """Convert Google Calendar events to when2meet payload format. Use the times parameter to create a bitmap of availability,
    where 0 indicates available and 1 indicates busy. The times parameter is a list of four elements:
    start_date, end_date, start_hour, end_hour = times
    sample_curl.txt provides an example of how the payload should look, for the availability field."""
    start_date, end_date, start_hour, end_hour = times
    total_days = (end_date - start_date).days + 1
    slots_per_day = (end_hour - start_hour) * 4  # 4 slots per hour
    total_slots = total_days * slots_per_day
    # Initialize availability bit string with '0's
    availability_bits = ['1'] * total_slots
    for event in events:
        event_start_str = event["start"].get("dateTime", event["start"].get("date"))
        event_end_str = event["end"].get("dateTime", event["end"].get("date"))
        # dates in America/New_York timezone
        event_start = datetime.datetime.fromisoformat(event_start_str.replace("Z", "+00:00")).astimezone(zoneinfo.ZoneInfo("America/New_York"))
        event_end = datetime.datetime.fromisoformat(event_end_str.replace("Z", "+00:00")).astimezone(zoneinfo.ZoneInfo("America/New_York"))

        # Calculate the slot indices for the start and end times
        try:
            current_time = event_start
            while current_time < event_end:
                # print(availability_bits)
                if start_date <= current_time <= end_date and start_hour <= current_time.hour < end_hour:
                    day_index = (current_time - start_date).days
                    hour_index = current_time.hour - start_hour
                    slot_index = day_index * slots_per_day + hour_index * 4 + (current_time.minute // 15)
                    availability_bits[slot_index] = '0'
                current_time += datetime.timedelta(minutes=15)
        except Exception as e:
            print(f"Error processing event event: {e}")

    DATA["availability"] = ''.join(availability_bits)

    # old implementation, with slots
    # start_date, end_date, start_hour, end_hour = times
    # total_days = (end_date - start_date).days + 1
    # slots_per_day = (end_hour - start_hour) * 4  # 4 slots per hour
    # total_slots = total_days * slots_per_day

    # # Create a mapping from datetime to slot index
    # slot_index_map = {}
    # for day in range(total_days):
    #     for slot in range(slots_per_day):
    #         current_time = start_date + datetime.timedelta(days=day, minutes=slot * 15 + start_hour * 60)
    #         slot_index_map[current_time] = day * slots_per_day + slot

    # # Initialize availability bit string with '0's
    # availability_bits = ['0'] * total_slots

    # for event in events:
    #     event_start_str = event["start"].get("dateTime", event["start"].get("date"))
    #     event_end_str = event["end"].get("dateTime", event["end"].get("date"))
    #     event_start = datetime.datetime.fromisoformat(event_start_str.replace("Z", "+00:00"))
    #     event_end = datetime.datetime.fromisoformat(event_end_str.replace("Z", "+00:00"))

    #     # Mark the slots as unavailable ('1') for the duration of the event
    #     current_time = event_start
    #     while current_time < event_end:
    #         if current_time in slot_index_map:
    #             slot_index = slot_index_map[current_time]
    #             availability_bits[slot_index] = '1'
    #         current_time += datetime.timedelta(minutes=15)

    # DATA["slots"] = str(total_slots)
    # DATA["availability"] = ''.join(availability_bits)


def post_request(events, times):
    """Post request to when2meet endpoint with the events data."""
    convert_event_to_when2meet_format(events, times)
    response = requests.post(SAVE_TIMES_URL, headers=HEADERS, data=DATA)
    if response.status_code == 200:
        print("Successfully posted events to when2meet.")
    else:
        print(f"Failed to post events. Response: {response}")

def filter_events_by_time(events, start_hour, end_hour):
    """Filter events to only those that fall within the specified hour range."""
    filtered_events = []
    for event in events:
        event_start_str = event["start"].get("dateTime", event["start"].get("date"))
        event_start = datetime.datetime.fromisoformat(event_start_str.replace("Z", "+00:00")).astimezone(zoneinfo.ZoneInfo("America/New_York"))
        if start_hour <= event_start.hour < end_hour:
            filtered_events.append(event)
    return filtered_events

def get_events(start_date, end_date):
    """Fetch and print events between start_date and end_date."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())
    
    try:
        service = build("calendar", "v3", credentials=creds)

        calendarIDs = ["c_171c080dedb1698e6289d5d6bb784696e0c689a9084d4972ba9f9e5673cd5070@group.calendar.google.com", "c_8d7c26dac56e6888840bd23e14075f56135bc81b6033d803cc93582dc55f29c6@group.calendar.google.com", "moses_yang@brown.edu"]
        events = []

        for id in calendarIDs:
            events_result = (
                service.events()
                .list(
                    calendarId=id,
                    timeMin=start_date.isoformat(),
                    timeMax=end_date.isoformat(),
                    singleEvents=True,
                    eventTypes="default",
                    orderBy="startTime",
                )
                .execute()
            )
            accepted_events = get_only_accepted_events(events_result)
            events.extend(accepted_events)

            # print events_result output to file, as json, for debugging. each id to a separate file
            # with open(f"events_{id.replace('@', '_').replace('.', '_')}.json", "w") as f:
            #     json.dump(events_result, f, indent=4)

        if not events:
            print("No events found in the specified date range.")
            return
    
        # for event in events:
        #     start = event["start"].get("dateTime", event["start"].get("date"))
        #     print(start, event["summary"])
        
        return events
    
    except HttpError as error:
        print(f"An error occurred: {error}")

def get_only_accepted_events(events_results):
    """Filter events to only those where the user has accepted the invitation."""
    events = events_results.get("items", [])
    if events_results.get("summary", "") in ["Classes", "Fencing"]:
        return events
    
    accepted_events = []
    for event in events:
        attendees = event.get("attendees", [])
        for attendee in attendees:
            if attendee.get("self") and attendee.get("responseStatus") == "accepted":
                accepted_events.append(event)
                break
    return accepted_events

def main():
  start_repl()

if __name__ == "__main__":
  main()
