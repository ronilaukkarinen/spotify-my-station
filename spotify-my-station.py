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

__version__ = "1.2.0"

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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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
        
        # Use only 30% loved tracks for more variety
        loved_count = int(num_tracks * 0.3)
        if len(all_tracks) < loved_count:
            log_message(f"Warning: Less than {loved_count} loved tracks found. Using {len(all_tracks)} tracks.", 'yellow')
            loved_count = len(all_tracks)

        log_message(f"Selecting {loved_count} random tracks from {len(all_tracks)} total loved tracks...")
        random_tracks = random.sample(all_tracks, loved_count)
        
        # Add similar artists recommendations to fill remaining slots
        remaining_slots = num_tracks - loved_count
        if remaining_slots > 0:
            log_message(f"Getting {remaining_slots} additional tracks from similar artists...")
            similar_tracks = get_similar_artist_tracks(network, all_tracks, remaining_slots)
            if similar_tracks:
                random_tracks.extend(similar_tracks)
        
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
        
        # Get similar artists for a sample of user's artists
        for artist_name in artists[:20]:  # Limit to prevent API overload
            if len(similar_tracks) >= num_tracks:
                break
                
            try:
                artist = network.get_artist(artist_name)
                similar_artists = artist.get_similar(limit=5)
                
                for similar_artist in similar_artists:
                    if len(similar_tracks) >= num_tracks:
                        break
                    
                    similar_artist_name = similar_artist.item.name
                    if similar_artist_name.lower() not in used_artists:
                        try:
                            top_tracks = similar_artist.item.get_top_tracks(limit=3)
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


def get_lastfm_recommendations(sp, network, num_tracks=100):
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
            return get_random_tracks_from_lastfm(network, num_tracks)
        
        # Shuffle and trim to requested number
        random.shuffle(recommended_tracks)
        recommended_tracks = recommended_tracks[:num_tracks]
        
        log_message(f"Generated {len(recommended_tracks)} Last.fm-based recommendations", 'green')
        return recommended_tracks
        
    except Exception as e:
        import traceback
        log_message(f"Error getting Last.fm recommendations: {str(e)}", 'red')
        log_message(f"Traceback: {traceback.format_exc()}", 'red')
        return None


def get_ai_hybrid_recommendations(sp, network, history_analysis, num_tracks=100):
    try:
        log_message("Getting AI-powered recommendations...")
        
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

Your task: Recommend artists and musical directions for creating the perfect personalized radio station.

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
        
        if AI_PROVIDER == "openai" and OPENAI_API_KEY and openai:
            try:
                openai.api_key = OPENAI_API_KEY
                log_message("Using OpenAI GPT-4o-mini for AI recommendations...", 'green')
                log_message(f"Preparing to send analysis of your {len(loved_tracks_data)} tracks to OpenAI...", 'yellow')
                log_message("Sending music taste analysis to OpenAI API...", 'yellow')
                
                start_ai_time = time.time()
                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=4000
                )
                ai_time = time.time() - start_ai_time
                ai_response = response.choices[0].message.content
                log_message(f"Successfully received AI recommendations from OpenAI in {ai_time:.1f} seconds!", 'green')
            except Exception as e:
                log_message(f"OpenAI API error: {e}", 'red')
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
                log_message(f"Gemini API error: {e}", 'red')
        
        if not ai_response:
            log_message("No AI API available or all failed. Falling back to Last.fm recommendations.", 'red')
            return get_lastfm_recommendations(None, network, num_tracks)
        
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
                
                # Skip if we already have a song from this artist, this exact track, or if it's filtered content
                if (artist_name not in used_artists and 
                    track_key not in used_tracks and 
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
                        
                        # FIXED: Ensure one track per artist - skip if we already have a song from this artist, this exact track, or if it's filtered content
                        if (artist_name_lower not in used_artists and 
                            track_key not in used_tracks and 
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
                    
                    # FIXED: Ensure one track per artist - skip if we already have a song from this artist, this exact track, or if it's filtered content
                    if (artist_name not in used_artists and 
                        track_key not in used_tracks and 
                        not is_various_artists and 
                        not is_live):
                        class LovedTrack:
                            def __init__(self, title, artist_name):
                                self.title = title
                                self.artist = type('Artist', (), {'name': artist_name})()
                        
                        recommended_tracks.append(LovedTrack(track_data['title'], track_data['artist']))
                        used_artists.add(artist_name)
                        used_tracks.add(track_key)
            
            log_message(f"Generated {len(recommended_tracks)} hybrid AI+Spotify recommendations", 'green')
            return recommended_tracks
            
        except (json.JSONDecodeError, KeyError) as e:
            log_message(f"Failed to parse AI response: {e}", 'red')
            log_message("Falling back to Last.fm recommendations...", 'yellow')
            return get_lastfm_recommendations(None, network, num_tracks)
            
    except Exception as e:
        log_message(f"Error getting AI recommendations: {e}", 'red')
        return get_lastfm_recommendations(None, network, num_tracks)


def update_spotify_playlist(sp, playlist_id, tracks):
    try:
        user_id = sp.me()["id"]
        track_uris = []
        not_found_count = 0 #Counts how many tracks were not found
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
                            track_uris.append(track_uri)
                            track_found = True
                            break
                        elif query == search_queries[-1]:  # Last query, use first result
                            track_uri = search_results["tracks"]["items"][0]["uri"]
                            track_uris.append(track_uri)
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


def job(use_recommended=False, use_ai=False, playlist_id=None):
    target_playlist_id = playlist_id or SPOTIFY_PLAYLIST_ID
    log_message(f"Starting playlist update job (version {__version__})...", 'yellow')
    log_message(f"Target playlist ID: {target_playlist_id}")
    log_message(f"Requesting {NUMBER_OF_TRACKS} tracks from Last.fm user: {LASTFM_USERNAME}")
    
    mode = "AI-powered My Station" if use_ai else ("Recommended" if use_recommended else "Random")
    log_message(f"Mode: {mode} tracks")
    
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

    if use_ai:
        log_message("Analyzing listening history for AI recommendations...")
        history_analysis = analyze_listening_history()
        log_message("Generating AI-powered hybrid My Station recommendations...")
        tracks = get_ai_hybrid_recommendations(spotify_client, lastfm_network, history_analysis, NUMBER_OF_TRACKS)
    elif use_recommended:
        log_message("Generating recommendations based on your Last.fm loved tracks...")
        tracks = get_lastfm_recommendations(spotify_client, lastfm_network, NUMBER_OF_TRACKS)
    else:
        log_message("Fetching random tracks from Last.fm loved tracks...")
        tracks = get_random_tracks_from_lastfm(lastfm_network, NUMBER_OF_TRACKS)
    
    if not tracks:
        log_message("Failed to retrieve tracks from Last.fm. Aborting.", 'red')
        return
    log_message(f"Successfully retrieved {len(tracks)} tracks from Last.fm.", 'green')

    log_message("Updating Spotify playlist...")
    update_spotify_playlist(spotify_client, target_playlist_id, tracks)
    log_message("Playlist update job completed successfully.", 'green')


# --- Main ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Spotify My Station - Update playlist with Last.fm loved tracks')
    parser.add_argument('--recommended', action='store_true', 
                       help='Use recommended mode (less played + newer tracks) instead of random selection')
    parser.add_argument('--ai', action='store_true',
                       help='Use AI-powered My Station mode (mimics Apple Music My Station with familiar favorites + discoveries)')
    parser.add_argument('--playlist', type=str,
                       help='Spotify playlist ID to update (overrides environment variable)')
    
    args = parser.parse_args()
    job(use_recommended=args.recommended, use_ai=args.ai, playlist_id=args.playlist)
