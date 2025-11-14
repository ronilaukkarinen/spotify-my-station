import pylast
import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
import time
import random
import os
import argparse
from datetime import datetime
from dotenv import load_dotenv
import json
from collections import Counter, defaultdict
import re
try:
    import openai
except ImportError:
    openai = None
try:
    import google.generativeai as genai
except ImportError:
    genai = None

__version__ = "2.4.0"

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

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

LOG_FILE = os.getenv("LOG_FILE", "/home/rolle/spotify-my-station/spotify-my-station.log")
HISTORY_FILE = os.getenv("HISTORY_FILE", "/home/rolle/spotify-my-station/playlist-history.json")
BANNED_FILE = os.getenv("BANNED_FILE", "/home/rolle/spotify-my-station/banned.json")

NUMBER_OF_TRACKS = int(os.getenv("NUMBER_OF_TRACKS", "100"))
RANDOMITY_FACTOR = int(os.getenv("RANDOMITY_FACTOR", "50"))  # 0-100 scale

# --- Functions ---
# Playlist history loading removed - using only Last.fm data for freshness

def load_playlist_history():
    """Load playlist history from file."""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        return {"recent_tracks": [], "recent_artists": []}
    except Exception as e:
        log_message(f"Error loading playlist history: {e}", 'yellow')
        return {"recent_tracks": [], "recent_artists": []}


def load_banned_items():
    """Load list of banned songs, artists, and albums."""
    try:
        if os.path.exists(BANNED_FILE):
            with open(BANNED_FILE, 'r') as f:
                data = json.load(f)
                banned_items = {
                    'songs': [],
                    'artists': [],
                    'albums': [],
                    'genres': []
                }

                for item in data.get("banned_items", []):
                    item_lower = item.lower()
                    if item_lower.startswith('song:'):
                        banned_items['songs'].append(item_lower[5:].strip())
                    elif item_lower.startswith('artist:'):
                        banned_items['artists'].append(item_lower[7:].strip())
                    elif item_lower.startswith('album:'):
                        banned_items['albums'].append(item_lower[6:].strip())
                    elif item_lower.startswith('genre:'):
                        banned_items['genres'].append(item_lower[6:].strip())

                return banned_items
        return {'songs': [], 'artists': [], 'albums': [], 'genres': []}
    except Exception as e:
        log_message(f"Error loading banned items: {e}", 'yellow')
        return {'songs': [], 'artists': [], 'albums': [], 'genres': []}




def save_playlist_history(tracks):
    """Save current playlist tracks with timestamps for unlimited history tracking."""
    try:
        history = load_playlist_history()
        banned_items = load_banned_items()
        current_time = datetime.now().isoformat()

        # Get or create track_history dict
        if "track_history" not in history:
            history["track_history"] = {}

        saved_count = 0
        for track in tracks:
            # Double-check that we're not saving banned items
            if not is_banned_item(track.title, track.artist.name, None, banned_items):
                track_key = f"{track.title.lower()}|{track.artist.name.lower()}"

                # Update or create track entry
                if track_key not in history["track_history"]:
                    history["track_history"][track_key] = {
                        "first_suggested": current_time,
                        "last_suggested": current_time,
                        "times_suggested": 1
                    }
                else:
                    history["track_history"][track_key]["last_suggested"] = current_time
                    history["track_history"][track_key]["times_suggested"] += 1

                saved_count += 1

        # Keep legacy fields for backward compatibility but unused
        history["recent_tracks"] = []
        history["recent_artists"] = []
        history["last_updated"] = current_time

        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)

        log_message(f"Saved {saved_count} tracks to unlimited history (total: {len(history['track_history'])} tracks tracked)", 'green')

    except Exception as e:
        log_message(f"Error saving playlist history: {e}", 'yellow')


def cleanup_old_history():
    """Clean up old history entries to prevent feedback loops and remove banned items."""
    try:
        history = load_playlist_history()
        banned_items = load_banned_items()
        
        cleaned_tracks = []
        cleaned_artists = []
        removed_count = 0
        
        # Clean banned items from history
        for track_key in history.get("recent_tracks", []):
            if '|' in track_key:
                track_title, artist_name = track_key.split('|', 1)
                if not is_banned_item(track_title, artist_name, None, banned_items):
                    cleaned_tracks.append(track_key)
                else:
                    removed_count += 1
            else:
                cleaned_tracks.append(track_key)
        
        # Clean banned artists from history
        for artist_key in history.get("recent_artists", []):
            if not is_banned_item('', artist_key, None, banned_items):
                cleaned_artists.append(artist_key)
            else:
                removed_count += 1
        
        # Check if history is too large (indicates feedback loop)
        if len(cleaned_tracks) > 200:
            log_message("Detected large history file, cleaning up to prevent feedback loops...", 'yellow')
            # Keep only the most recent entries
            max_tracks = int(NUMBER_OF_TRACKS * 1.5)
            cleaned_tracks = cleaned_tracks[:max_tracks]
            cleaned_artists = cleaned_artists[:max_tracks]
        
        # Update history
        history["recent_tracks"] = cleaned_tracks
        history["recent_artists"] = cleaned_artists
        
        # Save cleaned history
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
        
        if removed_count > 0:
            log_message(f"Removed {removed_count} banned items from history.", 'green')
        log_message("History cleanup completed.", 'green')
        
    except Exception as e:
        log_message(f"Error cleaning up history: {e}", 'red')


# is_recently_used function removed - history system eliminated for better variety

def is_recently_used(track_title, artist_name, playlist_history):
    """Check if a track should be filtered based on cooldown period."""
    from datetime import datetime, timedelta

    track_key = f"{track_title.lower()}|{artist_name.lower()}"
    track_history = playlist_history.get("track_history", {})

    if track_key not in track_history:
        return False  # Never suggested before

    track_data = track_history[track_key]
    last_suggested = datetime.fromisoformat(track_data["last_suggested"])
    days_since = (datetime.now() - last_suggested).days
    times_suggested = track_data.get("times_suggested", 0)

    # Overplay protection: if suggested 5+ times in last 60 days, ban for 120 days
    if times_suggested >= 5 and days_since < 120:
        return True

    # Cooldown logic: 3 days minimum between plays (reduced for more familiarity)
    if days_since < 3:
        return True

    # Probabilistic cooldown for 3-90 days (more lenient for familiar tracks)
    if days_since < 14:
        return random.random() > 0.5  # 50% chance to include
    elif days_since < 30:
        return random.random() > 0.7  # 70% chance to include
    elif days_since < 90:
        return random.random() > 0.9  # 90% chance to include

    return False  # 90+ days or never suggested: always include


def get_track_genres(sp, track_uri):
    """Get genres for a track from Spotify."""
    try:
        track = sp.track(track_uri)
        artist_id = track['artists'][0]['id']
        artist = sp.artist(artist_id)
        return artist.get('genres', [])
    except:
        return []


def is_banned_item(track_title, artist_name, album_name, banned_items, genres=None):
    """Check if a track, artist, album, or genre is banned."""
    track_title_lower = track_title.lower()
    artist_name_lower = artist_name.lower()
    album_name_lower = album_name.lower() if album_name else ""
    
    # Check if song is banned
    if track_title_lower in banned_items['songs']:
        return True
    
    # Check if artist is banned
    if artist_name_lower in banned_items['artists']:
        return True
    
    # Check if album is banned
    if album_name_lower and album_name_lower in banned_items['albums']:
        return True
    
    # Check if any genre is banned
    if genres and banned_items['genres']:
        for genre in genres:
            genre_lower = genre.lower()
            for banned_genre in banned_items['genres']:
                if banned_genre in genre_lower or genre_lower in banned_genre:
                    return True
    
    return False


def apply_randomity(tracks_list, randomity_factor):
    """Apply randomity factor to track selection with improved variety."""
    if randomity_factor == 0:
        return tracks_list  # No randomization
    elif randomity_factor >= 80:
        # High randomization: full shuffle with some weighted selection
        random.shuffle(tracks_list)
        return tracks_list
    else:
        # Improved partial randomization: smaller chunks for more variety
        chunk_size = max(2, int(len(tracks_list) * (1 - randomity_factor / 100) * 0.5))  # Smaller chunks
        
        # Create overlapping chunks for better mixing
        chunks = []
        for i in range(0, len(tracks_list), chunk_size // 2):
            chunk_end = min(i + chunk_size, len(tracks_list))
            if i < len(tracks_list):
                chunks.append(tracks_list[i:chunk_end])
        
        # Shuffle within each chunk and shuffle chunks
        for chunk in chunks:
            random.shuffle(chunk)
        random.shuffle(chunks)
        
        # Flatten and remove duplicates while preserving order
        result = []
        seen = set()
        for chunk in chunks:
            for track in chunk:
                track_key = f"{track.title.lower()}|{track.artist.name.lower()}"
                if track_key not in seen:
                    result.append(track)
                    seen.add(track_key)
        
        return result[:len(tracks_list)]  # Return original length


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
            scope="playlist-modify-public playlist-modify-private user-read-private user-library-read user-read-recently-played",
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


def analyze_listening_history():
    try:
        if not os.path.exists(LOG_FILE):
            log_message("No log file found for history analysis", 'yellow')
            return {}
        
        log_message("Analyzing listening history from log file...")
        
        track_stats = defaultdict(int)
        artist_stats = defaultdict(int)
        total_updates = 0
        
        with open(LOG_FILE, 'r') as f:
            for line in f:
                if 'Added' in line and 'tracks' in line:
                    total_updates += 1
                elif 'Track not found:' in line:
                    match = re.search(r'Track not found: (.+) by (.+)', line)
                    if match:
                        track_name, artist_name = match.groups()
                        track_key = f"{track_name.strip()} - {artist_name.strip()}"
                        track_stats[track_key] += 1
                        artist_stats[artist_name.strip()] += 1
        
        analysis = {
            'total_playlist_updates': total_updates,
            'most_attempted_tracks': dict(Counter(track_stats).most_common(20)),
            'most_attempted_artists': dict(Counter(artist_stats).most_common(20)),
            'unique_tracks_attempted': len(track_stats),
            'unique_artists_attempted': len(artist_stats)
        }
        
        log_message(f"History analysis complete: {total_updates} playlist updates analyzed", 'green')
        return analysis
        
    except Exception as e:
        log_message(f"Error analyzing listening history: {e}", 'red')
        return {}


def get_random_tracks_from_lastfm(network, num_tracks=100, randomity_factor=50):
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
        
        # Use only 20% loved tracks for maximum variety
        loved_count = int(num_tracks * 0.2)
        if len(all_tracks) < loved_count:
            log_message(f"Warning: Less than {loved_count} loved tracks found. Using {len(all_tracks)} tracks.", 'yellow')
            loved_count = len(all_tracks)

        log_message(f"Selecting {loved_count} random tracks from {len(all_tracks)} total loved tracks...")
        
        # Improved selection: avoid recently played tracks from the start
        playlist_history = load_playlist_history()
        filtered_tracks = []
        for track in all_tracks:
            if not is_recently_used(track.title, track.artist.name, playlist_history):
                filtered_tracks.append(track)
        
        # If we have enough filtered tracks, use them; otherwise fall back to all tracks
        selection_pool = filtered_tracks if len(filtered_tracks) >= loved_count else all_tracks
        log_message(f"Using {len(selection_pool)} tracks from selection pool (filtered: {len(filtered_tracks)})")
        
        random_tracks = random.sample(selection_pool, min(loved_count, len(selection_pool)))
        
        # Add similar artists recommendations to fill remaining slots
        remaining_slots = num_tracks - loved_count
        if remaining_slots > 0:
            log_message(f"Getting {remaining_slots} additional tracks from similar artists...")
            similar_tracks = get_similar_artist_tracks(network, all_tracks, remaining_slots)
            if similar_tracks:
                random_tracks.extend(similar_tracks)
        
        # Apply randomity factor
        if randomity_factor > 0:
            log_message(f"Applying randomity factor of {randomity_factor}%...", 'yellow')
            random_tracks = apply_randomity(random_tracks, randomity_factor)
        
        return random_tracks
    except Exception as e:
        log_message(f"Error getting random tracks from Last.fm: {e}", 'red')
        return None


def get_similar_artist_tracks(network, loved_tracks, num_tracks):
    """Get tracks from similar artists based on user's loved tracks."""
    try:
        # Extract unique artists from loved tracks
        artists = list(set([track.artist.name for track in loved_tracks]))
        random.shuffle(artists)
        
        similar_tracks = []
        used_artists = set()
        
        # Get similar artists for a larger sample of user's artists for more variety
        sample_size = min(50, len(artists))  # Increased from 20 to 50
        for artist_name in artists[:sample_size]:  # Expanded artist pool
            if len(similar_tracks) >= num_tracks:
                break
                
            try:
                artist = network.get_artist(artist_name)
                similar_artists = artist.get_similar(limit=10)  # Increased from 5 to 10
                
                for similar_artist in similar_artists:
                    if len(similar_tracks) >= num_tracks:
                        break
                    
                    similar_artist_name = similar_artist.item.name
                    if similar_artist_name.lower() not in used_artists:
                        try:
                            top_tracks = similar_artist.item.get_top_tracks(limit=5)  # Increased from 3 to 5
                            for track in top_tracks:
                                if len(similar_tracks) >= num_tracks:
                                    break
                                
                                # Filter out live tracks
                                track_title = track.title.lower()
                                is_live = any(keyword in track_title for keyword in 
                                            ['live', 'live at', 'live from', 'live in', 'live on', 'concert', 'acoustic version'])
                                
                                if not is_live:
                                    similar_tracks.append(track)
                                    used_artists.add(similar_artist_name.lower())
                                    break
                        except Exception:
                            continue
            except Exception:
                continue
        
        log_message(f"Found {len(similar_tracks)} similar artist tracks", 'green')
        return similar_tracks
    except Exception as e:
        log_message(f"Error getting similar artist tracks: {e}", 'yellow')
        return []


def get_lastfm_recommendations(sp, network, num_tracks=100, randomity_factor=50):
    try:
        log_message("Getting recommendations using Last.fm similar artists...")
        
        # Get some random artists from loved tracks to find similar artists
        user = network.get_user(LASTFM_USERNAME)
        loved_tracks = user.get_loved_tracks(limit=200)
        
        # Extract unique artists from loved tracks
        artists_set = set()
        for item in loved_tracks:
            artists_set.add(item.track.artist.name)
        
        artists_list = list(artists_set)
        random.shuffle(artists_list)
        log_message(f"Found {len(artists_list)} unique artists from loved tracks")
        
        # First, add some loved tracks (25% of total)
        loved_tracks_list = []
        for item in loved_tracks:
            loved_tracks_list.append(item.track)
        
        loved_count = int(num_tracks * 0.25)
        recommended_tracks = random.sample(loved_tracks_list, min(loved_count, len(loved_tracks_list)))
        log_message(f"Added {len(recommended_tracks)} loved tracks ({len(recommended_tracks)}/{num_tracks})")
        
        # Get similar artists for remaining slots
        remaining_slots = num_tracks - len(recommended_tracks)
        similar_tracks = []
        seed_artists_used = 0
        max_seed_artists = 5  # Use up to 5 seed artists
        
        for artist_name in artists_list[:max_seed_artists]:
            if len(similar_tracks) >= remaining_slots:
                break
                
            try:
                log_message(f"Finding artists similar to: {artist_name}")
                artist = network.get_artist(artist_name)
                similar_artists = artist.get_similar(limit=10)
                
                # Get top tracks from similar artists
                for similar_artist in similar_artists:
                    if len(similar_tracks) >= remaining_slots:
                        break
                    
                    try:
                        # Get top tracks from this similar artist
                        top_tracks = similar_artist.item.get_top_tracks(limit=5)
                        
                        for track_item in top_tracks:
                            if len(similar_tracks) >= remaining_slots:
                                break
                            
                            track = track_item.item
                            
                            # Skip if this track is already in user's loved tracks
                            track_key = f"{track.title}|{track.artist.name}"
                            
                            # Search for track on Spotify to verify it exists
                            search_results = sp.search(
                                q=f"track:{track.title} artist:{track.artist.name}", 
                                type="track", 
                                limit=1
                            )
                            
                            if search_results["tracks"]["items"]:
                                # Create a track object that matches the expected format
                                class RecommendedTrack:
                                    def __init__(self, title, artist_name):
                                        self.title = title
                                        self.artist = type('Artist', (), {'name': artist_name})()
                                
                                similar_tracks.append(RecommendedTrack(
                                    track.title, 
                                    track.artist.name
                                ))
                                
                                if len(similar_tracks) % 10 == 0:
                                    log_message(f"Found {len(similar_tracks)} similar tracks so far...")
                    
                    except Exception as track_error:
                        # Skip this artist if we can't get their tracks
                        continue
                
                seed_artists_used += 1
                log_message(f"Processed {seed_artists_used}/{max_seed_artists} seed artists")
                
            except Exception as artist_error:
                log_message(f"Could not process artist {artist_name}: {artist_error}", 'yellow')
                continue
        
        # Combine loved tracks with similar tracks
        recommended_tracks.extend(similar_tracks)
        
        if not recommended_tracks:
            log_message("No recommendations found. Falling back to random loved tracks.", 'yellow')
            return get_random_tracks_from_lastfm(network, num_tracks, 50)
        
        # If we don't have enough tracks, fill with more loved tracks
        if len(recommended_tracks) < num_tracks:
            remaining_needed = num_tracks - len(recommended_tracks)
            log_message(f"Need {remaining_needed} more tracks to reach {num_tracks}. Adding more loved tracks...", 'yellow')
            
            # Get more loved tracks to fill the gap
            additional_loved = []
            for item in loved_tracks:
                if len(additional_loved) >= remaining_needed:
                    break
                track = item.track
                # Don't add tracks we already have
                track_already_added = False
                for existing_track in recommended_tracks:
                    if (existing_track.title.lower() == track.title.lower() and 
                        existing_track.artist.name.lower() == track.artist.name.lower()):
                        track_already_added = True
                        break
                if not track_already_added:
                    additional_loved.append(track)
            
            recommended_tracks.extend(additional_loved)
            log_message(f"Added {len(additional_loved)} additional loved tracks", 'green')
        
        # Shuffle and trim to requested number
        random.shuffle(recommended_tracks)
        recommended_tracks = recommended_tracks[:num_tracks]
        
        # Apply randomity factor
        if randomity_factor > 0:
            log_message(f"Applying randomity factor of {randomity_factor}%...", 'yellow')
            recommended_tracks = apply_randomity(recommended_tracks, randomity_factor)
        
        log_message(f"Generated {len(recommended_tracks)} Last.fm-based recommendations", 'green')
        return recommended_tracks
        
    except Exception as e:
        import traceback
        log_message(f"Error getting Last.fm recommendations: {str(e)}", 'red')
        log_message(f"Traceback: {traceback.format_exc()}", 'red')
        return None


def get_recent_listening_context(network):
    """Analyze recent Last.fm listening patterns to determine current music preferences."""
    try:
        user = network.get_user(LASTFM_USERNAME)

        # Get recent tracks (last 500 plays to ensure we get enough recent data)
        log_message("Fetching recent tracks from Last.fm...", 'yellow')
        recent_tracks = user.get_recent_tracks(limit=500)

        # Load playlist history to EXCLUDE tracks we generated (prevent feedback loop!)
        playlist_history = load_playlist_history()
        recent_playlist_tracks = set(playlist_history.get("recent_tracks", []))
        recent_playlist_artists = set(playlist_history.get("recent_artists", []))

        recent_artists = []
        recent_genres = []
        artist_counts = Counter()

        # Filter to last 7 days
        import time
        from datetime import datetime, timedelta
        seven_days_ago = datetime.now() - timedelta(days=7)
        seven_days_ago_timestamp = int(seven_days_ago.timestamp())

        tracks_processed = 0
        tracks_in_timeframe = 0
        tracks_skipped_from_playlist = 0

        log_message("Processing recent tracks and filtering to last 7 days...", 'yellow')
        
        for track_item in recent_tracks:
            tracks_processed += 1
            track = track_item.track

            # Check if track has timestamp and is within last 7 days
            try:
                # Get the timestamp of when the track was played
                timestamp = getattr(track_item, 'timestamp', None)
                if timestamp:
                    track_time = int(timestamp)
                    if track_time < seven_days_ago_timestamp:
                        # Skip tracks older than 7 days
                        continue
                tracks_in_timeframe += 1
            except:
                # If we can't get timestamp, include it (better to include than exclude)
                tracks_in_timeframe += 1

            # PREVENT FEEDBACK LOOP: Skip most playlist tracks, but keep ~10% as "nice surprises"
            track_key = f"{track.title.lower()}|{track.artist.name.lower()}"
            artist_key = track.artist.name.lower()

            if track_key in recent_playlist_tracks or artist_key in recent_playlist_artists:
                # Keep 10% of playlist tracks as "surprises" (your actual favorites)
                if random.random() > 0.10:  # Skip 90% of playlist tracks
                    tracks_skipped_from_playlist += 1
                    continue

            artist_name = track.artist.name
            recent_artists.append(artist_name)
            artist_counts[artist_name] += 1
            
            # Try to get genre/tags for the artist (but limit to save API calls)
            if artist_name not in [a for a, c in artist_counts.most_common(20)]:
                continue
                
            try:
                artist = network.get_artist(artist_name)
                tags = artist.get_top_tags(limit=3)
                for tag in tags:
                    recent_genres.append(tag.item.name.lower())
            except:
                continue
        
        log_message(f"Processed {tracks_processed} recent tracks, {tracks_in_timeframe} from last 7 days, {tracks_skipped_from_playlist} skipped (from generated playlist)", 'green')
        
        # Get top recent artists and genres
        top_recent_artists = [artist for artist, count in artist_counts.most_common(15)]
        top_recent_genres = [genre for genre, count in Counter(recent_genres).most_common(8)]
        
        # Debug: Show detailed counts
        top_artist_counts = artist_counts.most_common(10)
        log_message(f"Top recent artists with counts: {', '.join([f'{artist}({count})' for artist, count in top_artist_counts])}", 'yellow')
        log_message(f"Recent listening context: {len(top_recent_artists)} artists, {len(top_recent_genres)} genres", 'green')
        log_message(f"Top recent artists: {', '.join(top_recent_artists[:8])}", 'yellow')
        log_message(f"Top recent genres: {', '.join(top_recent_genres)}", 'yellow')
        
        return {
            'recent_artists': top_recent_artists,
            'recent_genres': top_recent_genres,
            'artist_counts': dict(artist_counts)
        }
        
    except Exception as e:
        log_message(f"Error analyzing recent listening context: {e}", 'yellow')
        return {'recent_artists': [], 'recent_genres': [], 'artist_counts': {}}


def get_clustered_loved_tracks(network, recent_context):
    """Cluster loved tracks by genre/mood/era for coherent selection."""
    try:
        user = network.get_user(LASTFM_USERNAME)
        loved_tracks = user.get_loved_tracks(limit=None)

        # Organize tracks by artist and add metadata
        clustered_tracks = {
            'recent_favorites': [],  # Artists from recent listening (limit to top played)
            'genre_clusters': defaultdict(list),  # Tracks by genre
            'discovery_candidates': [],  # Less played artists for discovery
            'classics': []  # High playcount tracks
        }

        track_count = 0
        processed_artists = set()

        log_message("Clustering loved tracks by genre and recency...", 'yellow')

        for track_item in loved_tracks:
            track = track_item.track
            track_count += 1

            # Progress updates
            if track_count % 1000 == 0:
                log_message(f"Processed {track_count} tracks for clustering...", 'yellow')

            artist_name = track.artist.name
            track_data = {
                'title': track.title,
                'artist': artist_name,
                'playcount': getattr(track, 'playcount', 0) or 0
            }

            # Skip if we already processed this artist (one track per artist for coherence)
            if artist_name.lower() in processed_artists:
                continue

            processed_artists.add(artist_name.lower())

            # Categorize based on recent listening patterns
            # Only include in "recent favorites" if artist has multiple plays (not just 1-2)
            artist_play_count = recent_context['artist_counts'].get(artist_name, 0)
            if artist_name in recent_context['recent_artists'] and artist_play_count >= 3:
                # Only add to recent favorites if you actually played this artist multiple times
                clustered_tracks['recent_favorites'].append(track_data)
            elif track_data['playcount'] > 100:  # High playcount = classics
                clustered_tracks['classics'].append(track_data)
            else:
                clustered_tracks['discovery_candidates'].append(track_data)
            
            # Try to get genre information
            try:
                artist = network.get_artist(artist_name)
                tags = artist.get_top_tags(limit=2)
                for tag in tags:
                    genre = tag.item.name.lower()
                    if genre in recent_context['recent_genres'] or any(g in genre for g in recent_context['recent_genres']):
                        clustered_tracks['genre_clusters'][genre].append(track_data)
                        break
            except:
                continue
        
        # Log cluster sizes
        log_message(f"Clustering complete - Recent favorites: {len(clustered_tracks['recent_favorites'])}, "
                   f"Classics: {len(clustered_tracks['classics'])}, "
                   f"Discovery: {len(clustered_tracks['discovery_candidates'])}", 'green')
        
        return clustered_tracks
        
    except Exception as e:
        log_message(f"Error clustering loved tracks: {e}", 'red')
        return {'recent_favorites': [], 'genre_clusters': defaultdict(list), 'discovery_candidates': [], 'classics': []}


class CoherentTrack:
    def __init__(self, title, artist_name):
        self.title = title
        self.artist = type('Artist', (), {'name': artist_name})()


def create_coherent_mix(sp, network, clustered_tracks, recent_context, num_tracks, playlist_history):
    """Create a coherent mix that balances familiar and new while maintaining genre/mood consistency."""
    try:
        coherent_tracks = []
        used_artists = set()
        
        # Load banned items
        banned_items = load_banned_items()
        banned_count = len(banned_items['songs']) + len(banned_items['artists']) + len(banned_items['albums']) + len(banned_items['genres'])
        if banned_count > 0:
            log_message(f"Loaded {len(banned_items['songs'])} banned songs, {len(banned_items['artists'])} banned artists, {len(banned_items['albums'])} banned albums, {len(banned_items['genres'])} banned genres", 'yellow')
        
        # Strategy: Build coherent "sessions" rather than random mixing
        
        # 1. Start with recent favorites (40% - what you've been listening to lately)
        recent_count = int(num_tracks * 0.4)
        log_message(f"Adding {recent_count} tracks from recent favorites...", 'yellow')
        
        recent_tracks = clustered_tracks['recent_favorites']
        for track_data in recent_tracks:
            if len(coherent_tracks) >= recent_count:
                break
            artist_name = track_data['artist'].lower()
            if (artist_name not in used_artists and 
                not is_recently_used(track_data['title'], track_data['artist'], playlist_history) and
                not is_banned_item(track_data['title'], track_data['artist'], None, banned_items)):
                if is_track_suitable(track_data):
                    coherent_tracks.append(CoherentTrack(track_data['title'], track_data['artist']))
                    used_artists.add(artist_name)
        
        # 2. Add genre-cohesive tracks (30% - maintain mood consistency)
        genre_count = int(num_tracks * 0.3)
        log_message(f"Adding {genre_count} genre-cohesive tracks...", 'yellow')
        
        # Focus on genres from recent listening
        for genre in recent_context['recent_genres']:
            if len(coherent_tracks) >= recent_count + genre_count:
                break
            
            genre_tracks = clustered_tracks['genre_clusters'].get(genre, [])
            for track_data in genre_tracks:
                if len(coherent_tracks) >= recent_count + genre_count:
                    break
                    
                artist_name = track_data['artist'].lower()
                if (artist_name not in used_artists and 
                    not is_recently_used(track_data['title'], track_data['artist'], playlist_history) and
                    not is_banned_item(track_data['title'], track_data['artist'], None, banned_items)):
                    if is_track_suitable(track_data):
                        coherent_tracks.append(CoherentTrack(track_data['title'], track_data['artist']))
                        used_artists.add(artist_name)
        
        # 3. Add discovery tracks from similar artists (20% - new but coherent)
        discovery_count = int(num_tracks * 0.2)
        log_message(f"Adding {discovery_count} discovery tracks from similar artists...", 'yellow')
        
        # Get similar artists based on recent favorites
        similar_tracks = get_coherent_similar_tracks(sp, network, recent_context['recent_artists'][:5], 
                                                    used_artists, discovery_count)
        coherent_tracks.extend(similar_tracks)
        
        # 4. Fill remaining with classics (10% - timeless favorites)
        remaining_count = num_tracks - len(coherent_tracks)
        if remaining_count > 0:
            log_message(f"Filling {remaining_count} remaining slots with classics...", 'yellow')
            
            classics = clustered_tracks['classics']
            random.shuffle(classics)
            
            for track_data in classics:
                if len(coherent_tracks) >= num_tracks:
                    break
                    
                artist_name = track_data['artist'].lower()
                if (artist_name not in used_artists and 
                    not is_recently_used(track_data['title'], track_data['artist'], playlist_history) and
                    not is_banned_item(track_data['title'], track_data['artist'], None, banned_items)):
                    if is_track_suitable(track_data):
                        coherent_tracks.append(CoherentTrack(track_data['title'], track_data['artist']))
                        used_artists.add(artist_name)
        
        # GUARANTEE 100 TRACKS: If we don't have enough, expand search from discovery candidates
        if len(coherent_tracks) < num_tracks:
            remaining_needed = num_tracks - len(coherent_tracks)
            log_message(f"Need {remaining_needed} more tracks to reach {num_tracks}. Expanding search from discovery candidates...", 'yellow')
            
            discovery_candidates = clustered_tracks['discovery_candidates']
            for track_data in discovery_candidates:
                if len(coherent_tracks) >= num_tracks:
                    break
                    
                artist_name = track_data['artist'].lower()
                if (artist_name not in used_artists and 
                    not is_banned_item(track_data['title'], track_data['artist'], None, banned_items)):
                    if is_track_suitable(track_data):
                        coherent_tracks.append(CoherentTrack(track_data['title'], track_data['artist']))
                        used_artists.add(artist_name)
                        
        # FINAL GUARANTEE: If still not enough, get more loved tracks without recent filtering
        if len(coherent_tracks) < num_tracks:
            remaining_needed = num_tracks - len(coherent_tracks)
            log_message(f"Still need {remaining_needed} more tracks. Filling from any available loved tracks...", 'yellow')
            
            all_discovery = clustered_tracks['discovery_candidates'] + clustered_tracks['classics']
            for track_data in all_discovery:
                if len(coherent_tracks) >= num_tracks:
                    break
                    
                artist_name = track_data['artist'].lower()
                if (artist_name not in used_artists and 
                    not is_banned_item(track_data['title'], track_data['artist'], None, banned_items)):
                    if is_track_suitable(track_data):
                        coherent_tracks.append(CoherentTrack(track_data['title'], track_data['artist']))
                        used_artists.add(artist_name)
        
        log_message(f"Created coherent mix with {len(coherent_tracks)} tracks from {len(used_artists)} unique artists", 'green')
        return coherent_tracks
        
    except Exception as e:
        log_message(f"Error creating coherent mix: {e}", 'red')
        return []


def get_coherent_similar_tracks(sp, network, seed_artists, used_artists, target_count):
    """Get tracks from similar artists that maintain genre/mood coherence."""
    try:
        similar_tracks = []
        
        for seed_artist in seed_artists:
            if len(similar_tracks) >= target_count:
                break
                
            try:
                artist = network.get_artist(seed_artist)
                similar_artists = artist.get_similar(limit=3)
                
                for similar_artist_item in similar_artists:
                    if len(similar_tracks) >= target_count:
                        break
                        
                    similar_artist = similar_artist_item.item
                    artist_name_lower = similar_artist.name.lower()
                    
                    if artist_name_lower not in used_artists:
                        top_tracks = similar_artist.get_top_tracks(limit=1)
                        
                        for track_item in top_tracks:
                            track = track_item.item
                            track_data = {
                                'title': track.title,
                                'artist': track.artist.name
                            }
                            
                            if is_track_suitable(track_data):
                                # Verify track exists on Spotify
                                try:
                                    search_results = sp.search(
                                        q=f"track:{track.title} artist:{track.artist.name}",
                                        type="track",
                                        limit=1
                                    )
                                    if search_results["tracks"]["items"]:
                                        class SimilarTrack:
                                            def __init__(self, title, artist_name):
                                                self.title = title
                                                self.artist = type('Artist', (), {'name': artist_name})()
                                        
                                        similar_tracks.append(SimilarTrack(track.title, track.artist.name))
                                        used_artists.add(artist_name_lower)
                                        break
                                except:
                                    continue
                            break
                            
            except Exception:
                continue
        
        return similar_tracks
        
    except Exception as e:
        log_message(f"Error getting coherent similar tracks: {e}", 'yellow')
        return []


def is_track_suitable(track_data):
    """Smart filtering to ensure track quality and coherence."""
    title = track_data['title'].lower()
    artist = track_data['artist'].lower()
    
    # Filter out problematic content
    unsuitable_keywords = [
        'live', 'live at', 'live from', 'live in', 'live on', 
        'concert', 'acoustic version', 'demo', 'rehearsal',
        'interview', 'spoken word', 'various artists', 'va'
    ]
    
    # Check title and artist
    if any(keyword in title for keyword in unsuitable_keywords):
        return False
    
    if any(keyword in artist for keyword in unsuitable_keywords):
        return False
    
    # Filter out very short or very long titles (likely incomplete or messy data)
    if len(track_data['title']) < 2 or len(track_data['title']) > 100:
        return False
    
    return True


def get_coherent_my_station_recommendations(sp, network, history_analysis, num_tracks=100, randomity_factor=50):
    """
    Creates a coherent My Station experience that reduces messiness by:
    1. Analyzing recent Last.fm listening patterns for context
    2. Clustering tracks by genre/mood/era for coherence
    3. Smart filtering to avoid live tracks, duplicates, and maintain consistency
    4. Temporal weighting to prioritize recently played genres/artists
    """
    try:
        log_message("Creating coherent My Station recommendations...", 'green')
        
        # Load playlist history to avoid repetition
        playlist_history = load_playlist_history()
        log_message(f"Loaded history: {len(playlist_history.get('recent_tracks', []))} recent tracks, {len(playlist_history.get('recent_artists', []))} recent artists", 'yellow')
        
        # Get recent listening context from Last.fm
        log_message("Analyzing recent Last.fm listening patterns...", 'yellow')
        recent_context = get_recent_listening_context(network)
        
        # Get and cluster loved tracks
        log_message("Fetching and clustering your loved tracks collection...", 'yellow')
        clustered_tracks = get_clustered_loved_tracks(network, recent_context)
        
        # Create coherent mix
        log_message("Creating coherent mix based on recent listening patterns...", 'yellow')
        coherent_tracks = create_coherent_mix(sp, network, clustered_tracks, recent_context, num_tracks, playlist_history)
        
        # Apply randomity factor
        if randomity_factor > 0:
            log_message(f"Applying randomity factor of {randomity_factor}%...", 'yellow')
            coherent_tracks = apply_randomity(coherent_tracks, randomity_factor)
        
        log_message(f"Generated {len(coherent_tracks)} coherent My Station tracks", 'green')
        return coherent_tracks
        
    except Exception as e:
        log_message(f"Error getting coherent recommendations: {e}", 'red')
        log_message("Falling back to standard AI recommendations...", 'yellow')
        return get_ai_hybrid_recommendations(sp, network, history_analysis, num_tracks, randomity_factor)


def get_ai_artist_recommendations(network, loved_tracks_list, num_artists=10):
    """Get AI-powered artist recommendations using GPT-5-mini or Gemini."""
    try:
        log_message("Getting AI-powered artist recommendations...", 'green')

        # Sample tracks for AI analysis
        sample_size = min(100, len(loved_tracks_list))
        sample_tracks = random.sample(loved_tracks_list, sample_size)
        sample_track_names = [f"{item.track.title} by {item.track.artist.name}" for item in sample_tracks]

        # Get unique artists
        artists_set = set()
        for item in loved_tracks_list:
            artists_set.add(item.track.artist.name)
        artists_list = list(artists_set)[:50]  # Top 50 for prompt

        prompt = f"""You are an AI music curator. Analyze this user's music taste and recommend {num_artists} NEW artists they would love.

User's Music Profile:
- Sample tracks: {', '.join(sample_track_names[:30])}
- Favorite artists: {', '.join(artists_list[:25])}

Return ONLY a JSON array of artist recommendations in this exact format:
[
  {{"type": "artist", "name": "Artist Name", "reason": "Brief reason"}},
  ...
]

Focus on artists similar to their taste but NOT in their current collection."""

        ai_response = None

        # Try OpenAI first
        if AI_PROVIDER == "openai" and OPENAI_API_KEY and openai:
            try:
                openai.api_key = OPENAI_API_KEY
                log_message("Using GPT-5-mini for artist recommendations...")
                response = openai.chat.completions.create(
                    model="gpt-5-mini",
                    messages=[{"role": "user", "content": prompt}]
                    # Note: GPT-5 models don't support temperature/top_p/max_tokens parameters
                    # They use default settings only
                )
                ai_response = response.choices[0].message.content
                log_message("Received AI artist recommendations from GPT-5-mini", 'green')
            except Exception as e:
                log_message(f"OpenAI error: {e}", 'yellow')

        # Fallback to Gemini
        if not ai_response and GEMINI_API_KEY and genai:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                log_message("Using Gemini for artist recommendations...")
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(prompt)
                ai_response = response.text
                log_message("Received AI artist recommendations from Gemini", 'green')
            except Exception as e:
                log_message(f"Gemini error: {e}", 'yellow')

        if not ai_response:
            log_message("No AI available, skipping AI recommendations", 'yellow')
            return []

        # Parse JSON response
        import json
        import re
        json_match = re.search(r'\[.*?\]', ai_response, re.DOTALL)
        if json_match:
            try:
                recommendations_data = json.loads(json_match.group())
                ai_artists = []
                for rec in recommendations_data:
                    if isinstance(rec, dict) and rec.get('type') == 'artist' and 'name' in rec:
                        ai_artists.append(rec['name'])
                        log_message(f"AI recommends: {rec['name']} - {rec.get('reason', '')[:50]}...", 'yellow')
                return ai_artists
            except json.JSONDecodeError as e:
                log_message(f"Failed to parse AI response: {e}", 'yellow')
                return []

        return []

    except Exception as e:
        log_message(f"Error getting AI recommendations: {e}", 'yellow')
        return []


def get_audio_features_similarity(sp, seed_features, candidate_features):
    """Calculate similarity score between two tracks based on audio features."""
    try:

        if not seed_features or not candidate_features:
            return 0.0

        # Key audio features for sonic similarity
        feature_weights = {
            'energy': 2.0,          # High weight - crucial for vibe
            'danceability': 1.5,    # Important for rhythmic feel
            'valence': 1.5,         # Mood/positivity
            'tempo': 1.0,           # Beat speed
            'acousticness': 1.2,    # Electric vs acoustic
            'instrumentalness': 1.0, # Vocal vs instrumental
            'speechiness': 0.8,     # Spoken word content
            'liveness': 0.5         # Lower weight - less important
        }

        # Normalize tempo (typically 60-200 BPM) to 0-1 scale
        seed_tempo_norm = (seed_features['tempo'] - 60) / 140
        cand_tempo_norm = (candidate_features['tempo'] - 60) / 140

        # Calculate weighted similarity
        total_weight = sum(feature_weights.values())
        similarity_score = 0.0

        for feature, weight in feature_weights.items():
            if feature == 'tempo':
                # Use normalized tempo
                diff = abs(seed_tempo_norm - cand_tempo_norm)
            else:
                diff = abs(seed_features[feature] - candidate_features[feature])

            # Convert difference to similarity (1 = identical, 0 = completely different)
            feature_similarity = 1.0 - diff
            similarity_score += feature_similarity * weight

        # Normalize to 0-100 scale
        final_score = (similarity_score / total_weight) * 100
        return final_score

    except Exception as e:
        log_message(f"Error calculating audio similarity: {e}", 'yellow')
        return 0.0


def get_recent_seed_track(sp, network):
    """Get one recent loved track to use as seed for sonic similarity."""
    try:
        log_message("Finding recent loved track to use as seed...", 'yellow')
        user = network.get_user(LASTFM_USERNAME)

        # Get recent listening history from last 7 days
        from datetime import datetime, timedelta
        seven_days_ago = datetime.now() - timedelta(days=7)
        seven_days_ago_timestamp = int(seven_days_ago.timestamp())

        recent_tracks = user.get_recent_tracks(limit=500)

        # Build dict of recently listened artists with play counts (from last 7 days)
        recent_artists = {}  # artist_name -> {'last_played': timestamp, 'play_count': int}

        log_message("Analyzing recent listening history (last 7 days)...", 'yellow')
        for track_item in recent_tracks:
            try:
                timestamp = getattr(track_item, 'timestamp', None)
                if timestamp:
                    track_time = int(timestamp)
                    if track_time < seven_days_ago_timestamp:
                        continue

                    artist_name = track_item.track.artist.name

                    # Track play count and most recent play for each artist
                    if artist_name not in recent_artists:
                        recent_artists[artist_name] = {'last_played': track_time, 'play_count': 1}
                    else:
                        recent_artists[artist_name]['play_count'] += 1
                        if track_time > recent_artists[artist_name]['last_played']:
                            recent_artists[artist_name]['last_played'] = track_time
            except:
                continue

        # Filter to artists with 5+ plays
        frequent_artists = {name: data for name, data in recent_artists.items() if data['play_count'] >= 5}

        log_message(f"Found {len(recent_artists)} artists in recent listening, {len(frequent_artists)} with 5+ plays", 'yellow')

        # Now get loved tracks and filter to those by frequently played artists
        log_message("Finding loved tracks from frequently played artists (5+ plays)...", 'yellow')
        loved_tracks = list(user.get_loved_tracks(limit=None))

        # Load history to avoid using generated tracks as seed
        playlist_history = load_playlist_history()
        recent_playlist_tracks = set(playlist_history.get("recent_tracks", []))

        candidates = []

        for item in loved_tracks:
            track = item.track
            artist_name = track.artist.name

            # Only include if this artist has 5+ plays in last 7 days
            if artist_name not in frequent_artists:
                continue

            # Skip generated playlist tracks
            track_key = f"{track.title.lower()}|{artist_name.lower()}"
            if track_key in recent_playlist_tracks:
                continue

            # Try to find on Spotify
            try:
                search_results = sp.search(
                    q=f"track:{track.title} artist:{artist_name}",
                    type="track",
                    limit=1
                )
                if search_results["tracks"]["items"]:
                    spotify_track = search_results["tracks"]["items"][0]
                    candidates.append({
                        'title': track.title,
                        'artist': artist_name,
                        'uri': spotify_track['uri'],
                        'spotify_id': spotify_track['id'],
                        'last_played': frequent_artists[artist_name]['last_played'],
                        'play_count': frequent_artists[artist_name]['play_count']
                    })

                    if len(candidates) >= 50:  # Get up to 50 candidates
                        break
            except:
                continue

        log_message(f"Found {len(candidates)} loved tracks from frequently played artists", 'green')

        if not candidates:
            log_message("No recent loved tracks found, using any loved tracks...", 'yellow')
            # Fallback to any loved tracks
            for item in loved_tracks[:100]:
                track = item.track
                try:
                    search_results = sp.search(
                        q=f"track:{track.title} artist:{track.artist.name}",
                        type="track",
                        limit=1
                    )
                    if search_results["tracks"]["items"]:
                        spotify_track = search_results["tracks"]["items"][0]
                        candidates.append({
                            'title': track.title,
                            'artist': track.artist.name,
                            'uri': spotify_track['uri'],
                            'spotify_id': spotify_track['id'],
                            'last_played': 0
                        })

                        if len(candidates) >= 20:
                            break
                except:
                    continue

        if candidates:
            # Weight selection toward more recently played
            # Sort by last_played and pick from top half randomly
            candidates.sort(key=lambda x: x.get('last_played', 0), reverse=True)
            top_half = candidates[:max(len(candidates)//2, 1)]

            seed = random.choice(top_half)
            log_message(f"Selected seed: '{seed['title']}' by {seed['artist']} (from loved tracks)", 'green')
            return seed

        return None

    except Exception as e:
        log_message(f"Error getting recent seed track: {e}", 'red')
        return None


def get_sonic_station(sp, network, num_tracks=100):
    """
    Create a sonically cohesive playlist using Last.fm similar artists.
    Note: Spotify's Audio Features & Recommendations APIs were deprecated Nov 2024.

    Strategy:
    1. Pick one recent favorite track as seed
    2. Get up to 30 similar artists from Last.fm
    3. Build playlist primarily from similar artists' top tracks
    4. Fill remaining slots with tracks from your loved collection by similar artists
    """
    try:
        log_message("Creating sonic similarity station using Last.fm similar artists...", 'green')

        # Get seed track from recent listening
        seed_track = get_recent_seed_track(sp, network)
        if not seed_track:
            log_message("Could not find seed track, falling back to Apple Music station", 'yellow')
            return get_apple_music_discovery_station(sp, network, num_tracks)

        seed_artist_name = seed_track['artist']
        log_message(f"Seed track: '{seed_track['title']}' by {seed_artist_name}", 'green')

        # Get similar artists from Last.fm
        log_message("Finding similar artists from Last.fm...", 'yellow')
        similar_artists = []

        try:
            seed_artist = network.get_artist(seed_artist_name)
            similar_artists_items = seed_artist.get_similar(limit=30)
            similar_artists = [sa.item for sa in similar_artists_items]
            log_message(f"Found {len(similar_artists)} similar artists", 'green')

            # Log top 5 for visibility
            for i, artist in enumerate(similar_artists[:5]):
                log_message(f"  {i+1}. {artist.name}", 'yellow')

        except Exception as e:
            log_message(f"Error getting similar artists: {e}", 'red')
            log_message("Falling back to Apple Music station", 'yellow')
            return get_apple_music_discovery_station(sp, network, num_tracks)

        if not similar_artists:
            log_message("No similar artists found, falling back", 'yellow')
            return get_apple_music_discovery_station(sp, network, num_tracks)

        # Load history and banned items
        playlist_history = load_playlist_history()
        banned_items = load_banned_items()

        # Build playlist from similar artists
        final_tracks = []
        used_artists = set()
        used_track_keys = set()

        log_message(f"Building playlist from similar artists' top tracks...", 'yellow')

        # Get tracks from similar artists
        for similar_artist in similar_artists:
            if len(final_tracks) >= num_tracks:
                break

            artist_name = similar_artist.name
            artist_lower = artist_name.lower()

            # Skip if already used
            if artist_lower in used_artists:
                continue

            # Filter out obscure/low-quality artists
            try:
                # Get Last.fm listener count
                listeners = similar_artist.get_listener_count()
                if listeners:
                    listener_count = int(listeners)
                    # Skip artists with very low listener counts (< 10,000 listeners)
                    if listener_count < 10000:
                        log_message(f"Skipping obscure artist: {artist_name} ({listener_count:,} listeners)", 'yellow')
                        continue
            except:
                # If we can't get listener count, proceed anyway (don't be too strict)
                pass

            try:
                # Get top tracks for this artist
                top_tracks = similar_artist.get_top_tracks(limit=5)

                for track_item in top_tracks:
                    if len(final_tracks) >= num_tracks:
                        break

                    track = track_item.item
                    track_title = track.title
                    track_key = f"{track_title.lower()}|{artist_lower}"

                    # Skip if already used, recently played, or banned
                    if (track_key in used_track_keys or
                        is_recently_used(track_title, artist_name, playlist_history) or
                        is_banned_item(track_title, artist_name, None, banned_items)):
                        continue

                    if not is_track_suitable({'title': track_title, 'artist': artist_name}):
                        continue

                    # Additional quality filters for track titles
                    title_lower = track_title.lower()
                    # Skip Christmas songs, AI music indicators, etc.
                    skip_keywords = ['christmas', 'xmas', 'ai generated', 'ai music',
                                    'cover version', 'tribute', 'karaoke']
                    if any(keyword in title_lower for keyword in skip_keywords):
                        continue

                    # Search on Spotify
                    try:
                        search_results = sp.search(
                            q=f"track:{track_title} artist:{artist_name}",
                            type="track",
                            limit=1
                        )

                        if search_results["tracks"]["items"]:
                            spotify_track = search_results["tracks"]["items"][0]

                            # Check Spotify popularity (0-100 scale, skip < 15)
                            popularity = spotify_track.get('popularity', 0)
                            if popularity < 15:
                                log_message(f"Skipping unpopular track: {track_title} by {artist_name} (popularity: {popularity})", 'yellow')
                                continue

                            # Check for banned genres
                            if banned_items['genres']:
                                track_genres = get_track_genres(sp, spotify_track['uri'])
                                if is_banned_item(track_title, artist_name, None, banned_items, track_genres):
                                    continue

                            class SonicTrack:
                                def __init__(self, title, artist_name):
                                    self.title = title
                                    self.artist = type('Artist', (), {'name': artist_name})()

                            final_tracks.append(SonicTrack(track_title, artist_name))
                            used_artists.add(artist_lower)
                            used_track_keys.add(track_key)

                            # Only one track per artist for variety
                            break

                    except Exception as e:
                        continue

            except Exception as e:
                log_message(f"Error getting tracks for {artist_name}: {e}", 'yellow')
                continue

            # Progress update
            if len(final_tracks) % 10 == 0 and len(final_tracks) > 0:
                log_message(f"Progress: {len(final_tracks)}/{num_tracks} tracks...", 'yellow')

        log_message(f"Got {len(final_tracks)} tracks from similar artists", 'green')

        # If we don't have enough, fill from your loved tracks by similar artists
        if len(final_tracks) < num_tracks:
            remaining_needed = num_tracks - len(final_tracks)
            log_message(f"Need {remaining_needed} more tracks, checking your loved collection...", 'yellow')

            user = network.get_user(LASTFM_USERNAME)
            loved_tracks_list = list(user.get_loved_tracks(limit=None))

            # Create set of similar artist names for quick lookup
            similar_artist_names = set([sa.name.lower() for sa in similar_artists])

            for item in loved_tracks_list:
                if len(final_tracks) >= num_tracks:
                    break

                track = item.track
                artist_name = track.artist.name
                artist_lower = artist_name.lower()
                track_key = f"{track.title.lower()}|{artist_lower}"

                # Only include if artist is in similar artists list
                if artist_lower not in similar_artist_names:
                    continue

                # Skip if already used (including artist already used)
                if (track_key in used_track_keys or
                    artist_lower in used_artists or
                    is_recently_used(track.title, artist_name, playlist_history) or
                    is_banned_item(track.title, artist_name, None, banned_items)):
                    continue

                if not is_track_suitable({'title': track.title, 'artist': artist_name}):
                    continue

                try:
                    search_results = sp.search(
                        q=f"track:{track.title} artist:{artist_name}",
                        type="track",
                        limit=1
                    )

                    if search_results["tracks"]["items"]:
                        spotify_track = search_results["tracks"]["items"][0]

                        # Check for banned genres
                        if banned_items['genres']:
                            track_genres = get_track_genres(sp, spotify_track['uri'])
                            if is_banned_item(track.title, artist_name, None, banned_items, track_genres):
                                continue

                        class SonicTrack:
                            def __init__(self, title, artist_name):
                                self.title = title
                                self.artist = type('Artist', (), {'name': artist_name})()

                        final_tracks.append(SonicTrack(track.title, artist_name))
                        used_artists.add(artist_lower)
                        used_track_keys.add(track_key)

                except:
                    continue

            log_message(f"Added {len(final_tracks) - (num_tracks - remaining_needed)} more from loved collection", 'green')

        # Shuffle for variety
        random.shuffle(final_tracks)

        log_message(f"Created sonic station with {len(final_tracks)} tracks from {len(used_artists)} similar artists", 'green')

        # Ensure we have enough tracks
        if len(final_tracks) < num_tracks * 0.5:  # Need at least 50%
            log_message(f"Only found {len(final_tracks)} tracks ({len(final_tracks)/num_tracks*100:.0f}%), falling back to Apple Music station", 'yellow')
            return get_apple_music_discovery_station(sp, network, num_tracks)

        return final_tracks[:num_tracks]

    except Exception as e:
        import traceback
        log_message(f"Error creating sonic station: {e}", 'red')
        log_message(f"Traceback: {traceback.format_exc()}", 'red')
        log_message("Falling back to Apple Music station", 'yellow')
        return get_apple_music_discovery_station(sp, network, num_tracks)


def get_apple_music_discovery_station(sp, network, num_tracks=100):
    """
    Apple Music My Station with balanced familiarity and discovery.

    Mix:
    - 50% Your Favorites (loved tracks weighted by playcount)
    - 20% AI Discovery (GPT-5-mini/Gemini recommends NEW artists)
    - 30% Last.fm Discovery (similar artists from Last.fm)

    Note: Fetches 2x tracks to account for duplicate artist filtering during playlist update.
    """
    try:
        log_message("Creating Apple Music-style discovery station (50% favorites + 20% AI + 30% Last.fm)...", 'green')

        playlist_history = load_playlist_history()
        banned_items = load_banned_items()
        user = network.get_user(LASTFM_USERNAME)

        all_tracks = []
        used_track_keys = set()
        artist_track_count = Counter()  # Track how many songs per artist

        def add_track(title, artist, source):
            """Helper to add track if not duplicate. Allows up to 2 tracks per artist for variety."""
            track_key = f"{title.lower()}|{artist.lower()}"
            artist_key = artist.lower()

            # Allow up to 2 tracks per artist during discovery (will be filtered to 1 during playlist update)
            if track_key not in used_track_keys and artist_track_count[artist_key] < 2:
                all_tracks.append({'title': title, 'artist': artist, 'source': source})
                used_track_keys.add(track_key)
                artist_track_count[artist_key] += 1
                return True
            return False

        # Fetch 2x tracks to account for duplicate filtering
        # Target: 100 final tracks, so fetch 200 during discovery
        discovery_multiplier = 2
        target_discovery_tracks = num_tracks * discovery_multiplier

        # 1. YOUR FAVORITES (50%) - Loved tracks weighted by playcount
        favorites_target = int(target_discovery_tracks * 0.50)
        log_message(f"Selecting {favorites_target} favorites (weighted by playcount)...")

        loved_tracks_list = list(user.get_loved_tracks(limit=None))

        # Weight by playcount - sort by playcount and take weighted random sample
        loved_with_playcount = []
        for item in loved_tracks_list:
            playcount = getattr(item.track, 'playcount', 0) or 1
            loved_with_playcount.append((item, playcount))

        # Sort by playcount descending and apply weighted selection
        loved_with_playcount.sort(key=lambda x: x[1], reverse=True)

        # Take 70% from top played, 30% from rest for variety
        top_played_count = int(len(loved_with_playcount) * 0.7)
        top_played = [x[0] for x in loved_with_playcount[:top_played_count]]
        rest = [x[0] for x in loved_with_playcount[top_played_count:]]

        random.shuffle(top_played)
        random.shuffle(rest)
        loved_tracks_list = top_played + rest

        for item in loved_tracks_list:
            if len([t for t in all_tracks if t['source'] == 'favorite']) >= favorites_target:
                break

            track = item.track
            if (not is_recently_used(track.title, track.artist.name, playlist_history) and
                not is_banned_item(track.title, track.artist.name, None, banned_items)):
                add_track(track.title, track.artist.name, 'favorite')

        log_message(f"Added {len([t for t in all_tracks if t['source'] == 'favorite'])} favorites")

        # 2. AI DISCOVERY (20%) - NEW artists from GPT-5-mini/Gemini
        ai_target = int(target_discovery_tracks * 0.20)
        log_message(f"Getting {ai_target} AI-recommended tracks (will be filtered to ~{int(num_tracks * 0.20)})...")

        # Get AI artist recommendations
        ai_artists = get_ai_artist_recommendations(network, loved_tracks_list, num_artists=15)

        if ai_artists:
            ai_added = 0
            for artist_name in ai_artists:
                if ai_added >= ai_target:
                    break

                try:
                    # Get top tracks from AI-recommended artist
                    artist = network.get_artist(artist_name)

                    # Quality filter: Check Last.fm listener count
                    try:
                        listeners = artist.get_listener_count()
                        if listeners and int(listeners) < 10000:
                            continue
                    except:
                        pass

                    top_tracks = artist.get_top_tracks(limit=5)

                    for track_item in top_tracks:
                        if ai_added >= ai_target:
                            break

                        track = track_item.item
                        track_title_lower = track.title.lower()

                        # Quality filter: Skip Christmas, AI music, covers, etc.
                        skip_keywords = ['christmas', 'xmas', 'ai generated', 'ai music',
                                        'cover version', 'tribute', 'karaoke']
                        if any(keyword in track_title_lower for keyword in skip_keywords):
                            continue

                        if not is_banned_item(track.title, track.artist.name, None, banned_items):
                            # Skip Spotify verification for speed - will verify during playlist update
                            if add_track(track.title, track.artist.name, 'ai_discovery'):
                                ai_added += 1
                                break  # Only one track per AI artist
                except:
                    continue

            log_message(f"Added {ai_added} AI-recommended tracks")
        else:
            log_message("No AI recommendations available, will fill with Last.fm", 'yellow')

        # 3. LAST.FM DISCOVERY (30%) - NEW tracks via similar artists
        lastfm_target = int(target_discovery_tracks * 0.30)
        log_message(f"Discovering {lastfm_target} NEW tracks via Last.fm similar artists (will be filtered to ~{int(num_tracks * 0.30)})...")

        # Use Last.fm similar artists for discovery (more conservative = closer to taste)
        lastfm_added = 0
        for item in random.sample(loved_tracks_list, min(10, len(loved_tracks_list))):
            if lastfm_added >= lastfm_target:
                break

            try:
                artist = network.get_artist(item.track.artist.name)
                similar = artist.get_similar(limit=10)  # Reduced from 20 to 10 for more conservative matching

                for sim_artist in similar:
                    if lastfm_added >= lastfm_target:
                        break

                    # Quality filter: Check Last.fm listener count
                    try:
                        listeners = sim_artist.item.get_listener_count()
                        if listeners and int(listeners) < 10000:
                            continue
                    except:
                        pass

                    top_tracks = sim_artist.item.get_top_tracks(limit=5)
                    for track_item in top_tracks:
                        if lastfm_added >= lastfm_target:
                            break

                        track = track_item.item
                        track_title_lower = track.title.lower()

                        # Quality filter: Skip Christmas, AI music, covers, etc.
                        skip_keywords = ['christmas', 'xmas', 'ai generated', 'ai music',
                                        'cover version', 'tribute', 'karaoke']
                        if any(keyword in track_title_lower for keyword in skip_keywords):
                            continue

                        if not is_banned_item(track.title, track.artist.name, None, banned_items):
                            # Skip Spotify verification for speed - will verify during playlist update
                            if add_track(track.title, track.artist.name, 'lastfm_discovery'):
                                lastfm_added += 1
                                break  # Only one track per similar artist
            except:
                continue

        log_message(f"Added {lastfm_added} discovery tracks from Last.fm similar artists")

        # 3-5. Fill remaining with more discovery
        remaining = target_discovery_tracks - len(all_tracks)
        log_message(f"Filling {remaining} remaining slots with Last.fm similar artist discovery...")

        # Use Last.fm similar artists for remaining slots (conservative matching)
        for item in random.sample(loved_tracks_list, min(8, len(loved_tracks_list))):
            if len(all_tracks) >= target_discovery_tracks:
                break

            try:
                artist = network.get_artist(item.track.artist.name)
                similar = artist.get_similar(limit=8)  # Reduced from 15 to 8 for closer matches

                for sim_artist in similar:
                    if len(all_tracks) >= target_discovery_tracks:
                        break

                    # Quality filter: Check Last.fm listener count
                    try:
                        listeners = sim_artist.item.get_listener_count()
                        if listeners and int(listeners) < 10000:
                            continue
                    except:
                        pass

                    top_tracks = sim_artist.item.get_top_tracks(limit=5)
                    for track_item in top_tracks:
                        if len(all_tracks) >= target_discovery_tracks:
                            break

                        track = track_item.item
                        track_title_lower = track.title.lower()

                        # Quality filter: Skip Christmas, AI music, covers, etc.
                        skip_keywords = ['christmas', 'xmas', 'ai generated', 'ai music',
                                        'cover version', 'tribute', 'karaoke']
                        if any(keyword in track_title_lower for keyword in skip_keywords):
                            continue

                        if not is_banned_item(track.title, track.artist.name, None, banned_items):
                            # Skip Spotify verification for speed - will verify during playlist update
                            if add_track(track.title, track.artist.name, 'discovery'):
                                break  # Only one track per similar artist
            except:
                continue

        log_message(f"Total tracks discovered: {len(all_tracks)} (target after filtering: ~{num_tracks})", 'green')

        # Convert to track objects
        class DiscoveryTrack:
            def __init__(self, title, artist_name):
                self.title = title
                self.artist = type('Artist', (), {'name': artist_name})()

        final_tracks = [DiscoveryTrack(t['title'], t['artist']) for t in all_tracks]

        # Shuffle for variety
        random.shuffle(final_tracks)

        return final_tracks

    except Exception as e:
        import traceback
        log_message(f"Error in Apple Music discovery: {e}", 'red')
        log_message(f"Traceback: {traceback.format_exc()}", 'red')
        return []


def get_ai_hybrid_recommendations(sp, network, history_analysis, num_tracks=100, randomity_factor=50):
    # Keep existing implementation as fallback
    try:
        log_message("Getting AI-powered recommendations...")

        # Load banned items for filtering
        banned_items = load_banned_items()
        log_message(f"Loaded {len(banned_items['songs'])} banned songs, {len(banned_items['artists'])} banned artists, {len(banned_items['albums'])} banned albums, {len(banned_items['genres'])} banned genres", 'yellow')
        
        log_message("Connecting to Last.fm API and fetching user profile...", 'yellow')
        user = network.get_user(LASTFM_USERNAME)
        
        log_message("Starting to fetch loved tracks from Last.fm (this may take 1-2 minutes for large collections)...", 'yellow')
        log_message("Last.fm API has rate limits, so please be patient...", 'yellow')
        
        loved_tracks = user.get_loved_tracks(limit=None)
        
        loved_tracks_data = []
        track_count = 0
        start_time = time.time()
        
        log_message("Beginning to process loved tracks data...", 'yellow')
        for item in loved_tracks:
            track = item.track
            track_count += 1
            loved_tracks_data.append({
                'title': track.title,
                'artist': track.artist.name,
                'playcount': getattr(track, 'playcount', 0) or 0
            })
            
            # More frequent progress updates
            if track_count % 500 == 0:
                elapsed = time.time() - start_time
                rate = track_count / elapsed
                log_message(f"Processed {track_count} loved tracks ({rate:.1f} tracks/sec, {elapsed:.1f}s elapsed)...", 'yellow')
            
            # Even more frequent for first 1000
            elif track_count <= 1000 and track_count % 100 == 0:
                elapsed = time.time() - start_time
                log_message(f"Processed {track_count} loved tracks ({elapsed:.1f}s elapsed)...", 'yellow')
        
        total_time = time.time() - start_time
        log_message(f"Analyzed {len(loved_tracks_data)} total loved tracks for AI recommendations in {total_time:.1f} seconds", 'green')
        
        log_message("Extracting unique artists from your collection...", 'yellow')
        artists_list = list(set([track['artist'] for track in loved_tracks_data]))
        random.shuffle(artists_list)
        log_message(f"Found {len(artists_list)} unique artists in your collection", 'green')
        
        log_message("Selecting representative sample of tracks for AI analysis...", 'yellow')
        # Get a more representative sample of loved tracks
        sample_tracks = random.sample(loved_tracks_data, min(100, len(loved_tracks_data)))
        sample_track_names = [f"{track['title']} by {track['artist']}" for track in sample_tracks]
        
        # Also get some direct loved tracks for inclusion
        direct_loved_sample = random.sample(loved_tracks_data, min(30, len(loved_tracks_data)))
        direct_loved_names = [f"{track['title']} by {track['artist']}" for track in direct_loved_sample]
        log_message(f"Selected {len(sample_tracks)} sample tracks and {len(direct_loved_sample)} loved tracks for analysis", 'green')
        
        prompt = f"""You are an AI music curator creating a personalized "My Station" playlist similar to Apple Music's feature.

User's Music Profile:
- Last.fm Username: {LASTFM_USERNAME}
- Total loved tracks: {len(loved_tracks_data)} (20+ years of music history!)
- Unique artists in collection: {len(artists_list)}
- Playlist update history: {history_analysis.get('total_playlist_updates', 0)} updates
- Sample of their music taste: {', '.join(sample_track_names[:20])}
- Top artists from their collection: {', '.join(artists_list[:25])}
- Some loved tracks to include: {', '.join(direct_loved_names[:15])}

Your task: Recommend artists and musical directions for creating the perfect personalized radio station. Your goal is to mimic Apple Music's My Station. "My Station" on Apple Music refers to a personalized radio station that plays music based on user's listening history and preferences, combining songs from user's library with similar tracks that the AI/algorithm suggests. Try to achieve that same effect with these song choices.

Instead of specific songs (which you might get wrong), focus on:

1. **Artist Recommendations:**
   - Artists similar to their favorites that they should explore
   - Specific albums or eras from their existing favorite artists
   - New artists in the same genres/styles

2. **Musical Directions:**
   - Subgenres they'd likely enjoy based on their taste
   - Specific musical characteristics to look for
   - Time periods or movements that align with their preferences

3. **Response Format:**
   Return a JSON array with artist recommendations and musical guidance:
   [
     {{"type": "artist", "name": "Artist Name", "reason": "Why they'd like this artist", "relation": "Similar to [their favorite artist]"}},
     {{"type": "direction", "description": "Musical direction or characteristic", "reason": "Why this fits their taste"}},
     ...
   ]

Focus on giving me the musical DNA and artist suggestions - I'll handle finding the actual tracks using Spotify's recommendation engine."""

        ai_response = None

        log_message(f"AI Provider configured: {AI_PROVIDER}")
        log_message(f"Processing {len(loved_tracks_data)} loved tracks for AI analysis...")
        log_message(f"Found {len(artists_list)} unique artists in your collection")
        log_message(f"Using {len(sample_tracks)} sample tracks to represent your taste")
        
        # Debug AI configuration
        log_message(f"OpenAI available: {openai is not None}, API key set: {OPENAI_API_KEY is not None and len(OPENAI_API_KEY) > 0}", 'yellow')
        log_message(f"Gemini available: {genai is not None}, API key set: {GEMINI_API_KEY is not None and len(GEMINI_API_KEY) > 0}", 'yellow')

        if AI_PROVIDER == "openai" and OPENAI_API_KEY and openai:
            try:
                openai.api_key = OPENAI_API_KEY
                log_message("Using OpenAI GPT-5-mini for AI recommendations...", 'green')
                log_message(f"Preparing to send analysis of your {len(loved_tracks_data)} tracks to OpenAI...", 'yellow')
                log_message("Sending music taste analysis to OpenAI API...", 'yellow')

                start_ai_time = time.time()
                response = openai.chat.completions.create(
                    model="gpt-5-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_completion_tokens=8192
                )
                ai_time = time.time() - start_ai_time
                ai_response = response.choices[0].message.content
                log_message(f"Successfully received AI recommendations from OpenAI in {ai_time:.1f} seconds!", 'green')
            except Exception as e:
                import traceback
                log_message(f"OpenAI API error: {e}", 'red')
                log_message(f"OpenAI error details: {traceback.format_exc()}", 'red')
                log_message("Falling back to Gemini if available...", 'yellow')
        
        if (not ai_response or AI_PROVIDER == "gemini") and GEMINI_API_KEY and genai:
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                log_message("Using Google Gemini for AI recommendations...", 'green')
                log_message(f"Preparing to send analysis of your {len(loved_tracks_data)} tracks to Gemini...", 'yellow')
                log_message("Sending music taste analysis to Gemini API...", 'yellow')
                log_message("This may take 10-30 seconds for Gemini to process your extensive music history...", 'yellow')
                
                start_ai_time = time.time()
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(prompt)
                ai_time = time.time() - start_ai_time
                ai_response = response.text
                log_message(f"Successfully received AI recommendations from Gemini in {ai_time:.1f} seconds!", 'green')
            except Exception as e:
                import traceback
                log_message(f"Gemini API error: {e}", 'red')
                log_message(f"Gemini error details: {traceback.format_exc()}", 'red')
        
        if not ai_response:
            log_message("No AI API available or all failed. Falling back to Last.fm recommendations.", 'red')
            log_message(f"Debug: AI_PROVIDER={AI_PROVIDER}, OPENAI_API_KEY length={len(OPENAI_API_KEY) if OPENAI_API_KEY else 0}, GEMINI_API_KEY length={len(GEMINI_API_KEY) if GEMINI_API_KEY else 0}", 'red')
            return get_lastfm_recommendations(sp, network, num_tracks, 50)
        
        try:
            log_message("Parsing AI response and extracting recommendations...", 'yellow')
            import json
            
            # Try multiple parsing strategies
            recommendations_data = None
            
            # Strategy 1: Look for JSON array in response
            json_match = re.search(r'\[.*?\]', ai_response, re.DOTALL)
            if json_match:
                try:
                    log_message("Found JSON array in AI response, attempting to parse...")
                    recommendations_data = json.loads(json_match.group())
                    log_message(f"Successfully parsed {len(recommendations_data)} recommendations from JSON array")
                except json.JSONDecodeError as e:
                    log_message(f"Failed to parse JSON array: {e}", 'yellow')
            
            # Strategy 2: Try parsing entire response
            if not recommendations_data:
                try:
                    log_message("Attempting to parse entire AI response as JSON...")
                    recommendations_data = json.loads(ai_response)
                    log_message(f"Successfully parsed {len(recommendations_data)} recommendations from full response")
                except json.JSONDecodeError as e:
                    log_message(f"Failed to parse full response: {e}", 'yellow')
            
            # Strategy 3: Look for multiple JSON arrays and take the largest one
            if not recommendations_data:
                log_message("Searching for multiple JSON arrays in response...")
                all_matches = re.findall(r'\[.*?\]', ai_response, re.DOTALL)
                for i, match in enumerate(all_matches):
                    try:
                        parsed = json.loads(match)
                        if isinstance(parsed, list) and len(parsed) > 0:
                            recommendations_data = parsed
                            log_message(f"Successfully parsed {len(recommendations_data)} recommendations from JSON array {i+1}")
                            break
                    except json.JSONDecodeError:
                        continue
            
            if not recommendations_data:
                raise ValueError("Could not extract valid JSON recommendations from AI response")
            
            log_message(f"AI provided {len(recommendations_data)} artist/direction recommendations", 'green')
            
            # Extract artist recommendations from AI
            ai_artists = []
            musical_directions = []
            
            for rec in recommendations_data:
                if isinstance(rec, dict):
                    if rec.get('type') == 'artist' and 'name' in rec:
                        ai_artists.append(rec['name'])
                        log_message(f"AI recommends artist: {rec['name']} - {rec.get('reason', '')}", 'yellow')
                    elif rec.get('type') == 'direction':
                        musical_directions.append(rec.get('description', ''))
                        log_message(f"AI suggests direction: {rec.get('description', '')}", 'yellow')
            
            # Now create hybrid recommendations
            log_message("Creating hybrid playlist with AI guidance...", 'green')
            recommended_tracks = []
            used_artists = set()
            used_tracks = set()
            
            # 1. Include some actual loved tracks (25% of total)
            loved_count = int(num_tracks * 0.25)
            log_message(f"Adding {loved_count} tracks from your loved collection...", 'yellow')
            
            # Shuffle loved tracks to ensure variety
            shuffled_loved = loved_tracks_data.copy()
            random.shuffle(shuffled_loved)
            
            for track_data in shuffled_loved:
                if len(recommended_tracks) >= loved_count:
                    break
                
                artist_name = track_data['artist'].lower()
                track_title = track_data['title'].lower()
                track_key = f"{track_title}|{artist_name}"
                
                # Skip various artists and live songs
                is_various_artists = 'various artists' in artist_name or 'va' == artist_name
                is_live = any(keyword in track_title for keyword in ['live', 'live at', 'live from', 'live in', 'live on', 'concert', 'acoustic version'])
                
                # Skip if we already have a song from this artist, this exact track, banned, or if it's filtered content
                if (artist_name not in used_artists and 
                    track_key not in used_tracks and 
                    not is_banned_item(track_data['title'], track_data['artist'], None, banned_items) and
                    not is_various_artists and 
                    not is_live):
                    class LovedTrack:
                        def __init__(self, title, artist_name):
                            self.title = title
                            self.artist = type('Artist', (), {'name': artist_name})()
                    
                    recommended_tracks.append(LovedTrack(track_data['title'], track_data['artist']))
                    used_artists.add(artist_name)
                    used_tracks.add(track_key)
            
            log_message(f"Added {len(recommended_tracks)} unique tracks from {len(used_artists)} different artists", 'green')
            
            # 2. Find tracks from AI-recommended artists using Last.fm and search (50% of total)
            ai_target_count = int(num_tracks * 0.5)
            log_message(f"Getting {ai_target_count} tracks from AI-recommended artists using Last.fm and Spotify search...", 'yellow')
            
            # Get tracks from AI-recommended artists using Last.fm
            ai_artist_tracks = []
            for artist_name in ai_artists[:10]:  # Use up to 10 AI-recommended artists
                if len(ai_artist_tracks) >= ai_target_count:
                    break
                try:
                    # Get top tracks from this artist using Last.fm
                    artist = network.get_artist(artist_name)
                    top_tracks = artist.get_top_tracks(limit=5)
                    
                    for track_item in top_tracks:
                        if len(ai_artist_tracks) >= ai_target_count:
                            break
                        
                        track = track_item.item
                        artist_name_lower = track.artist.name.lower()
                        track_title_lower = track.title.lower()
                        track_key = f"{track_title_lower}|{artist_name_lower}"
                        
                        # Skip various artists and live songs
                        is_various_artists = 'various artists' in artist_name_lower or 'va' == artist_name_lower
                        is_live = any(keyword in track_title_lower for keyword in ['live', 'live at', 'live from', 'live in', 'live on', 'concert', 'acoustic version'])
                        
                        # FIXED: Ensure one track per artist - skip if we already have a song from this artist, this exact track, banned, or if it's filtered content
                        if (artist_name_lower not in used_artists and 
                            track_key not in used_tracks and 
                            not is_banned_item(track.title, track.artist.name, None, banned_items) and
                            not is_various_artists and 
                            not is_live):
                            
                            # Verify the track exists on Spotify
                            try:
                                search_results = sp.search(
                                    q=f"track:{track.title} artist:{track.artist.name}", 
                                    type="track", 
                                    limit=1
                                )
                                if search_results["tracks"]["items"]:
                                    class AIRecommendedTrack:
                                        def __init__(self, title, artist_name):
                                            self.title = title
                                            self.artist = type('Artist', (), {'name': artist_name})()
                                    
                                    ai_artist_tracks.append(AIRecommendedTrack(
                                        track.title, 
                                        track.artist.name
                                    ))
                                    used_artists.add(artist_name_lower)
                                    used_tracks.add(track_key)
                            except Exception:
                                continue
                                
                except Exception as e:
                    log_message(f"Could not get tracks for AI-recommended artist {artist_name}: {e}", 'yellow')
                    continue
            
            recommended_tracks.extend(ai_artist_tracks)
            log_message(f"Added {len(ai_artist_tracks)} unique tracks from AI-recommended artists", 'green')
            
            # 3. Get similar artist tracks from Last.fm (fill remaining 25%)
            remaining_count = num_tracks - len(recommended_tracks)
            if remaining_count > 0:
                log_message(f"Getting {remaining_count} tracks from similar artists using Last.fm...", 'yellow')
                
                # Get similar artists based on user's loved tracks
                similar_artist_tracks = []
                sample_artists = random.sample(list(set([track['artist'] for track in loved_tracks_data])), min(5, len(loved_tracks_data)))
                
                for base_artist_name in sample_artists:
                    if len(similar_artist_tracks) >= remaining_count:
                        break
                    try:
                        base_artist = network.get_artist(base_artist_name)
                        similar_artists = base_artist.get_similar(limit=5)
                        
                        for similar_artist_item in similar_artists:
                            if len(similar_artist_tracks) >= remaining_count:
                                break
                            try:
                                similar_artist = similar_artist_item.item
                                top_tracks = similar_artist.get_top_tracks(limit=3)
                                
                                for track_item in top_tracks:
                                    if len(similar_artist_tracks) >= remaining_count:
                                        break
                                    
                                    track = track_item.item
                                    artist_name_lower = track.artist.name.lower()
                                    track_title_lower = track.title.lower()
                                    track_key = f"{track_title_lower}|{artist_name_lower}"
                                    
                                    # Skip various artists and live songs
                                    is_various_artists = 'various artists' in artist_name_lower or 'va' == artist_name_lower
                                    is_live = any(keyword in track_title_lower for keyword in ['live', 'live at', 'live from', 'live in', 'live on', 'concert', 'acoustic version'])
                                    
                                    # Ensure one track per artist
                                    if (artist_name_lower not in used_artists and 
                                        track_key not in used_tracks and 
                                        not is_banned_item(track.title, track.artist.name, None, banned_items) and
                                        not is_various_artists and 
                                        not is_live):
                                        
                                        # Verify the track exists on Spotify
                                        try:
                                            search_results = sp.search(
                                                q=f"track:{track.title} artist:{track.artist.name}", 
                                                type="track", 
                                                limit=1
                                            )
                                            if search_results["tracks"]["items"]:
                                                class SimilarArtistTrack:
                                                    def __init__(self, title, artist_name):
                                                        self.title = title
                                                        self.artist = type('Artist', (), {'name': artist_name})()
                                                
                                                similar_artist_tracks.append(SimilarArtistTrack(
                                                    track.title, 
                                                    track.artist.name
                                                ))
                                                used_artists.add(artist_name_lower)
                                                used_tracks.add(track_key)
                                                break  # Only one track per similar artist
                                        except Exception:
                                            continue
                            except Exception:
                                continue
                    except Exception as e:
                        log_message(f"Could not get similar artists for {base_artist_name}: {e}", 'yellow')
                        continue
                
                recommended_tracks.extend(similar_artist_tracks)
                log_message(f"Added {len(similar_artist_tracks)} unique tracks from similar artists", 'green')
                    
            # Fill any remaining slots with more loved tracks (avoiding duplicates)
            if len(recommended_tracks) < num_tracks:
                remaining_slots = num_tracks - len(recommended_tracks)
                log_message(f"Filling {remaining_slots} remaining slots with more loved tracks...", 'yellow')
                
                for track_data in shuffled_loved:
                    if len(recommended_tracks) >= num_tracks:
                        break
                        
                    artist_name = track_data['artist'].lower()
                    track_title = track_data['title'].lower()
                    track_key = f"{track_title}|{artist_name}"
                    
                    # Skip various artists and live songs
                    is_various_artists = 'various artists' in artist_name or 'va' == artist_name
                    is_live = any(keyword in track_title for keyword in ['live', 'live at', 'live from', 'live in', 'live on', 'concert', 'acoustic version'])
                    
                    # FIXED: Ensure one track per artist - skip if we already have a song from this artist, this exact track, banned, or if it's filtered content
                    if (artist_name not in used_artists and 
                        track_key not in used_tracks and 
                        not is_banned_item(track_data['title'], track_data['artist'], None, banned_items) and
                        not is_various_artists and 
                        not is_live):
                        class LovedTrack:
                            def __init__(self, title, artist_name):
                                self.title = title
                                self.artist = type('Artist', (), {'name': artist_name})()
                        
                        recommended_tracks.append(LovedTrack(track_data['title'], track_data['artist']))
                        used_artists.add(artist_name)
                        used_tracks.add(track_key)
            
            # Apply randomity factor
            if randomity_factor > 0:
                log_message(f"Applying randomity factor of {randomity_factor}%...", 'yellow')
                recommended_tracks = apply_randomity(recommended_tracks, randomity_factor)
            
            log_message(f"Generated {len(recommended_tracks)} hybrid AI+Spotify recommendations", 'green')
            return recommended_tracks
            
        except (json.JSONDecodeError, KeyError) as e:
            log_message(f"Failed to parse AI response: {e}", 'red')
            log_message("Falling back to Last.fm recommendations...", 'yellow')
            return get_lastfm_recommendations(sp, network, num_tracks, 50)
            
    except Exception as e:
        log_message(f"Error getting AI recommendations: {e}", 'red')
        return get_lastfm_recommendations(sp, network, num_tracks, 50)


def update_spotify_playlist(sp, playlist_id, tracks):
    try:
        banned_items = load_banned_items()
        user_id = sp.me()["id"]
        track_uris = []
        track_uris_set = set()  # Track URIs we've already added to avoid duplicates
        used_spotify_artists = set()  # Artist names we've already added to ensure one track per artist
        not_found_count = 0 #Counts how many tracks were not found
        banned_count = 0 #Counts how many tracks were banned
        artist_duplicate_count = 0 #Counts how many tracks were skipped due to artist already being used
        
        for track in tracks:
            # Try multiple search strategies to improve match rate
            search_queries = [
                f"track:{track.title} artist:{track.artist.name}",
                f"{track.title} {track.artist.name}",
                f"artist:{track.artist.name} {track.title}",
                track.title
            ]
            
            track_found = False
            for query in search_queries:
                try:
                    search_results = sp.search(q=query, type="track", limit=10)
                    if search_results["tracks"]["items"]:
                        # Look for best match by checking artist names
                        best_match = None
                        for result in search_results["tracks"]["items"]:
                            for artist in result["artists"]:
                                if (artist["name"].lower() == track.artist.name.lower() or 
                                    track.artist.name.lower() in artist["name"].lower() or
                                    artist["name"].lower() in track.artist.name.lower()):
                                    best_match = result
                                    break
                            if best_match:
                                break
                        
                        if best_match:
                            track_uri = best_match["uri"]
                            spotify_artist_name = best_match["artists"][0]["name"].lower()

                            # Check if we already have a track from this Spotify artist
                            if spotify_artist_name in used_spotify_artists:
                                log_message(f"Artist duplicate skipped: {track.title} by {track.artist.name} (already have track from {best_match['artists'][0]['name']})", 'yellow')
                                artist_duplicate_count += 1
                                track_found = True
                                break

                            # Check if this track has banned genres
                            if banned_items['genres']:
                                track_genres = get_track_genres(sp, track_uri)
                                if is_banned_item(track.title, track.artist.name, None, banned_items, track_genres):
                                    log_message(f"Track banned (genre filter): {track.title} by {track.artist.name}", 'yellow')
                                    banned_count += 1
                                    track_found = True
                                    break

                            if track_uri not in track_uris_set:
                                track_uris.append(track_uri)
                                track_uris_set.add(track_uri)
                                used_spotify_artists.add(spotify_artist_name)
                            track_found = True
                            break
                        elif query == search_queries[-1]:  # Last query, use first result
                            track_result = search_results["tracks"]["items"][0]
                            track_uri = track_result["uri"]
                            spotify_artist_name = track_result["artists"][0]["name"].lower()

                            # Check if we already have a track from this Spotify artist
                            if spotify_artist_name in used_spotify_artists:
                                log_message(f"Artist duplicate skipped: {track.title} by {track.artist.name} (already have track from {track_result['artists'][0]['name']})", 'yellow')
                                artist_duplicate_count += 1
                                track_found = True
                                break

                            # Check if this track has banned genres
                            if banned_items['genres']:
                                track_genres = get_track_genres(sp, track_uri)
                                if is_banned_item(track.title, track.artist.name, None, banned_items, track_genres):
                                    log_message(f"Track banned (genre filter): {track.title} by {track.artist.name}", 'yellow')
                                    banned_count += 1
                                    track_found = True
                                    break

                            if track_uri not in track_uris_set:
                                track_uris.append(track_uri)
                                track_uris_set.add(track_uri)
                                used_spotify_artists.add(spotify_artist_name)
                            track_found = True
                            break
                except Exception as e:
                    continue
            
            if not track_found:
                log_message(f"Track not found: {track.title} by {track.artist.name}", 'yellow')
                not_found_count += 1

        # Replace playlist contents (completely clears and adds new tracks)
        log_message(f"Replacing playlist with {len(track_uris)} new tracks...", 'yellow')

        if track_uris:
            # First call replaces ALL existing tracks with new ones
            sp.playlist_replace_items(playlist_id, track_uris[:100])
            # Add remaining tracks in batches of 100
            for i in range(100, len(track_uris), 100):
                sp.playlist_add_items(playlist_id, track_uris[i : i + 100])
        else:
            # If no tracks, just clear the playlist
            log_message("No tracks to add, clearing playlist", 'yellow')
            sp.playlist_replace_items(playlist_id, [])

        log_message(f"Playlist updated successfully! Added {len(track_uris)} tracks. {not_found_count} tracks not found, {banned_count} tracks banned, {artist_duplicate_count} artist duplicates skipped.", 'green')


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


def job(playlist_id=None):
    target_playlist_id = playlist_id or SPOTIFY_PLAYLIST_ID
    
    log_message(f"Starting playlist update job (version {__version__})...", 'yellow')
    log_message(f"Target playlist ID: {target_playlist_id}")
    log_message(f"Requesting {NUMBER_OF_TRACKS} tracks from Last.fm user: {LASTFM_USERNAME}")
    log_message("Mode: AI-powered My Station")

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

    log_message("Generating Apple Music-style discovery station...")
    tracks = get_apple_music_discovery_station(spotify_client, lastfm_network, NUMBER_OF_TRACKS)
    
    if not tracks:
        log_message("Failed to retrieve tracks from Last.fm. Aborting.", 'red')
        return
    log_message(f"Successfully retrieved {len(tracks)} tracks from Last.fm.", 'green')

    log_message("Updating Spotify playlist...")
    update_spotify_playlist(spotify_client, target_playlist_id, tracks)

    log_message("Saving playlist history...")
    save_playlist_history(tracks)

    log_message("Playlist update job completed successfully.", 'green')


# --- Main ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Spotify My Station - Sonic similarity station based on recent favorites')
    parser.add_argument('--playlist', type=str,
                       help='Spotify playlist ID to update (overrides environment variable)')

    args = parser.parse_args()
    job(playlist_id=args.playlist)
