#!/usr/bin/env python3

import csv
import datetime
import os
import requests

# Adjust these filenames as needed
LISTS_CSV = "lists_to_check.csv"
PROPERTIES_TXT = "properties_to_check.txt"
LOG_CSV = "log_file.csv"
CHECKED_LISTS_CSV = "checked_lists.csv"

# Bearer token (set via environment variable or replace with a hard-coded string)
HUBSPOT_BEARER = os.environ.get("HUBSPOT_BEARER", "YOUR_BEARER_TOKEN_HERE")

def load_list_ids(filename: str):
    """Load list names and IDs from a CSV file with columns: Name,ListId."""
    lists_data = []
    with open(filename, mode="r", encoding="utf-8-sig") as csvfile:
        # Ensure we treat commas as delimiter
        reader = csv.DictReader(csvfile, delimiter=',')
        for row in reader:
            lists_data.append({
                "name": row["Name"].strip(),
                "listId": row["ListId"].strip()
            })
    return lists_data

def load_properties(filename: str):
    """
    Load properties from a TXT file, one property per line.
    Returns both a list (to preserve order) and a set (for quick membership checks).
    """
    prop_list = []
    prop_set = set()
    with open(filename, mode="r", encoding="utf-8-sig") as txtfile:
        for line in txtfile:
            p = line.strip()
            if p:
                prop_list.append(p)
                prop_set.add(p)
    return prop_list, prop_set

def log_result(logfile: str, list_name: str, list_id: str, status_code: int, error_message: str = ""):
    """
    Append a single log entry to the log CSV file.
    Columns: [DateTime, List_Name, List_ID, StatusCode, ErrorMessage]
    """
    now = datetime.datetime.now().isoformat()
    with open(logfile, mode="a", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow([now, list_name, list_id, status_code, error_message])

def traverse_filter_branches(branch, found_props, properties_to_check):
    """
    Recursively traverse 'filterBranches' to find filters that use 'property'.
    If the property is in properties_to_check, add it to found_props.
    """
    if not branch:
        return

    # Check direct filters in this branch
    filters = branch.get("filters", [])
    for f in filters:
        # If filterType == 'PROPERTY', we look for 'property'
        if f.get("filterType") == "PROPERTY":
            prop_name = f.get("property", "")
            # Debug line: remove or comment out once you've confirmed it works
            #print(f"DEBUG: Found filter property='{prop_name}' (checking against {properties_to_check})")

            if prop_name in properties_to_check:
                found_props.add(prop_name)

    # Recurse into sub-branches
    sub_branches = branch.get("filterBranches", [])
    for sb in sub_branches:
        traverse_filter_branches(sb, found_props, properties_to_check)

def check_list_properties(response_json: dict, properties_to_check: set):
    """
    Return a set of property names found in the list's filters that match properties_to_check.
    The relevant portion of the JSON is typically: response_json["list"]["filterBranch"].
    """
    found_props = set()
    list_obj = response_json.get("list", {})
    top_branch = list_obj.get("filterBranch", {})
    traverse_filter_branches(top_branch, found_props, properties_to_check)
    return found_props

def main():
    # Load the lists from CSV, and properties from text
    lists_data = load_list_ids(LISTS_CSV)
    property_list, property_set = load_properties(PROPERTIES_TXT)

    # Prepare the log file: if it doesn't exist, write a header
    if not os.path.exists(LOG_CSV):
        with open(LOG_CSV, mode="w", encoding="utf-8", newline="") as csvfile:
            writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(["DateTime", "List_Name", "List_ID", "StatusCode", "ErrorMessage"])

    # Overwrite or create 'checked_lists.csv' with a header
    with open(CHECKED_LISTS_CSV, mode="w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        header = ["Name", "ListId"] + property_list
        writer.writerow(header)

        for item in lists_data:
            list_name = item["name"]
            list_id = item["listId"]
            row_values = [list_name, list_id]

            url = f"https://api.hubapi.com/crm/v3/lists/{list_id}?includeFilters=true"
            headers = {
                "Authorization": f"Bearer {HUBSPOT_BEARER}",
                "Content-Type": "application/json"
            }

            try:
                response = requests.get(url, headers=headers)
                status_code = response.status_code

                if response.ok:
                    data = response.json()
                    found_props = check_list_properties(data, property_set)

                    # For each property in property_list, mark "TRUE" if it's found, else ""
                    for prop in property_list:
                        row_values.append("TRUE" if prop in found_props else "")

                    writer.writerow(row_values)
                    log_result(LOG_CSV, list_name, list_id, status_code, "")

                else:
                    # If non-OK response, mark all as "ERROR"
                    row_values.extend(["ERROR"] * len(property_list))
                    writer.writerow(row_values)
                    error_message = f"API error: {response.text}"
                    log_result(LOG_CSV, list_name, list_id, status_code, error_message)

            except requests.RequestException as e:
                # If a request exception occurs, mark all as "ERROR"
                row_values.extend(["ERROR"] * len(property_list))
                writer.writerow(row_values)
                log_result(LOG_CSV, list_name, list_id, 0, str(e))

if __name__ == "__main__":
    main()
