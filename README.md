# HubSpot-list-filter-check
Python script checks Filters in a given range of HubSpot lists to see if the filters include certain properties.

V1.0 - First working version.
V1.1 now with Rate Limiting and Multithreading

This script checks multiple HubSpot lists to see if they use certain properties in their filters. It:

1. Reads a CSV of lists to check (using ILS ListId)
2. Reads a TXT file of properties to check (using API name)
3. Calls the HubSpot Lists API (via GET requests) to retrieve filter definitions
4. Logs only errors to a log file
5. Writes results to an output CSV immediately for each list
6. Uses a rolling-window rate limiter to keep requests under 100 per 10 seconds
7. Can run multithreaded to speed up processing

----------------------------------------------------------------
GETTING STARTED

Prerequisites:
- Python 3.9+ (or any compatible Python version).
- A valid HubSpot Bearer token (an API key or private app token).
  - You can create a Private App in HubSpot and copy the Access Token.
  - Or use an existing token if you have one.

Recommended Setup:
1. Clone or download this repository to your machine.
2. Create a Python virtual environment (optional but recommended) and install dependencies:
   python3 -m venv venv
   source venv/bin/activate
   pip install requests

Files in This Repository:
- list_check.py
  The main script that reads input files, checks each list against the HubSpot API, logs errors, and outputs a CSV of results.

- lists_to_check.csv
  A comma-separated CSV listing all the HubSpot lists you want to check. The first line must be a header with Name,ListId, for example:
      Name,ListId
      Research areas: Human genomics profiled,6537
      PW - Customers Paid,6402
      Lifecycle = Lead,6433
  - Name: A descriptive name for the list (not used by the script except for logging).
  - ListId: The numeric or string ID of the list in HubSpot.

- properties_to_check.txt
  A text file containing one property name per line. For example:
      research_areas
      techniques
      applied_uses
      investigating
  When the script checks each list, it looks for these property names in its filters.

- log_file.csv (created automatically if it doesn’t exist)
  Contains only error entries, with columns:
      DateTime, List_Name, List_ID, StatusCode, ErrorMessage

- checked_lists.csv (generated / overwritten by each run)
  Contains a row for every list checked, with columns:
      Name, ListId, <property1>, <property2>, ...
  - If a given property was found in the list’s filters, that column is TRUE.
  - If not found, it’s blank.
  - If an error occurred for that list, that row shows ERROR in all property columns.

----------------------------------------------------------------
SETTING THE BEARER TOKEN

1. Environment Variable Method
   - Set HUBSPOT_BEARER in your shell:
        export HUBSPOT_BEARER="my_secret_bearer_token"
   - The script will automatically read the token from os.environ.get("HUBSPOT_BEARER").

2. Hard-Coding (not recommended)
   - In list_check.py, near the top, replace "YOUR_BEARER_TOKEN_HERE" with your actual token:
        HUBSPOT_BEARER = "my_secret_bearer_token"
   - Anyone with access to this code can see your token, so be cautious.

----------------------------------------------------------------
RUNNING THE SCRIPT

1. Activate your virtual environment (if you created one):
     source venv/bin/activate

2. Ensure your input files (lists_to_check.csv, properties_to_check.txt) are in the same directory as list_check.py (or edit the script variables to point to their correct locations).

3. Run the script:
     python list_check.py

4. Check the generated files:
   - checked_lists.csv for a row-by-row report on each list.
   - log_file.csv for any errors encountered.

----------------------------------------------------------------
UNDERSTANDING RATE LIMITING

- HubSpot’s typical rate limit is around 190 requests per 10 seconds for standard accounts, but confirm your exact plan’s limits.
- This script enforces a rolling-window of 100 requests per 10 seconds (which keeps you safely below 190). You can adjust it in the script:
      while request_timestamps and (now - request_timestamps[0]) > 10:
          request_timestamps.pop(0)
      if len(request_timestamps) < 100:
          request_timestamps.append(now)
          return
  Increase if you want more concurrency but still remain below your account’s limit.

----------------------------------------------------------------
MULTITHREADING

- The script uses ThreadPoolExecutor from Python’s concurrent.futures to parallelize requests.
- The default max_workers=5 means up to 5 requests run at once, still obeying the rolling-window limit.
- If your environment (e.g., your server or local machine) can handle more concurrency, consider increasing max_workers.

----------------------------------------------------------------
COMMON QUESTIONS

1. Why is Excel merging columns into one?
   Some local settings in Excel default to semicolons or tabs. Use Data → From Text/CSV and select Comma as the delimiter.

2. I’m not seeing any TRUE in checked_lists.csv, but I know a property is used.
   Double-check your property spelling in properties_to_check.txt. The script looks for exact matches.
   Verify the JSON from the HubSpot API to ensure the filter uses property, not propertyName or another key.

3. How do I preserve the original order in checked_lists.csv?
   By default, rows are written in completion order due to multithreading. If you need to maintain the original order, you can collect all results first and then write them in sequence, or run single-threaded.

----------------------------------------------------------------
LICENSE
GNU GENERAL PUBLIC LICENSE v3.0
