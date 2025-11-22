# 🎵 Spotify My Station

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54) ![Spotify](https://img.shields.io/badge/Spotify-1DB954?style=for-the-badge&logo=spotify&logoColor=white) ![Last.fm](https://img.shields.io/badge/last.fm-D51007?style=for-the-badge&logo=last.fm&logoColor=white) ![Chagtgpt](https://img.shields.io/badge/OpenAI-74aa9c?style=for-the-badge&logo=openai&logoColor=white) ![Google Gemini](https://img.shields.io/badge/Google%20Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white) ![Version](https://img.shields.io/badge/version-2.5.0-blue?style=for-the-badge)

![image](https://github.com/user-attachments/assets/6c3e1c17-483e-450f-ae59-60564c69548b)

A Python script that automatically creates an Apple Music "My Station"-style playlist on Spotify with quality-filtered recommendations. Combines 50% favorites with 50% discovery (AI + Last.fm), while filtering out obscure artists and low-quality tracks.

![Screenshot from 2025-06-30 19-49-25](https://github.com/user-attachments/assets/38b60f90-2725-4b56-9897-e644b5df7d1b)

## Features

- **Balanced discovery**: 50% favorites and 50% new tracks, blending familiarity with discovery
- **Apple Music My Station experience**: Mimics Apple Music's intelligent station algorithm
- **Smart mix**:
  - 50% your favorites (weighted by playcount, with 3+ day cooldown)
  - 20% AI discovery (GPT-5-mini or Gemini suggests NEW artists based on your taste)
  - 30% Last.fm discovery (similar artists from Last.fm collaborative filtering)
- **Quality filtering**: Blocks obscure artists (< 10k listeners), Christmas songs, AI-generated music, covers
- **Unlimited history tracking**: Tracks every song ever suggested with timestamps
- **Intelligent cooldown**: Minimum 3 days between repeats, overplay protection
- **Genre filtering**: Ban entire genres from your playlists
- **Automatic updates**: Runs hourly via cron job with fresh discoveries each time
- **Comprehensive logging**: Detailed logs showing discovery sources

**Note:** Spotify deprecated their Audio Features and Recommendations APIs on November 27, 2024.

## Requirements

- Python 3.6+
- Last.fm account with API access
- Spotify account with API access
- A Spotify playlist to update
- **OpenAI API key OR Google Gemini API key** (required for AI features)

## Setup

### 1. Virtual environment setup

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

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. API setup

#### Last.fm API

1. Go to https://www.last.fm/api/account/create
2. Create an API account and get your API key and secret

#### Spotify API

1. Go to https://developer.spotify.com/dashboard
2. Create a new app and get your client ID and secret
3. **IMPORTANT**: In "Redirect URIs", add exactly: `https://developer.spotify.com/callback`
   - Click "Add URI" and enter `https://developer.spotify.com/callback`
   - Click "Save" at the bottom of the page
   - This URI must match what's in your `.env` file
   - **Note**: This is Spotify's own testing redirect URI

### 4. Environment configuration

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

# AI API credentials and configuration (required)
AI_PROVIDER=openai  # Options: openai, gemini
OPENAI_API_KEY=your_openai_api_key  # Also accepts OPEN_AI_API_KEY
GEMINI_API_KEY=your_gemini_api_key

LOG_FILE=/path/to/your/spotify-my-station.log
NUMBER_OF_TRACKS=100
```

### 5. Get Spotify playlist ID

1. Open Spotify and navigate to your playlist
2. Click "Share" > "Copy link to playlist"
3. Extract the playlist ID from the URL (the part after `/playlist/`)

### 6. First run authentication

The script handles Spotify authentication with clear terminal instructions:

#### First run process

1. Script displays an authorization URL
2. Copy this URL and open it in your browser
3. Log in to Spotify and click "Agree" to authorize
4. You'll be redirected to `https://developer.spotify.com/callback?code=...` (Spotify's own page will show an error - this is normal!)
5. **Copy the entire URL from your browser's address bar** (including the `?code=...` part)
6. Paste this URL back into the terminal when prompted
7. Script saves token to `.spotify_cache` for future runs

**Security note**: Using Spotify's own developer callback URL is completely safe - it's their official testing redirect URI.
**Subsequent runs**: Uses cached tokens automatically (no interaction needed)

## Usage

### Basic Usage

```bash
python spotify-my-station.py
```

**AI-powered by default!** The script creates intelligent playlists that mimic Apple Music's "My Station" feature with quality filtering.

**How it works:**
- Analyzes your entire Last.fm loved tracks collection
- Creates an intelligent mix of familiar favorites and new discoveries
- Learns from your listening patterns and playlist update history
- Balances songs you love with AI-curated recommendations based on your taste
- Filters out obscure artists, Christmas music, covers, and AI-generated tracks

**Mix Strategy:**
- 50% songs from your loved tracks collection (weighted by playcount)
- 20% tracks from AI-recommended artists based on your taste analysis
- 30% songs from similar artists discovered via Last.fm recommendations

**Quality Control:**
- Only artists with 10,000+ Last.fm listeners
- Blocks Christmas songs, AI music, covers, tributes, karaoke
- One track per artist for maximum variety

### Custom Playlist

```bash
python spotify-my-station.py --playlist PLAYLIST_ID
```
Updates a specific playlist instead of the default one from environment variables.

### Genre Filtering

Create a `banned.json` file to filter out unwanted genres:

```json
{
  "banned_items": [
    "song:Hello Kitty",
    "artist:Streetgazer", 
    "genre:hip hop",
    "genre:rap"
  ]
}
```

Use the provided `banned.example.json` as a template. Supported prefixes:
- `song:` - Ban specific songs
- `artist:` - Ban all songs by an artist
- `album:` - Ban all songs from an album
- `genre:` - Ban all songs with this genre

### Help

```bash
python spotify-my-station.py --help
```
Shows all available options.

### Automated runs with cron

To run the script automatically every hour:

1. Open your crontab:
   ```bash
   crontab -e
   ```

2. Add this line:
   ```bash
   # Spotify My Station
   0 * * * * cd /home/rolle/spotify-my-station && /home/rolle/spotify-my-station/venv/bin/python spotify-my-station.py --playlist xxxxxxxxxxx >> /dev/null 2>&1
   ```

## Configuration

The script can be configured through environment variables in the `.env` file:

- `NUMBER_OF_TRACKS`: Number of tracks to add to the playlist (default: 100)
- `LOG_FILE`: Path to the log file

## Logging

The script logs all operations to both the console and a log file. Check the log file for detailed information about:
- Authentication status
- Number of tracks processed
- Tracks not found on Spotify
- Error messages

## Troubleshooting

1. **Authentication issues**: Make sure your API credentials are correct in the `.env` file
2. **Playlist not updating**: Verify the playlist ID and ensure your Spotify app has the correct permissions
3. **Tracks not found**: Some Last.fm tracks might not be available on Spotify
4. **Permission errors**: Ensure the script has write permissions for the log file location
