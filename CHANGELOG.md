# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### 1.0.0: 2025-06-30

### Added
* Initial release of Spotify My Station
* Automatic playlist updates with Last.fm loved tracks
* Hourly scheduling system using Python schedule library
* Environment variable configuration support
* Comprehensive logging system
* Virtual environment setup documentation
* Cron job scheduling instructions
* README with complete setup guide
* Security improvements with .env file usage

### Features
* Fetches random tracks from Last.fm loved tracks
* Updates specified Spotify playlist automatically
* Removes existing tracks before adding new ones
* Configurable number of tracks (default: 100)
* Detailed logging with timestamps
* Error handling for API authentication failures
* Support for tracks not found on Spotify

### Security
* Moved all API credentials to environment variables
* Added .gitignore to prevent credential exposure
* Created .env.example template for easy setup