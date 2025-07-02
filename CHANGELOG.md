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
