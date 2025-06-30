import pylast
import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
import time
import random
import os
from datetime import datetime
from dotenv import load_dotenv

__version__ = "1.0.0"

load_dotenv()

# --- Configuration ---
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_API_SECRET = os.getenv("LASTFM_API_SECRET")
LASTFM_USERNAME = os.getenv("LASTFM_USERNAME")
LASTFM_PASSWORD = os.getenv("LASTFM_PASSWORD")

SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI")
SPOTIFY_PLAYLIST_ID = os.getenv("SPOTIFY_PLAYLIST_ID")

LOG_FILE = os.getenv("LOG_FILE", "/home/rolle/spotify-my-station/spotify-my-station.log")

NUMBER_OF_TRACKS = int(os.getenv("NUMBER_OF_TRACKS", "100"))

# --- Functions ---
def authenticate_lastfm():
    try:
        network = pylast.LastFMNetwork(
            api_key=LASTFM_API_KEY,
            api_secret=LASTFM_API_SECRET,
            username=LASTFM_USERNAME,
            password_hash=pylast.md5(LASTFM_PASSWORD),
        )
        return network
    except Exception as e:
        log_message(f"Last.fm Authentication Error: {e}", 'red')
        return None


def authenticate_spotify():
    try:
        cache_path = os.path.join(os.path.dirname(__file__), '.spotify_cache')
        
        # Check if we already have a cached token
        if os.path.exists(cache_path):
            log_message("Using cached Spotify authentication token.")
        else:
            log_message("No cached Spotify token found. Setting up first-time authentication...", 'yellow')
        
        auth_manager = SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope="playlist-modify-public playlist-modify-private",
            cache_path=cache_path,
            open_browser=False
        )
        
        # If no cached token, provide manual authorization instructions
        if not os.path.exists(cache_path):
            auth_url = auth_manager.get_authorize_url()
            log_message("=" * 80, 'yellow')
            log_message("SPOTIFY AUTHENTICATION REQUIRED", 'yellow')
            log_message("=" * 80, 'yellow')
            log_message("1. Open this URL in your browser:", 'yellow')
            log_message(f"   {auth_url}")
            log_message("2. Log in to Spotify and authorize the application", 'yellow')
            log_message("3. You'll be redirected to a Spotify page that shows an error - this is normal!", 'yellow')
            log_message("4. Copy the entire URL from your browser's address bar", 'yellow')
            log_message("5. It should look like: https://developer.spotify.com/callback?code=...", 'yellow')
            log_message("=" * 80, 'yellow')
            
            try:
                redirect_response = input("Paste the redirect URL here: ").strip()
                if not redirect_response:
                    log_message("No URL provided. Authentication cancelled.", 'red')
                    return None
                    
                auth_manager.parse_response_code(redirect_response)
                log_message("Authorization code received successfully!", 'green')
                
            except KeyboardInterrupt:
                log_message("\nAuthentication cancelled by user.", 'red')
                return None
            except Exception as e:
                log_message(f"Error processing redirect URL: {e}", 'red')
                return None
        
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        # Test the connection
        user_info = sp.me()
        log_message(f"Spotify authentication successful! Logged in as: {user_info['display_name']}", 'green')
        
        # Save the token for future runs
        if os.path.exists(cache_path):
            log_message("Authentication token cached for future runs.", 'green')
        
        return sp
        
    except Exception as e:
        log_message(f"Spotify Authentication Error: {e}", 'red')
        return None


def get_random_tracks_from_lastfm(network, num_tracks=100):
    try:
        log_message("Getting Last.fm user profile...")
        user = network.get_user(LASTFM_USERNAME)
        
        log_message("Fetching loved tracks from Last.fm (this may take a while for large collections)...")
        loved_tracks = user.get_loved_tracks(limit=None)
        
        log_message("Processing loved tracks data...")
        all_tracks = []
        track_count = 0
        
        for item in loved_tracks:
            track_count += 1
            all_tracks.append(item.track)
            
            # Progress update every 1000 tracks
            if track_count % 1000 == 0:
                log_message(f"Processed {track_count} loved tracks so far...", 'yellow')
        
        log_message(f"Finished processing. Total loved tracks found: {len(all_tracks)}", 'green')
        
        if len(all_tracks) < num_tracks:
            log_message(f"Warning: Less than {num_tracks} loved tracks found. Using {len(all_tracks)} tracks.", 'yellow')
            num_tracks = len(all_tracks)

        log_message(f"Selecting {num_tracks} random tracks from {len(all_tracks)} total tracks...")
        random_tracks = random.sample(all_tracks, num_tracks)
        return random_tracks
    except Exception as e:
        log_message(f"Error getting random tracks from Last.fm: {e}", 'red')
        return None


def update_spotify_playlist(sp, playlist_id, tracks):
    try:
        user_id = sp.me()["id"]
        track_uris = []
        not_found_count = 0 #Counts how many tracks were not found
        for track in tracks:
            search_results = sp.search(
                q=f"track:{track.title} artist:{track.artist.name}", type="track", limit=1
            )
            if search_results["tracks"]["items"]:
                track_uri = search_results["tracks"]["items"][0]["uri"]
                track_uris.append(track_uri)
            else:
                log_message(f"Track not found: {track.title} by {track.artist.name}", 'yellow')
                not_found_count += 1

        # Clear existing playlist
        existing_tracks = sp.playlist_items(playlist_id)
        track_ids_to_remove = []

        for item in existing_tracks['items']:
          track_ids_to_remove.append(item['track']['uri'])
        #Spotify API only allows deleting 100 at a time
        for i in range(0, len(track_ids_to_remove), 100):
          sp.playlist_remove_all_occurrences_of_items(playlist_id, track_ids_to_remove[i:i+100])
        # Add new tracks in batches of 100
        for i in range(0, len(track_uris), 100):
            sp.playlist_add_items(playlist_id, track_uris[i : i + 100])

        log_message(f"Playlist updated. Added {len(track_uris)} tracks. {not_found_count} tracks not found.", 'green')


    except Exception as e:
        log_message(f"Error updating Spotify playlist: {e}", 'red')


def log_message(message, color=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp}: {message}\n"
    
    # Color codes for console output
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'reset': '\033[0m'
    }
    
    # Print to console with color
    if color and color in colors:
        colored_message = f"{colors[color]}{log_entry.strip()}{colors['reset']}"
        print(colored_message)
    else:
        print(log_entry.strip())
    
    # Write to file without color codes
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)


def job():
    log_message(f"Starting playlist update job (version {__version__})...", 'yellow')
    log_message(f"Target playlist ID: {SPOTIFY_PLAYLIST_ID}")
    log_message(f"Requesting {NUMBER_OF_TRACKS} tracks from Last.fm user: {LASTFM_USERNAME}")
    
    log_message("Authenticating with Last.fm...")
    lastfm_network = authenticate_lastfm()
    if not lastfm_network:
        log_message("Last.fm authentication failed. Aborting.", 'red')
        return
    log_message("Last.fm authentication successful.", 'green')

    log_message("Authenticating with Spotify...")
    spotify_client = authenticate_spotify()
    if not spotify_client:
        log_message("Spotify authentication failed. Aborting.", 'red')
        return
    log_message("Spotify authentication successful.", 'green')

    log_message("Fetching random tracks from Last.fm loved tracks...")
    tracks = get_random_tracks_from_lastfm(lastfm_network, NUMBER_OF_TRACKS)
    if not tracks:
        log_message("Failed to retrieve tracks from Last.fm. Aborting.", 'red')
        return
    log_message(f"Successfully retrieved {len(tracks)} tracks from Last.fm.", 'green')

    log_message("Updating Spotify playlist...")
    update_spotify_playlist(spotify_client, SPOTIFY_PLAYLIST_ID, tracks)
    log_message("Playlist update job completed successfully.", 'green')


# --- Main ---
if __name__ == "__main__":
    job()
