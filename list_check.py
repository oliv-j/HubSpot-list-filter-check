#!/usr/bin/env python3

import csv
import datetime
import os
import time
import requests
import threading
import concurrent.futures

# Filenames (adjust if needed)
LISTS_CSV = "lists_to_check.csv"
PROPERTIES_TXT = "properties_to_check.txt"
LOG_CSV = "log_file.csv"
CHECKED_LISTS_CSV = "checked_lists.csv"

# Bearer token (set via environment variable or replace directly)
HUBSPOT_BEARER = os.environ.get("HUBSPOT_BEARER", "YOUR_BEARER_TOKEN_HERE")

# ---------------------
# 1) RATE LIMITING
# A simple rolling-window rate limiter.
# We'll allow 100 requests per 10-second window.
# ---------------------
request_timestamps = []  # times of recent requests
rate_lock = threading.Lock()

def wait_for_rate_slot():
    """
    Blocks until we can make another request without exceeding
    100 requests in any rolling 10-second window.
    """
    while True:
        with rate_lock:
            now = time.time()
            # Drop timestamps older than 10 seconds
            while request_timestamps and (now - request_timestamps[0]) > 10:
                request_timestamps.pop(0)

            if len(request_timestamps) < 100:
                # We have capacity to make a new request
                request_timestamps.append(now)
                return

        # If we get here, the window is full. Wait a bit, then retry
        time.sleep(0.1)

# ---------------------
# 2) LOAD HELPER FUNCTIONS
# ---------------------
def load_list_ids(filename: str):
    """
    Load Name and ListId from the CSV. 
    The CSV header must match exactly: Name,ListId
    """
    lists_data = []
    with open(filename, mode="r", encoding="utf-8-sig") as csvfile:
        reader = csv.DictReader(csvfile, delimiter=",")
        for row in reader:
            lists_data.append({
                "name": row["Name"].strip(),
                "listId": row["ListId"].strip()
            })
    return lists_data

def load_properties(filename: str):
    """
    Load properties from a TXT file, one property per line.
    Return a list (to preserve order) and a set (for quick membership).
    """
    prop_list = []
    prop_set = set()
    with open(filename, "r", encoding="utf-8-sig") as txtfile:
        for line in txtfile:
            p = line.strip()
            if p:
                prop_list.append(p)
                prop_set.add(p)
    return prop_list, prop_set

# ---------------------
# 3) LOGGING ONLY ERRORS
# ---------------------
log_lock = threading.Lock()

def log_error(list_name: str, list_id: str, status_code: int, error_message: str):
    """
    Append a single row to the log file, but only for errors.
    Columns: [DateTime, List_Name, List_ID, StatusCode, ErrorMessage]
    """
    now = datetime.datetime.now().isoformat()
    with log_lock:
        with open(LOG_CSV, mode="a", encoding="utf-8", newline="") as csvfile:
            writer = csv.writer(csvfile, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow([now, list_name, list_id, status_code, error_message])

# ---------------------
# 4) EXTRACT PROPERTIES FROM THE JSON
# ---------------------
def traverse_filter_branches(branch, found_props, properties_to_check):
    """
    Recursively traverse filterBranches to find filters with filterType="PROPERTY".
    If 'property' is in properties_to_check, add it to found_props.
    """
    if not branch:
        return

    filters = branch.get("filters", [])
    for f in filters:
        if f.get("filterType") == "PROPERTY":
            prop_name = f.get("property", "")
            if prop_name in properties_to_check:
                found_props.add(prop_name)

    # Recurse into sub-branches
    for sub in branch.get("filterBranches", []):
        traverse_filter_branches(sub, found_props, properties_to_check)

def check_list_properties(response_json: dict, properties_to_check: set):
    """
    Return a set of property names found in the list's filters.
    We look under response_json["list"]["filterBranch"].
    """
    found_props = set()
    list_obj = response_json.get("list", {})
    top_branch = list_obj.get("filterBranch", {})
    traverse_filter_branches(top_branch, found_props, properties_to_check)
    return found_props

# ---------------------
# 5) THE WORKER FUNCTION FOR EACH LIST
# ---------------------
def check_single_list(item, property_list, property_set):
    """
    1) Wait for a rate slot (so we don't exceed 100 requests/10s).
    2) Make the GET call.
    3) Return (list_name, list_id, results).
       Where results is a list of "TRUE" or "" for each property in property_list.
    4) If there's an error, log it, and return "ERROR" for all properties.
    """
    list_name = item["name"]
    list_id = item["listId"]

    # 1) Wait for rate limit
    wait_for_rate_slot()

    # 2) Make the GET request
    url = f"https://api.hubapi.com/crm/v3/lists/{list_id}?includeFilters=true"
    headers = {
        "Authorization": f"Bearer {HUBSPOT_BEARER}",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.get(url, headers=headers)
        if resp.ok:
            data = resp.json()
            found_props = check_list_properties(data, property_set)
            # Build a list of "TRUE" or ""
            row_values = [("TRUE" if p in found_props else "") for p in property_list]
            return (list_name, list_id, row_values, None)  # no error
        else:
            # Non-OK -> log the error
            error_msg = f"API error: {resp.text}"
            log_error(list_name, list_id, resp.status_code, error_msg)

            # Return "ERROR" for each property
            row_values = ["ERROR"] * len(property_list)
            return (list_name, list_id, row_values, error_msg)

    except requests.RequestException as e:
        # Network or connection error -> log it
        error_msg = str(e)
        log_error(list_name, list_id, 0, error_msg)
        row_values = ["ERROR"] * len(property_list)
        return (list_name, list_id, row_values, error_msg)

# ---------------------
# 6) MAIN ROUTINE - MULTITHREADED
# ---------------------
def main():
    # Load data
    lists_data = load_list_ids(LISTS_CSV)
    property_list, property_set = load_properties(PROPERTIES_TXT)

    # If log file doesn't exist, write a header row:
    if not os.path.exists(LOG_CSV):
        with open(LOG_CSV, "w", encoding="utf-8", newline="") as logf:
            writer = csv.writer(logf, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(["DateTime", "List_Name", "List_ID", "StatusCode", "ErrorMessage"])

    # Prepare output file: write the header row once
    # We'll keep it open the entire run, but we must coordinate writes from multiple threads
    with open(CHECKED_LISTS_CSV, "w", encoding="utf-8", newline="") as out_f:
        writer = csv.writer(out_f, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
        header = ["Name", "ListId"] + property_list
        writer.writerow(header)

        write_lock = threading.Lock()  # to synchronize writing rows

        # We'll use a thread pool so we can do multiple requests concurrently
        max_workers = 5  # or some number that is reasonable for your environment
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for item in lists_data:
                # schedule each list check
                fut = executor.submit(check_single_list, item, property_list, property_set)
                futures.append(fut)

            # As each future completes, immediately write its row to CSV
            for fut in concurrent.futures.as_completed(futures):
                list_name, list_id, row_values, err_msg = fut.result()
                # row_values is the list of "TRUE"/"" or "ERROR"
                with write_lock:
                    writer.writerow([list_name, list_id] + row_values)
                    # Flush so each row is on disk immediately
                    out_f.flush()

if __name__ == "__main__":
    main()
