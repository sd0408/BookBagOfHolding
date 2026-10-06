# BookBagOfHolding

**Your digital reading companion for automated book, audiobook, and magazine management.**

[![CI](https://github.com/sd0408/BookBagOfHolding/actions/workflows/ci.yml/badge.svg)](https://github.com/sd0408/BookBagOfHolding/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

BookBagOfHolding is an open-source metadata aggregation and download automation system for digital reading materials. It monitors your favorite authors, tracks new releases, and automates the acquisition and organization of ebooks, audiobooks, magazines, and comics.

> **Note:** This project is a modernized fork of [LazyLibrarian](https://gitlab.com/LazyLibrarian/LazyLibrarian). We extend our gratitude to the original developers and community.

---

## Table of Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Quick Start](#quick-start)
  - [Docker (Recommended)](#docker-recommended)
  - [Manual Installation](#manual-installation)
- [Configuration](#configuration)
  - [Basic Settings](#basic-settings)
  - [Metadata Sources](#metadata-sources)
  - [Download Clients](#download-clients)
  - [Search Providers](#search-providers)
- [Usage](#usage)
  - [Web Interface](#web-interface)
  - [REST API](#rest-api)
  - [OPDS Catalog](#opds-catalog)
  - [Command Line Options](#command-line-options)
- [Advanced Configuration](#advanced-configuration)
  - [Post-Processing](#post-processing)
  - [Calibre Integration](#calibre-integration)
  - [Running as a Service](#running-as-a-service)
- [Contributing](#contributing)
  - [Development Setup](#development-setup)
  - [Code Style](#code-style)
  - [Testing](#testing)
  - [Pull Request Guidelines](#pull-request-guidelines)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

### Core Functionality
- **Author Monitoring** - Follow your favorite authors and automatically track new releases
- **Multi-Source Metadata** - Aggregates data from Goodreads, Google Books, and LibraryThing
- **Automated Downloads** - Searches and downloads based on your preferences
- **Library Management** - Organize, rename, and manage your digital collection
- **Series Tracking** - Track book series and reading order

### Supported Media Types
- **Ebooks** - epub, mobi, pdf, azw3, cbr, cbz, and more
- **Audiobooks** - mp3, m4b, m4a, flac
- **Magazines** - PDF issues with date tracking
- **Comics** - cbr, cbz formats

### Download Client Support

| Usenet | Torrent |
|--------|---------|
| SABnzbd | qBittorrent |
| NZBGet | rTorrent |
| Synology NZB | Transmission |
| | Deluge |
| | uTorrent |
| | Synology Torrent |

### Additional Features
- **Modern Web UI** - Responsive Bootstrap 5 interface
- **REST API** - Full programmatic access
- **OPDS Catalog** - Compatible with e-reader apps
- **Post-Processing** - Automatic file organization and renaming
- **Calibre Integration** - Format conversion and library sync
- **Multi-Platform** - Linux, macOS, Windows, Docker

---

## Quick Start

### Docker (Recommended)

The easiest way to run BookBagOfHolding is with Docker:

```bash
docker run -d \
  --name bookbagofholding \
  -p 5299:5299 \
  -v /path/to/config:/config \
  -v /path/to/books:/books \
  -v /path/to/downloads:/downloads \
  --restart unless-stopped \
  ghcr.io/sd0408/bookbagofholding:latest
```

Or with Docker Compose:

```yaml
# docker-compose.yml
services:
  bookbagofholding:
    image: ghcr.io/sd0408/bookbagofholding:latest
    container_name: bookbagofholding
    ports:
      - "5299:5299"
    volumes:
      - /path/to/config:/config
      - /path/to/books:/books
      - /path/to/downloads:/downloads
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York
    restart: unless-stopped
```

Then start it:

```bash
docker-compose up -d
```

Access the web interface at `http://localhost:5299`

### Manual Installation

#### Requirements
- Python 3.10 or higher
- pip (Python package manager)

#### System Libraries (Optional but Recommended)

Some features require system libraries to be installed:

**macOS (Homebrew):**
```bash
brew install libmagic unrar
```

**Ubuntu/Debian:**
```bash
sudo apt install libmagic1 unrar
```

**Fedora/RHEL:**
```bash
sudo dnf install file-libs unrar
```

| Library | Purpose | Required For |
|---------|---------|--------------|
| libmagic | File type detection | Accurate file identification |
| unrar/libunrar | RAR archive extraction | Processing RAR downloads |

> **Note:** The Docker image includes all system libraries pre-installed.

#### Installation Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/sd0408/BookBagOfHolding.git
   cd BookBagOfHolding
   ```

2. **Create a virtual environment (recommended)**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   # or
   .venv\Scripts\activate     # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -e .
   ```

4. **Run the application**
   ```bash
   python BookBagOfHolding.py
   ```

5. **Access the web interface**

   Open your browser to `http://localhost:5299`

---

## Configuration

On first run, BookBagOfHolding creates a `config.ini` file in your data directory. You can configure settings through the web interface at **Config** or by editing the file directly.

### Basic Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `HTTP_PORT` | 5299 | Web interface port |
| `HTTP_HOST` | 0.0.0.0 | Bind address |
| `EBOOK_DIR` | | Path to your ebook library |
| `AUDIO_DIR` | | Path to audiobook library |
| `DOWNLOAD_DIR` | | Path for downloads |
| `LAUNCH_BROWSER` | 1 | Open browser on startup |

### Metadata Sources

BookBagOfHolding uses multiple sources to gather comprehensive metadata:

#### Google Books API (Recommended)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the Books API
4. Create an API key
5. Add to Config → API Keys → Google Books API

> **Note:** Since late September 2026 Google Books returns no results for field-restricted
> queries (`inauthor:`, `intitle:`, `isbn:`), even with a valid key. Author and title lookups
> now use plain-text searches, filtered by author and ranked by fuzzy match, instead. Searching
> by ISBN will find nothing until Google restores `isbn:` queries.

#### LibraryThing (Optional)
1. Get a developer key from [LibraryThing](https://www.librarything.com/services/keys.php)
2. Add to Config → API Keys → LibraryThing Developer Key

### Download Clients

Configure your preferred download client under **Config → Download Settings**.

#### SABnzbd Example
```ini
SAB_HOST = localhost
SAB_PORT = 8080
SAB_APIKEY = your_api_key
SAB_CATEGORY = books
```

#### qBittorrent Example
```ini
QBITTORRENT_HOST = localhost
QBITTORRENT_PORT = 8080
QBITTORRENT_USER = admin
QBITTORRENT_PASS = your_password
QBITTORRENT_LABEL = books
```

### Search Providers

Add Newznab/Torznab indexers under **Config → Search Providers**:

| Setting | Description |
|---------|-------------|
| `NEWZNAB_HOST` | Indexer URL |
| `NEWZNAB_API` | API key |
| `NEWZNAB_ENABLED` | Enable/disable |

You can configure up to 5 Newznab and 5 Torznab providers.

---

## Usage

### Web Interface

The web interface provides full control over BookBagOfHolding:

| Page | Description |
|------|-------------|
| **Dashboard** | Overview of library stats and recent activity |
| **Authors** | Browse and manage followed authors |
| **Books** | View all books, filter by status |
| **Magazines** | Manage magazine subscriptions |
| **Series** | Track book series |
| **Wanted** | Queue of books to download |
| **History** | Download history |
| **Config** | All settings |

#### Adding Authors
1. Navigate to **Authors** → **Add Author**
2. Search by author name
3. Select the correct author from results
4. BookBagOfHolding will import all their books

#### Managing Books
- **Wanted** - Books to search for
- **Have** - Books in your library
- **Ignored** - Books you don't want
- **Skipped** - Temporarily skipped

### REST API

The API is available at `/api` with your API key:

```bash
# Get all authors
curl "http://localhost:5299/api?cmd=getIndex&apikey=YOUR_API_KEY"

# Get wanted books
curl "http://localhost:5299/api?cmd=getWanted&apikey=YOUR_API_KEY"

# Force book search
curl "http://localhost:5299/api?cmd=forceBookSearch&apikey=YOUR_API_KEY"

# Get specific author
curl "http://localhost:5299/api?cmd=getAuthor&id=AUTHOR_ID&apikey=YOUR_API_KEY"
```

#### Common API Commands

| Command | Description |
|---------|-------------|
| `getIndex` | List all authors |
| `getAuthor` | Get author details |
| `getWanted` | List wanted books |
| `getSnatched` | List snatched books |
| `queueBook` | Add book to wanted |
| `forceBookSearch` | Trigger search |
| `forceProcess` | Run post-processor |
| `getLogs` | Get log entries |

### OPDS Catalog

BookBagOfHolding provides an OPDS catalog for e-reader apps:

- **URL:** `http://localhost:5299/opds`
- **Authentication:** Uses your web credentials if enabled

Compatible with apps like:
- Moon+ Reader
- FBReader
- Calibre
- KOReader

### Command Line Options

```
Usage: BookBagOfHolding.py [options]

Options:
  -d, --daemon       Run as background daemon (Linux/macOS)
  -q, --quiet        Suppress console output
  --debug            Enable debug logging
  --nolaunch         Don't open browser on startup
  --port PORT        Override HTTP port
  --datadir DIR      Set data directory
  --config FILE      Use alternate config file
  -p, --pidfile FILE Write process ID to file
  --loglevel LEVEL   Set debug verbosity (0-4)
```

---

## Advanced Configuration

### Post-Processing

Configure automatic file organization under **Config → Processing**.

#### Filename Templates

Use these variables in your naming templates:

| Variable | Description |
|----------|-------------|
| `$Author` | Author name |
| `$Title` | Book title |
| `$Series` | Series name |
| `$SeriesNum` | Position in series |
| `$Year` | Publication year |
| `$ISBN` | ISBN number |

**Example folder structure:**
```
$Author/$Series/$Title
```
Results in: `Stephen King/The Dark Tower/The Gunslinger`

### Calibre Integration

BookBagOfHolding can integrate with Calibre for format conversion:

1. Install Calibre or use the Docker image (includes Calibre)
2. Enable in **Config → Processing → Calibre Integration**
3. Set your Calibre library path
4. Configure preferred output format

### Running as a Service

#### systemd (Linux)

```bash
# Copy the service file
sudo cp init/bookbagofholding.service /etc/systemd/system/

# Edit paths and user
sudo nano /etc/systemd/system/bookbagofholding.service

# Enable and start
sudo systemctl enable bookbagofholding
sudo systemctl start bookbagofholding
```

#### init.d (Legacy Linux)

```bash
sudo cp init/bookbagofholding.initd /etc/init.d/bookbagofholding
sudo chmod +x /etc/init.d/bookbagofholding
sudo update-rc.d bookbagofholding defaults
```

See [init/INSTALL.txt](init/INSTALL.txt) for detailed instructions.

---

## Contributing

We welcome contributions! Here's how to get started.

### Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/BookBagOfHolding.git
   cd BookBagOfHolding
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install with development dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Run the test suite**
   ```bash
   python -m pytest bookbagofholding/unittests/
   ```

### Code Style

- Follow PEP 8 guidelines
- Use meaningful variable and function names
- Add docstrings to public functions
- Keep functions focused and concise

Run the linter before committing:
```bash
flake8 bookbagofholding/
```

### Testing

**All code changes must include tests.**

- Test files go in `bookbagofholding/unittests/`
- Name test files `test_<module>.py`
- Use pytest fixtures from `conftest.py`
- Mock external dependencies

```bash
# Run all tests
python -m pytest bookbagofholding/unittests/

# Run with coverage
python -m pytest bookbagofholding/unittests/ --cov=bookbagofholding

# Run specific test file
python -m pytest bookbagofholding/unittests/test_api.py

# Run tests matching pattern
python -m pytest -k "test_author"
```

### Pull Request Guidelines

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clean, documented code
   - Add or update tests
   - Ensure all tests pass

3. **Commit with clear messages**
   ```bash
   git commit -m "Add feature: description of what it does"
   ```

4. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

5. **In your PR description:**
   - Describe what the change does
   - Reference any related issues
   - Note any breaking changes

---

## Project Structure

```
BookBagOfHolding/
├── BookBagOfHolding.py          # Main entry point
├── bookbagofholding/            # Core application package
│   ├── __init__.py              # Global config and initialization
│   ├── webServe.py              # Web interface routes
│   ├── webStart.py              # CherryPy server setup
│   ├── api.py                   # REST API endpoints
│   ├── database.py              # SQLite database layer
│   ├── common.py                # Utilities and scheduler
│   │
│   ├── # Metadata Sources
│   ├── gb.py                    # Google Books integration
│   ├── grsync.py                # Goodreads sync
│   │
│   ├── # Search & Providers
│   ├── searchbook.py            # Book search logic
│   ├── searchmag.py             # Magazine search
│   ├── providers.py             # Provider interface
│   ├── torrentparser.py         # Torrent site parsers
│   ├── directparser.py          # Direct download parsers
│   │
│   ├── # Download Clients
│   ├── sabnzbd.py, nzbget.py    # Usenet clients
│   ├── qbittorrent.py, ...      # Torrent clients
│   │
│   ├── # Library Management
│   ├── librarysync.py           # Library scanning
│   ├── postprocess.py           # Download processing
│   ├── calibre.py               # Calibre integration
│   │
│   └── unittests/               # Test suite
│
├── data/
│   ├── interfaces/modern/       # Web UI templates
│   ├── css/                     # Stylesheets
│   ├── js/                      # JavaScript
│   └── images/                  # UI assets
│
├── docker/                      # Docker configuration
├── init/                        # Service init scripts
└── examples/                    # Example scripts
```

---

## Troubleshooting

### Common Issues

**Port already in use**
```bash
# Change port in config.ini or use --port flag
python BookBagOfHolding.py --port 5300
```

**Permission denied on library folders**
```bash
# Ensure the user running BookBagOfHolding has read/write access
chown -R $USER:$USER /path/to/books
```

**Database locked errors**
- Ensure only one instance is running
- Check for zombie processes: `ps aux | grep BookBagOfHolding`

**Search not finding books**
- Verify your search providers are configured
- Check API keys are valid
- Review logs at **Logs** page

### Logs

Logs are stored in your data directory:
- Default: `~/.bookbagofholding/logs/`
- View in web UI: **Logs** page
- Debug mode: `python BookBagOfHolding.py --debug`

### Getting Help

- **GitHub Issues:** [Report bugs or request features](https://github.com/sd0408/BookBagOfHolding/issues)
- **Documentation:** [bookbagofholding.gitlab.io](https://bookbagofholding.gitlab.io/)

---

## License

BookBagOfHolding is released under the **GNU General Public License v3.0**.

This means:
- You can use, modify, and distribute this software
- Any modifications must also be released under GPL v3
- You must include the original license and copyright notice

See [LICENSE](LICENSE) for the full text.

---

## Acknowledgments

### LazyLibrarian

BookBagOfHolding is a fork of [LazyLibrarian](https://gitlab.com/LazyLibrarian/LazyLibrarian), an excellent open-source project that has served the book automation community for many years. We are deeply grateful to the LazyLibrarian developers and contributors whose work made this project possible.

This fork aims to modernize the codebase while preserving the core functionality that made LazyLibrarian so valuable to its users.

### Open Source Libraries

BookBagOfHolding also builds on the work of many other open-source projects:

- [CherryPy](https://cherrypy.dev/) - Web framework
- [Mako](https://www.makotemplates.org/) - Template engine
- [Bootstrap](https://getbootstrap.com/) - UI framework
- [FuzzyWuzzy](https://github.com/seatgeek/fuzzywuzzy) - Fuzzy string matching
- [APScheduler](https://apscheduler.readthedocs.io/) - Job scheduling

---

**Happy Reading!**
