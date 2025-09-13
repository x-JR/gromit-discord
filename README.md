# Gromit Discord Bot

A feature-rich Discord bot for server management, UFC event notifications, and more. Built with Python.

## Features
- **UFC Event Monitoring**: Automatically fetches, stores, and posts UFC event notifications for today and the week to configured channels (if enabled).
- **Wall of Shame**: Archive and display notable messages from your server.
- **Random Responses**: Fetch random responses from a database table.
- **Admin Elevation**: Automatically grants admin privileges to a specified user on join.

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
   Create a `.env` file in the project root (see below for required variables).

### .env Example
```
PREFIX=$
ADMIN_USER_ID=your_discord_user_id
SQL_SERVER=your_db_host
SQL_USER=your_db_user
SQL_PASSWORD=your_db_password
SQL_DATABASE=your_db_name
DISCORD_BOT_TOKEN=your_discord_bot_token
UFC_MONITORING=true
```

- Set `UFC_MONITORING` to `true` to enable UFC event features.

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
