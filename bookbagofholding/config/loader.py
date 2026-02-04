#  This file is part of Bookbag of Holding.
#  Bookbag of Holding is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Bookbag of Holding is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Bookbag of Holding.  If not, see <http://www.gnu.org/licenses/>.

"""
Configuration loader for Bookbag of Holding.

This module provides functionality to load and save configuration
from INI files, with backward compatibility for the legacy CONFIG dict.
"""

import configparser
import os
from typing import Any, Dict, Optional, Tuple

from bookbagofholding.config.settings import (
    Configuration,
    ConfigError,
    HttpSettings,
    GeneralSettings,
    SearchSettings,
    DownloadSettings,
    UsenetSettings,
    TorrentSettings,
    LibrarySettings,
    PostProcessSettings,
    FileTypeSettings,
    NotificationSettings,
    ApiSettings,
    ImportSettings,
    DateSettings,
)


class ConfigLoader:
    """Loads and saves configuration from INI files.

    This class provides methods to:
    - Load configuration from a file into a Configuration object
    - Save configuration back to a file
    - Convert between legacy CONFIG dict and new Configuration
    """

    # Mapping of INI sections to dataclass fields
    SECTION_MAPPING = {
        'General': ['http', 'general', 'download', 'filetypes', 'dates', 'imports'],
        'SearchScan': ['search'],
        'LibraryScan': ['library'],
        'PostProcess': ['postprocess'],
        'SABnzbd': ['usenet'],
        'NZBGet': ['usenet'],
        'USENET': ['usenet'],
        'TORRENT': ['torrent'],
        'QBITTORRENT': ['torrent'],
        'TRANSMISSION': ['torrent'],
        'DELUGE': ['torrent'],
        'RTORRENT': ['torrent'],
        'UTORRENT': ['torrent'],
        'SYNOLOGY': ['torrent'],
        'Email': ['notifications'],
        'Pushover': ['notifications'],
        'Pushbullet': ['notifications'],
        'Telegram': ['notifications'],
        'Slack': ['notifications'],
        'Custom': ['notifications'],
        'API': ['api'],
    }

    def __init__(self, config_file: Optional[str] = None):
        """Initialize the config loader.

        Args:
            config_file: Path to the configuration file
        """
        self.config_file = config_file
        self._parser = configparser.ConfigParser()

    def load(self, config_file: Optional[str] = None) -> Configuration:
        """Load configuration from a file.

        Args:
            config_file: Path to config file (overrides constructor path)

        Returns:
            Configuration object with loaded values

        Raises:
            ConfigError: If file cannot be read
        """
        file_path = config_file or self.config_file
        if not file_path:
            raise ConfigError("No configuration file specified")

        config = Configuration()

        if os.path.isfile(file_path):
            try:
                self._parser.read(file_path)
            except Exception as e:
                raise ConfigError("Failed to read config file: %s" % str(e))

            # Load each section
            self._load_http_settings(config)
            self._load_general_settings(config)
            self._load_search_settings(config)
            self._load_download_settings(config)
            self._load_usenet_settings(config)
            self._load_torrent_settings(config)
            self._load_library_settings(config)
            self._load_postprocess_settings(config)
            self._load_filetype_settings(config)
            self._load_notification_settings(config)
            self._load_api_settings(config)
            self._load_import_settings(config)
            self._load_date_settings(config)

        return config

    def save(self, config: Configuration, config_file: Optional[str] = None) -> None:
        """Save configuration to a file.

        Args:
            config: Configuration object to save
            config_file: Path to config file (overrides constructor path)

        Raises:
            ConfigError: If file cannot be written
        """
        file_path = config_file or self.config_file
        if not file_path:
            raise ConfigError("No configuration file specified")

        # Ensure all sections exist
        self._ensure_section('General')
        self._ensure_section('SearchScan')
        self._ensure_section('LibraryScan')
        self._ensure_section('PostProcess')
        self._ensure_section('SABnzbd')
        self._ensure_section('NZBGet')
        self._ensure_section('USENET')
        self._ensure_section('TORRENT')
        self._ensure_section('QBITTORRENT')
        self._ensure_section('TRANSMISSION')
        self._ensure_section('DELUGE')
        self._ensure_section('RTORRENT')
        self._ensure_section('UTORRENT')
        self._ensure_section('SYNOLOGY')
        self._ensure_section('Email')
        self._ensure_section('Pushover')
        self._ensure_section('Pushbullet')
        self._ensure_section('Telegram')
        self._ensure_section('Slack')
        self._ensure_section('Custom')
        self._ensure_section('API')

        # Save each section
        self._save_http_settings(config)
        self._save_general_settings(config)
        self._save_search_settings(config)
        self._save_download_settings(config)
        self._save_usenet_settings(config)
        self._save_torrent_settings(config)
        self._save_library_settings(config)
        self._save_postprocess_settings(config)
        self._save_filetype_settings(config)
        self._save_notification_settings(config)
        self._save_api_settings(config)
        self._save_import_settings(config)
        self._save_date_settings(config)

        try:
            with open(file_path, 'w') as f:
                self._parser.write(f)
        except Exception as e:
            raise ConfigError("Failed to write config file: %s" % str(e))

    def from_legacy_dict(self, legacy_config: Dict[str, Any]) -> Configuration:
        """Create a Configuration from a legacy CONFIG dictionary.

        Args:
            legacy_config: The legacy CONFIG dictionary

        Returns:
            Configuration object
        """
        config = Configuration()

        # HTTP settings
        config.http.port = self._get_int(legacy_config, 'HTTP_PORT', 5299)
        config.http.host = legacy_config.get('HTTP_HOST', '0.0.0.0')
        config.http.user = legacy_config.get('HTTP_USER', '')
        config.http.password = legacy_config.get('HTTP_PASS', '')
        config.http.proxy = self._get_bool(legacy_config, 'HTTP_PROXY')
        config.http.root = legacy_config.get('HTTP_ROOT', '')
        config.http.timeout = self._get_int(legacy_config, 'HTTP_TIMEOUT', 30)
        config.http.ext_timeout = self._get_int(legacy_config, 'HTTP_EXT_TIMEOUT', 90)
        config.http.https_enabled = self._get_bool(legacy_config, 'HTTPS_ENABLED')
        config.http.https_cert = legacy_config.get('HTTPS_CERT', '')
        config.http.https_key = legacy_config.get('HTTPS_KEY', '')
        config.http.ssl_verify = self._get_bool(legacy_config, 'SSL_VERIFY')
        config.http.launch_browser = self._get_bool(legacy_config, 'LAUNCH_BROWSER', True)

        # General settings
        config.general.user_accounts = self._get_bool(legacy_config, 'USER_ACCOUNTS')
        config.general.single_user = self._get_bool(legacy_config, 'SINGLE_USER')
        config.general.admin_email = legacy_config.get('ADMIN_EMAIL', '')
        config.general.log_dir = legacy_config.get('LOGDIR', '')
        config.general.log_limit = self._get_int(legacy_config, 'LOGLIMIT', 500)
        config.general.log_files = self._get_int(legacy_config, 'LOGFILES', 10)
        config.general.log_size = self._get_int(legacy_config, 'LOGSIZE', 204800)
        config.general.log_level = self._get_int(legacy_config, 'LOGLEVEL', 1)
        config.general.api_enabled = self._get_bool(legacy_config, 'API_ENABLED')
        config.general.api_key = legacy_config.get('API_KEY', '')

        # Search settings
        config.search.book_interval = self._get_int(legacy_config, 'SEARCH_BOOKINTERVAL', 360)
        config.search.scan_interval = self._get_int(legacy_config, 'SCAN_INTERVAL', 10)
        config.search.rss_interval = self._get_int(legacy_config, 'SEARCHRSS_INTERVAL', 20)
        config.search.wishlist_interval = self._get_int(legacy_config, 'WISHLIST_INTERVAL', 24)
        config.search.match_ratio = self._get_int(legacy_config, 'MATCH_RATIO', 80)
        config.search.dload_ratio = self._get_int(legacy_config, 'DLOAD_RATIO', 90)

        # Download settings
        config.download.ebook_dir = legacy_config.get('EBOOK_DIR', '')
        config.download.audio_dir = legacy_config.get('AUDIO_DIR', '')
        config.download.download_dir = legacy_config.get('DOWNLOAD_DIR', '')
        config.download.alternate_dir = legacy_config.get('ALTERNATE_DIR', '')
        config.download.destination_copy = self._get_bool(legacy_config, 'DESTINATION_COPY')

        # Post-process settings
        config.postprocess.ebook_dest_folder = legacy_config.get('EBOOK_DEST_FOLDER', '$Author/$Title')
        config.postprocess.ebook_dest_file = legacy_config.get('EBOOK_DEST_FILE', '$Title - $Author')
        config.postprocess.audiobook_dest_file = legacy_config.get(
            'AUDIOBOOK_DEST_FILE', '$Author - $Title Part $Part of $Total'
        )

        # File type settings
        config.filetypes.ebook_type = legacy_config.get('EBOOK_TYPE', 'epub, mobi, pdf')
        config.filetypes.audiobook_type = legacy_config.get('AUDIOBOOK_TYPE', 'mp3')
        config.filetypes.reject_words = legacy_config.get('REJECT_WORDS', 'audiobook, mp3')

        # API settings
        config.api.book_api = legacy_config.get('BOOK_API', 'GoogleBooks')
        config.api.gb_api = legacy_config.get('GB_API', '')
        config.api.lt_devkey = legacy_config.get('LT_DEVKEY', '')

        return config

    def to_legacy_dict(self, config: Configuration) -> Dict[str, Any]:
        """Convert a Configuration to a legacy CONFIG dictionary.

        Args:
            config: Configuration object

        Returns:
            Dictionary in legacy CONFIG format
        """
        legacy = {}

        # HTTP settings
        legacy['HTTP_PORT'] = config.http.port
        legacy['HTTP_HOST'] = config.http.host
        legacy['HTTP_USER'] = config.http.user
        legacy['HTTP_PASS'] = config.http.password
        legacy['HTTP_PROXY'] = 1 if config.http.proxy else 0
        legacy['HTTP_ROOT'] = config.http.root
        legacy['HTTP_TIMEOUT'] = config.http.timeout
        legacy['HTTP_EXT_TIMEOUT'] = config.http.ext_timeout
        legacy['HTTPS_ENABLED'] = 1 if config.http.https_enabled else 0
        legacy['HTTPS_CERT'] = config.http.https_cert
        legacy['HTTPS_KEY'] = config.http.https_key
        legacy['SSL_VERIFY'] = 1 if config.http.ssl_verify else 0
        legacy['LAUNCH_BROWSER'] = 1 if config.http.launch_browser else 0

        # General settings
        legacy['USER_ACCOUNTS'] = 1 if config.general.user_accounts else 0
        legacy['SINGLE_USER'] = 1 if config.general.single_user else 0
        legacy['ADMIN_EMAIL'] = config.general.admin_email
        legacy['LOGDIR'] = config.general.log_dir
        legacy['LOGLIMIT'] = config.general.log_limit
        legacy['LOGFILES'] = config.general.log_files
        legacy['LOGSIZE'] = config.general.log_size
        legacy['LOGLEVEL'] = config.general.log_level
        legacy['API_ENABLED'] = 1 if config.general.api_enabled else 0
        legacy['API_KEY'] = config.general.api_key

        # Search settings
        legacy['SEARCH_BOOKINTERVAL'] = config.search.book_interval
        legacy['SCAN_INTERVAL'] = config.search.scan_interval
        legacy['SEARCHRSS_INTERVAL'] = config.search.rss_interval
        legacy['WISHLIST_INTERVAL'] = config.search.wishlist_interval
        legacy['MATCH_RATIO'] = config.search.match_ratio
        legacy['DLOAD_RATIO'] = config.search.dload_ratio

        # Download settings
        legacy['EBOOK_DIR'] = config.download.ebook_dir
        legacy['AUDIO_DIR'] = config.download.audio_dir
        legacy['DOWNLOAD_DIR'] = config.download.download_dir
        legacy['ALTERNATE_DIR'] = config.download.alternate_dir
        legacy['DESTINATION_COPY'] = 1 if config.download.destination_copy else 0

        # Post-process settings
        legacy['EBOOK_DEST_FOLDER'] = config.postprocess.ebook_dest_folder
        legacy['EBOOK_DEST_FILE'] = config.postprocess.ebook_dest_file
        legacy['AUDIOBOOK_DEST_FILE'] = config.postprocess.audiobook_dest_file

        # File type settings
        legacy['EBOOK_TYPE'] = config.filetypes.ebook_type
        legacy['AUDIOBOOK_TYPE'] = config.filetypes.audiobook_type
        legacy['REJECT_WORDS'] = config.filetypes.reject_words

        # API settings
        legacy['BOOK_API'] = config.api.book_api
        legacy['GB_API'] = config.api.gb_api
        legacy['LT_DEVKEY'] = config.api.lt_devkey

        return legacy

    def _ensure_section(self, section: str) -> None:
        """Ensure a section exists in the parser."""
        if not self._parser.has_section(section):
            self._parser.add_section(section)

    def _get_setting(self, section: str, key: str, default: Any = None) -> Any:
        """Get a setting from the parser."""
        try:
            return self._parser.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    def _get_int(self, source: Dict, key: str, default: int = 0) -> int:
        """Get an integer value from a dictionary."""
        value = source.get(key, default)
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _get_bool(self, source: Dict, key: str, default: bool = False) -> bool:
        """Get a boolean value from a dictionary."""
        value = source.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return default

    def _load_http_settings(self, config: Configuration) -> None:
        """Load HTTP settings from parser."""
        config.http.port = int(self._get_setting('General', 'http_port', 5299) or 5299)
        config.http.host = self._get_setting('General', 'http_host', '0.0.0.0') or '0.0.0.0'
        config.http.user = self._get_setting('General', 'http_user', '') or ''
        config.http.password = self._get_setting('General', 'http_pass', '') or ''
        config.http.root = self._get_setting('General', 'http_root', '') or ''
        config.http.timeout = int(self._get_setting('General', 'http_timeout', 30) or 30)
        config.http.bookstrap_theme = self._get_setting('General', 'bookstrap_theme', 'slate') or 'slate'

    def _load_general_settings(self, config: Configuration) -> None:
        """Load general settings from parser."""
        config.general.log_dir = self._get_setting('General', 'logdir', '') or ''
        config.general.log_level = int(self._get_setting('General', 'loglevel', 1) or 1)
        config.general.log_limit = int(self._get_setting('General', 'loglimit', 500) or 500)
        config.general.log_files = int(self._get_setting('General', 'logfiles', 10) or 10)
        config.general.log_size = int(self._get_setting('General', 'logsize', 204800) or 204800)

    def _load_search_settings(self, config: Configuration) -> None:
        """Load search settings from parser."""
        config.search.book_interval = int(self._get_setting('SearchScan', 'search_bookinterval', 360) or 360)
        config.search.scan_interval = int(self._get_setting('SearchScan', 'scan_interval', 10) or 10)
        config.search.match_ratio = int(self._get_setting('General', 'match_ratio', 80) or 80)
        config.search.dload_ratio = int(self._get_setting('General', 'dload_ratio', 90) or 90)

    def _load_download_settings(self, config: Configuration) -> None:
        """Load download settings from parser."""
        config.download.ebook_dir = self._get_setting('General', 'ebook_dir', '') or ''
        config.download.audio_dir = self._get_setting('General', 'audio_dir', '') or ''
        config.download.download_dir = self._get_setting('General', 'download_dir', '') or ''

    def _load_usenet_settings(self, config: Configuration) -> None:
        """Load usenet settings from parser."""
        config.usenet.sab_host = self._get_setting('SABnzbd', 'sab_host', '') or ''
        config.usenet.sab_port = int(self._get_setting('SABnzbd', 'sab_port', 0) or 0)
        config.usenet.sab_api = self._get_setting('SABnzbd', 'sab_api', '') or ''
        config.usenet.sab_cat = self._get_setting('SABnzbd', 'sab_cat', '') or ''

    def _load_torrent_settings(self, config: Configuration) -> None:
        """Load torrent settings from parser."""
        config.torrent.qbittorrent_host = self._get_setting('QBITTORRENT', 'qbittorrent_host', '') or ''
        config.torrent.qbittorrent_port = int(self._get_setting('QBITTORRENT', 'qbittorrent_port', 0) or 0)
        config.torrent.transmission_host = self._get_setting('TRANSMISSION', 'transmission_host', '') or ''
        config.torrent.transmission_port = int(self._get_setting('TRANSMISSION', 'transmission_port', 0) or 0)

    def _load_library_settings(self, config: Configuration) -> None:
        """Load library settings from parser."""
        config.library.add_author = self._get_setting('LibraryScan', 'add_author', '1') == '1'
        config.library.add_series = self._get_setting('LibraryScan', 'add_series', '1') == '1'
        config.library.newbook_status = self._get_setting('LibraryScan', 'newbook_status', 'Skipped') or 'Skipped'

    def _load_postprocess_settings(self, config: Configuration) -> None:
        """Load post-process settings from parser."""
        config.postprocess.ebook_dest_folder = self._get_setting(
            'PostProcess', 'ebook_dest_folder', '$Author/$Title'
        ) or '$Author/$Title'
        config.postprocess.ebook_dest_file = self._get_setting(
            'PostProcess', 'ebook_dest_file', '$Title - $Author'
        ) or '$Title - $Author'

    def _load_filetype_settings(self, config: Configuration) -> None:
        """Load file type settings from parser."""
        config.filetypes.ebook_type = self._get_setting('General', 'ebook_type', 'epub, mobi, pdf') or 'epub, mobi, pdf'
        config.filetypes.audiobook_type = self._get_setting('General', 'audiobook_type', 'mp3') or 'mp3'

    def _load_notification_settings(self, config: Configuration) -> None:
        """Load notification settings from parser."""
        config.notifications.use_email = self._get_setting('Email', 'use_email', '0') == '1'
        config.notifications.email_smtp_server = self._get_setting('Email', 'email_smtp_server', '') or ''

    def _load_api_settings(self, config: Configuration) -> None:
        """Load API settings from parser."""
        config.api.book_api = self._get_setting('API', 'book_api', 'GoogleBooks') or 'GoogleBooks'
        config.api.gb_api = self._get_setting('API', 'gb_api', '') or ''

    def _load_import_settings(self, config: Configuration) -> None:
        """Load import settings from parser."""
        config.imports.preflang = self._get_setting('General', 'imp_preflang', 'en, eng, en-US, en-GB') or 'en, eng, en-US, en-GB'

    def _load_date_settings(self, config: Configuration) -> None:
        """Load date settings from parser."""
        config.dates.date_format = self._get_setting('General', 'date_format', '$Y-$m-$d') or '$Y-$m-$d'
        config.dates.iss_format = self._get_setting('General', 'iss_format', '$Y-$m-$d') or '$Y-$m-$d'

    def _save_http_settings(self, config: Configuration) -> None:
        """Save HTTP settings to parser."""
        self._parser.set('General', 'http_port', str(config.http.port))
        self._parser.set('General', 'http_host', config.http.host)
        self._parser.set('General', 'http_user', config.http.user)
        self._parser.set('General', 'http_pass', config.http.password)
        self._parser.set('General', 'http_root', config.http.root)
        self._parser.set('General', 'http_timeout', str(config.http.timeout))

    def _save_general_settings(self, config: Configuration) -> None:
        """Save general settings to parser."""
        self._parser.set('General', 'logdir', config.general.log_dir)
        self._parser.set('General', 'loglevel', str(config.general.log_level))

    def _save_search_settings(self, config: Configuration) -> None:
        """Save search settings to parser."""
        self._parser.set('SearchScan', 'search_bookinterval', str(config.search.book_interval))

    def _save_download_settings(self, config: Configuration) -> None:
        """Save download settings to parser."""
        self._parser.set('General', 'ebook_dir', config.download.ebook_dir)
        self._parser.set('General', 'audio_dir', config.download.audio_dir)
        self._parser.set('General', 'download_dir', config.download.download_dir)

    def _save_usenet_settings(self, config: Configuration) -> None:
        """Save usenet settings to parser."""
        self._parser.set('SABnzbd', 'sab_host', config.usenet.sab_host)
        self._parser.set('SABnzbd', 'sab_port', str(config.usenet.sab_port))

    def _save_torrent_settings(self, config: Configuration) -> None:
        """Save torrent settings to parser."""
        self._parser.set('QBITTORRENT', 'qbittorrent_host', config.torrent.qbittorrent_host)

    def _save_library_settings(self, config: Configuration) -> None:
        """Save library settings to parser."""
        self._parser.set('LibraryScan', 'add_author', '1' if config.library.add_author else '0')
        self._parser.set('LibraryScan', 'add_series', '1' if config.library.add_series else '0')

    def _save_postprocess_settings(self, config: Configuration) -> None:
        """Save post-process settings to parser."""
        self._parser.set('PostProcess', 'ebook_dest_folder', config.postprocess.ebook_dest_folder)
        self._parser.set('PostProcess', 'ebook_dest_file', config.postprocess.ebook_dest_file)

    def _save_filetype_settings(self, config: Configuration) -> None:
        """Save file type settings to parser."""
        self._parser.set('General', 'ebook_type', config.filetypes.ebook_type)
        self._parser.set('General', 'audiobook_type', config.filetypes.audiobook_type)

    def _save_notification_settings(self, config: Configuration) -> None:
        """Save notification settings to parser."""
        self._parser.set('Email', 'use_email', '1' if config.notifications.use_email else '0')

    def _save_api_settings(self, config: Configuration) -> None:
        """Save API settings to parser."""
        self._parser.set('API', 'book_api', config.api.book_api)
        self._parser.set('API', 'gb_api', config.api.gb_api)

    def _save_import_settings(self, config: Configuration) -> None:
        """Save import settings to parser."""
        self._parser.set('General', 'imp_preflang', config.imports.preflang)

    def _save_date_settings(self, config: Configuration) -> None:
        """Save date settings to parser."""
        self._parser.set('General', 'date_format', config.dates.date_format)
