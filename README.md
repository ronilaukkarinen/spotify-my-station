# 🎵 Spotify My Station

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54) ![Spotify](https://img.shields.io/badge/Spotify-1DB954?style=for-the-badge&logo=spotify&logoColor=white) ![Last.fm](https://img.shields.io/badge/last.fm-D51007?style=for-the-badge&logo=last.fm&logoColor=white) ![Version](https://img.shields.io/badge/version-1.0.0-blue?style=for-the-badge) ![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge) ![Cron](https://img.shields.io/badge/Cron-Compatible-orange?style=for-the-badge&logo=linux&logoColor=white)

![image](https://github.com/user-attachments/assets/6c3e1c17-483e-450f-ae59-60564c69548b)

## Features

A Python script that automatically updates a Spotify playlist with random tracks from your Last.fm loved tracks. The script runs hourly to keep your playlist fresh with music you've previously loved. 🔄

## ✨ Features

![Screenshot from 2025-06-30 19-49-25](https://github.com/user-attachments/assets/38b60f90-2725-4b56-9897-e644b5df7d1b)

## Requirements

- 🎶 Fetches random tracks from your Last.fm loved tracks
- 📝 Updates a specified Spotify playlist with these tracks
- ⏰ Designed to run via cron job scheduling
- 📊 Logs all operations with timestamps
- 🔄 Removes existing tracks before adding new ones

## 📋 Requirements

- 🐍 Python 3.6+
- 🎵 Last.fm account with API access
- 🟢 Spotify account with API access
- 📜 A Spotify playlist to update

## 🚀 Setup

### 1. 🐍 Virtual Environment Setup

Create and activate a virtual environment:

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate
```

### 2. 📦 Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. 🔑 API Setup

#### 🎵 Last.fm API
1. Go to https://www.last.fm/api/account/create
2. Create an API account and get your API key and secret

#### 🟢 Spotify API
1. Go to https://developer.spotify.com/dashboard
2. Create a new app and get your client ID and secret
3. **IMPORTANT**: In "Redirect URIs", add exactly: `https://developer.spotify.com/callback`
   - Click "Add URI" and enter `https://developer.spotify.com/callback`
   - Click "Save" at the bottom of the page
   - This URI must match what's in your `.env` file
   - **Note**: This is Spotify's own testing redirect URI

### 4. ⚙️ Environment Configuration

Copy the `.env.example` file to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your API credentials:

```env
LASTFM_API_KEY=your_lastfm_api_key
LASTFM_API_SECRET=your_lastfm_api_secret
LASTFM_USERNAME=your_lastfm_username
LASTFM_PASSWORD=your_lastfm_password

SPOTIPY_CLIENT_ID=your_spotify_client_id
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret
SPOTIPY_REDIRECT_URI=https://developer.spotify.com/callback
SPOTIFY_PLAYLIST_ID=your_spotify_playlist_id

LOG_FILE=/path/to/your/spotify-my-station.log
NUMBER_OF_TRACKS=100
```

### 5. 🆔 Get Spotify Playlist ID

1. Open Spotify and navigate to your playlist
2. Click "Share" > "Copy link to playlist"
3. Extract the playlist ID from the URL (the part after `/playlist/`)

### 6. 🔐 First Run Authentication

The script handles Spotify authentication with clear terminal instructions:

**First Run Process:**
1. Script displays an authorization URL
2. Copy this URL and open it in your browser
3. Log in to Spotify and click "Agree" to authorize
4. You'll be redirected to `https://developer.spotify.com/callback?code=...` (Spotify's own page will show an error - this is normal!)
5. **Copy the entire URL from your browser's address bar** (including the `?code=...` part)
6. Paste this URL back into the terminal when prompted
7. Script saves token to `.spotify_cache` for future runs

**Security Note**: Using Spotify's own developer callback URL is completely safe - it's their official testing redirect URI.

**Subsequent runs**: Uses cached tokens automatically (no interaction needed)

## 🎯 Usage

### 🚀 Single Run

```bash
python spotify-my-station.py
```

### ⏰ Automated Runs with Cron

To run the script automatically every hour:

1. Open your crontab:
   ```bash
   crontab -e
   ```

2. Add this line:
   ```bash
   0 * * * * cd /home/rolle/spotify-my-station && /home/rolle/spotify-my-station/venv/bin/python spotify-my-station.py >> /dev/null 2>&1
   ```

## ⚙️ Configuration

The script can be configured through environment variables in the `.env` file:

- 🔢 `NUMBER_OF_TRACKS`: Number of tracks to add to the playlist (default: 100)
- 📄 `LOG_FILE`: Path to the log file

## 📝 Logging

The script logs all operations to both the console and a log file. Check the log file for detailed information about:
- 🔐 Authentication status
- 📊 Number of tracks processed
- ❌ Tracks not found on Spotify
- 🚨 Error messages

## 🔧 Troubleshooting

1. **🔑 Authentication Issues**: Make sure your API credentials are correct in the `.env` file
2. **📝 Playlist Not Updating**: Verify the playlist ID and ensure your Spotify app has the correct permissions
3. **🎵 Tracks Not Found**: Some Last.fm tracks might not be available on Spotify
4. **📁 Permission Errors**: Ensure the script has write permissions for the log file location

## 📄 License

This project is open source and available under the MIT License.
