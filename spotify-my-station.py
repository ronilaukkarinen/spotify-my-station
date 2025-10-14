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

__version__ = "1.8.0"

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
    """Save current playlist tracks to history to avoid repetition in future runs."""
    try:
        history = load_playlist_history()
        banned_items = load_banned_items()

        # Add current tracks to history (excluding banned items)
        current_tracks = []
        current_artists = []

        for track in tracks:
            # Double-check that we're not saving banned items
            if not is_banned_item(track.title, track.artist.name, None, banned_items):
                track_key = f"{track.title.lower()}|{track.artist.name.lower()}"
                current_tracks.append(track_key)
                current_artists.append(track.artist.name.lower())
        
        # Keep only last 1.5 runs worth of history for better variety (150 tracks max)
        max_history = int(NUMBER_OF_TRACKS * 1.5)
        
        # Combine with existing history
        all_tracks = current_tracks + history.get("recent_tracks", [])
        all_artists = current_artists + history.get("recent_artists", [])
        
        # Remove duplicates while preserving order
        seen_tracks = set()
        seen_artists = set()
        unique_tracks = []
        unique_artists = []
        
        for track in all_tracks:
            if track not in seen_tracks:
                unique_tracks.append(track)
                seen_tracks.add(track)
        
        for artist in all_artists:
            if artist not in seen_artists:
                unique_artists.append(artist)
                seen_artists.add(artist)
        
        # Trim to max history
        history["recent_tracks"] = unique_tracks[:max_history]
        history["recent_artists"] = unique_artists[:max_history]
        history["last_updated"] = datetime.now().isoformat()
        
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
        
        log_message(f"Saved {len(current_tracks)} tracks to playlist history", 'green')
        
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
    """Check if a track was recently used in previous playlists."""
    track_key = f"{track_title.lower()}|{artist_name.lower()}"
    artist_key = artist_name.lower()
    
    recent_tracks = playlist_history.get("recent_tracks", [])
    recent_artists = playlist_history.get("recent_artists", [])
    
    return track_key in recent_tracks or artist_key in recent_artists


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
            scope="playlist-modify-public playlist-modify-private user-read-private",
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

        log_message(f"Playlist updated. Added {len(track_uris)} tracks. {not_found_count} tracks not found, {banned_count} tracks banned, {artist_duplicate_count} artist duplicates skipped.", 'green')


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

    log_message("Analyzing listening history for recommendations...")
    history_analysis = analyze_listening_history()
    log_message("Generating coherent My Station recommendations...")
    tracks = get_coherent_my_station_recommendations(spotify_client, lastfm_network, history_analysis, NUMBER_OF_TRACKS, RANDOMITY_FACTOR)
    
    if not tracks:
        log_message("Failed to retrieve tracks from Last.fm. Aborting.", 'red')
        return
    log_message(f"Successfully retrieved {len(tracks)} tracks from Last.fm.", 'green')

    log_message("Updating Spotify playlist...")
    update_spotify_playlist(spotify_client, target_playlist_id, tracks)
    
    log_message("Playlist update job completed successfully.", 'green')


# --- Main ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Spotify My Station - AI-powered playlist with Last.fm loved tracks')
    parser.add_argument('--playlist', type=str,
                       help='Spotify playlist ID to update (overrides environment variable)')
    
    args = parser.parse_args()
    job(playlist_id=args.playlist)
