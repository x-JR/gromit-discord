# Gromit Discord Bot

A feature-rich Discord bot for server management, UFC event notifications, and more. Built with Python.

## Features
- **UFC Event Monitoring**: Automatically fetches, stores, and posts UFC event notifications for today and the week to configured channels (if enabled).
- **Wall of Shame**: Archive and display notable messages from your server.
- **Random Responses**: Fetch random responses from a database table.
- **Admin Elevation**: Automatically grants admin privileges to a specified user on join.
- **Custom Rich Presence**: Set the bot's presence to show Minecraft server status or a static message.

## Requirements
- Python 3.10+
- MySQL/MariaDB database
- Discord bot token
- Docker (optional, for containerized deployment)

## Setup
1. **Clone the repository:**
   ```bash
   git clone https://github.com/x-JR/gromit-discord.git
   cd gromit-discord
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure environment variables:**
   Create a `.env` file in the project root and fill in the required values. You can use `.env.example` as a template.

## Environment Variables

### Core Bot Settings
- `PREFIX`: The prefix for bot commands (e.g., `$`, `!`, `?`).
- `ADMIN_USER_ID`: The Discord User ID of the bot administrator. This user will be granted administrative privileges on servers the bot joins.
- `DISCORD_BOT_TOKEN`: The token for your Discord bot from the Discord Developer Portal.

### Rich Presence
- `RICH_PRESENCE_MODE`: Controls the bot's activity status.
  - `minecraft`: Displays the player count of a Minecraft server (requires Crafty API settings).
  - `static`: Displays a custom static message.
- `RICH_PRESENCE_STATIC_STRING`: The text to display when `RICH_PRESENCE_MODE` is set to `static`.

### Database
- `SQL_SERVER`: The hostname or IP address of your MySQL/MariaDB server.
- `SQL_USER`: The username for the database connection.
- `SQL_PASSWORD`: The password for the database user.
- `SQL_DATABASE`: The name of the database the bot will use.

### Crafty API (for Minecraft Rich Presence)
These are required if `RICH_PRESENCE_MODE` is set to `minecraft`.
- `CRAFTY_API_URL`: The URL for your Crafty Controller API.
- `CRAFTY_API_TOKEN`: The API token for authenticating with Crafty.
- `CRAFTY_SERVER_ID`: The ID of the Minecraft server you want to monitor in Crafty.
- `CRAFTY_INSECURE_SSL`: Set to `true` to disable SSL certificate verification if your Crafty instance uses a self-signed certificate. Defaults to `false`.

### UFC Monitoring
- `UFC_MONITORING`: Set to `true` to enable automatic fetching and notification of UFC events. Defaults to `false`.

## Running the Bot
```bash
python bot.py
```

## Docker Usage
1. **Build the image:**
   ```bash
   docker build -t gromit-discord .
   ```
2. **Run the container:**
   ```bash
   docker run --env-file .env gromit-discord
   ```
- The Dockerfile is configured for unbuffered output so all print statements appear in logs.

## Database Tables
- `ufc_events`: Stores UFC event data.
- `ufc_notify_channels`: List of Discord channel IDs to notify.
- `wall_of_shame`: Stores notable messages.
- `response_table`: Stores random responses.

## Customization
- Add or remove features by editing `bot.py` and `ufc_fetch.py`.
- Add more commands or event listeners as needed.

