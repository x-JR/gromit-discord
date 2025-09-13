def get_this_month_range():
    today = datetime.now(timezone.utc)
    start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Get the number of days in the current month
    _, num_days = calendar.monthrange(today.year, today.month)
    end_of_month = today.replace(day=num_days, hour=23, minute=59, second=59, microsecond=0)
    return start_of_month, end_of_month

def fetch_calendar(url):
    response = requests.get(url)
    response.raise_for_status()
    return Calendar(response.text)

def get_events_this_month(calendar):
    start, end = get_this_month_range()
    events = []
    for event in calendar.events:
        event_start = event.begin.datetime.replace(tzinfo=timezone.utc)
        if start <= event_start <= end:
            events.append(event)
    return events

def write_ufc_event(db_config, table_name, record_data):
    """
    Insert a record into the ufc_events table.
    
    Args:
        db_config (dict): Database connection parameters
        table_name (str): Name of the table to insert into
        record_data (dict): Column-value pairs for the record
        
    Returns:
        int: Last inserted row ID (or None if no auto-increment column)
        
    Raises:
        RuntimeError: For database operation errors
        ValueError: If record_data is empty
    """
    if not record_data:
        raise ValueError("Record data cannot be empty")
    
    connection = None
    cursor = None
    try:
        # Configure UTF-8mb4 for emoji support
        connection_params = db_config.copy()
        connection_params.setdefault('charset', 'utf8mb4')
        connection_params.setdefault('collation', 'utf8mb4_unicode_ci')
        # Establish database connection
        connection = mysql.connector.connect(**connection_params)
        cursor = connection.cursor()
        
        # Prepare parameterized query
        columns = ", ".join([f"`{col}`" for col in record_data.keys()])
        placeholders = ", ".join(["%s"] * len(record_data))
        query = f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})"
        
        # Execute query with values
        values = tuple(record_data.values())
        cursor.execute(query, values)
        connection.commit()
        
        # Return last inserted ID if exists
        if cursor.lastrowid:
            return cursor.lastrowid
        return None
        
    except Error as e:
        if connection:
            connection.rollback()
        raise RuntimeError(f"Database error: {e}")
    finally:
        # Clean up resources
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

def upsert_ufc_event(db_config, table_name, event_data):
    """
    Insert or update a UFC event record based on event_name.
    If a record with the same event_name exists, update it if any details differ.
    Otherwise, insert a new record.
    """
    connection = None
    cursor = None
    try:
        connection_params = db_config.copy()
        connection_params.setdefault('charset', 'utf8mb4')
        connection_params.setdefault('collation', 'utf8mb4_unicode_ci')
        connection = mysql.connector.connect(**connection_params)
        cursor = connection.cursor(dictionary=True)

        # Check for existing record by event_name
        select_query = f"SELECT * FROM `{table_name}` WHERE event_name = %s"
        cursor.execute(select_query, (event_data['event_name'],))
        existing = cursor.fetchone()

        if existing:
            # Compare fields
            needs_update = False
            for key in event_data:
                if str(existing.get(key)) != str(event_data[key]):
                    needs_update = True
                    break
            if needs_update:
                set_clause = ", ".join([f"`{k}` = %s" for k in event_data.keys()])
                update_query = f"UPDATE `{table_name}` SET {set_clause} WHERE event_name = %s"
                values = tuple(event_data.values()) + (event_data['event_name'],)
                cursor.execute(update_query, values)
                connection.commit()
                print(f"Updated event: {event_data['event_name']}")
                return 'updated'
            else:
                print(f"No changes for event: {event_data['event_name']}")
                return 'no_change'
        else:
            # Insert new record
            columns = ", ".join([f"`{col}`" for col in event_data.keys()])
            placeholders = ", ".join(["%s"] * len(event_data))
            insert_query = f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})"
            cursor.execute(insert_query, tuple(event_data.values()))
            connection.commit()
            print(f"Inserted event: {event_data['event_name']}")
            return 'inserted'
    except Error as e:
        if connection:
            connection.rollback()
        raise RuntimeError(f"Database error: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

def check_and_store_ufc_events(db_config):
    """Fetches and stores UFC events for the month."""
    print("Running monthly UFC event check...")
    try:
        url = "https://raw.githubusercontent.com/clarencechaan/ufc-cal/ics/UFC.ics"
        cal = fetch_calendar(url)
        events = get_events_this_month(cal)
        
        if not events:
            print("No UFC events found for this month.")
            return

        # Define AEST timezone
        aest = pytz.timezone('Australia/Sydney')

        for event in events:
            description = event.description or ""
            url_pattern = r'(https?://\S+)'
            match = re.search(url_pattern, description)
            event_url = match.group(1) if match else None

            # Convert event date to AEST
            event_utc = event.begin.datetime.replace(tzinfo=timezone.utc)
            event_aest = event_utc.astimezone(aest)

            event_data = {
                'event_name': event.name,
                'event_date': event_aest.strftime('%Y-%m-%d %H:%M:%S'),
                'event_url': event_url,
                'event_description': description,
                'event_location': event.location
            }
            
            upsert_ufc_event(db_config, 'ufc_events', event_data)

    except Exception as e:
        print(f"Error in check_and_store_ufc_events: {e}")

def format_event_for_discord(record, webhook_url, url=None):
    """
    Format a SQL record as a Discord embed and send it to the given webhook URL.
    Args:
        record (dict): The SQL record (column names as keys)
        webhook_url (str): The Discord webhook URL
        url (str, optional): Fallback URL for the embed
    """
    import requests
    # Use event_url from record if available, else fallback to url param
    event_url = record.get('event_url') or url
    embed = {
        "title": record.get('event_name', 'UFC Event'),
        "description": (record.get('event_description') or '').strip(),
        "url": event_url,
        "color": None,
        "fields": [
            {"name": "Event Date:", "value": record.get('event_date', 'N/A')},
            {"name": "Location:", "value": record.get('event_location', 'N/A')}
        ]
    }
    payload = {
        "content": None,
        "embeds": [embed],
        "attachments": []
    }
    response = requests.post(webhook_url, json=payload)
    if response.status_code >= 400:
        print(f"Failed to send to Discord webhook: {response.status_code} {response.text}")
    else:
        print(f"Event sent to Discord webhook: {record.get('event_name')}")
    return response
