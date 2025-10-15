### 1.9.0: 2025-10-15

* Fix playlist history never being saved after updates
* Add save_playlist_history call after each playlist update
* Fix same songs repeating every hour due to stale history file
* Resolve issue where history file was stuck at July 5th timestamp

### 1.8.0: 2025-10-14

* Fix repetitive tracks by requiring 3+ plays for recent favorites category
* Add play count threshold to prevent single plays from dominating recommendations
* Improve variety by filtering recent favorites to only heavily played artists

### 1.7.0: 2025-10-09

* Fix feedback loop by excluding generated playlist tracks from recent listening analysis
* Switch to coherent My Station algorithm as default (40% recent, 30% genre-cohesive, 20% discovery, 10% classics)
* Add 10% allowance for playlist tracks as nice surprises of actual favorites
* Filter 90% of generated playlist tracks when analyzing Last.fm recent listening patterns

### 1.6.0: 2025-10-09

* Upgrade model from gpt-4o-mini to gpt-5-mini
* Implement Apple Music "My Station"-style algorithm with temporal awareness
* Add 35% recently played favorites, 30% deep cuts, 20% smart discovery, 15% rediscoveries mix
* Add genre coherence to prevent jarring transitions (no more jazz to black metal jumps)
* Implement smart shuffling that groups similar genres into 3-5 track sessions
* Add genre family clustering (rock, electronic, jazz, etc.) with smooth transitions
* Add Spotify genre data integration for accurate genre detection
* Add recency weighting to prioritize current listening habits over old favorites
* Add temporal analysis for 30-day, 90-day, and 6-month listening patterns
* Improve discovery tracks to be based on recent listening, not random favorites
* Add intelligent session ordering for natural genre flow

### 1.5.0: 2025-07-06

* Streamlined script to use AI by default, removed complex flags
* Add genre filtering support with genre: prefix in banned.json 
* Enforce one track per artist rule in Spotify playlist updates
* Support both OPENAI_API_KEY and OPEN_AI_API_KEY environment variables
* Enhanced logging for banned items and artist duplicates
* Fix Last.fm fallback parameter errors
* Remove automatic banned.json file creation
* Update documentation for simplified usage

### 1.4.0: 2025-07-05

* Fix duplicate tracks appearing in playlists by adding Spotify URI deduplication
* Add persistent playlist history tracking to avoid repetitive songs across runs
* Add `--randomity [0-100]` parameter to control selection randomness (0=predictable, 100=random, default=50)
* Fix CoherentTrack class scope error in coherency-based mode
* Enhance all recommendation modes (AI, coherency-based, recommended, random) with history awareness
* Add cross-run persistence with playlist-history.json file
* Improve track variety and reduce algorithmic predictability
* Guarantee 100 tracks: Multi-tier fallback system ensures exactly 100 tracks are always added regardless of filtering
* Add comprehensive banned items feature with `banned.json` file supporting songs, artists, and albums with clear prefixes (song:, artist:, album:)
* Add automatic expansion from discovery candidates when filtering reduces track count
* Add case-insensitive banned song title matching across all recommendation modes

### 1.3.0: 2025-07-04

* Add `--coherency-based` flag which takes into account top artists this week

### 1.2.0: 2025-07-04

* Replace deprecated Spotify recommendations API with Last.fm-based approach
* Enforce one track per artist constraint across all recommendation modes
* AI hybrid mode now uses 25% loved tracks, 50% AI-recommended artists, 25% similar artists
* Better track verification to ensure all tracks exist on Spotify before adding
* Enhanced filtering for live tracks and various artists compilations
* Remove Spotify recommendations API calls due to deprecation in November 2024

### 1.1.0: 2025-07-02

* Add AI-powered My Station mode with --ai parameter
* Add OpenAI GPT-4o-mini and Google Gemini AI integration
* Add configurable AI provider selection via AI_PROVIDER environment variable
* Add hybrid approach: AI suggests artists, Spotify finds tracks (40% loved tracks, 60% AI-guided recommendations)
* Add deduplication logic to prevent multiple songs from same artist
* Add filtering to exclude "Various Artists" and live recordings
* Add verbose progress logging for large music collections
* Add robust JSON parsing with multiple fallback strategies
* Add listening history analysis from log files

### 1.0.1: 2025-07-01

* Add recommended tracks mode with --recommended parameter
* Add logic to prioritize less played and newer tracks
* Add argparse for command line argument handling

### 1.0.0: 2025-06-30

* Add initial release of Spotify My Station
* Add automatic playlist updates with Last.fm loved tracks
* Add hourly scheduling system using Python schedule library
* Add environment variable configuration support
* Add comprehensive logging system
* Add virtual environment setup documentation
* Add cron job scheduling instructions
* Add README with complete setup guide
* Add security improvements with .env file usage
* Add random track fetching from Last.fm loved tracks
* Add automatic Spotify playlist updates
* Add track removal before adding new ones
* Add configurable number of tracks (default: 100)
* Add detailed logging with timestamps
* Add error handling for API authentication failures
* Add support for tracks not found on Spotify
* Add API credentials moved to environment variables
* Add .gitignore to prevent credential exposure
* Add .env.example template for easy setup
