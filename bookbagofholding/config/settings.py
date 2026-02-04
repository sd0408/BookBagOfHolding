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
Type-safe configuration settings for Bookbag of Holding.

This module provides dataclass-based configuration that replaces
the mutable global CONFIG dictionary with typed settings objects.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


class ConfigError(Exception):
    """Exception raised for configuration errors."""
    pass


@dataclass
class HttpSettings:
    """HTTP server settings."""
    port: int = 5299
    host: str = '0.0.0.0'
    user: str = ''
    password: str = ''
    proxy: bool = False
    root: str = ''
    timeout: int = 30
    ext_timeout: int = 90

    # HTTPS settings
    https_enabled: bool = False
    https_cert: str = ''
    https_key: str = ''
    ssl_verify: bool = False

    # UI settings
    bookstrap_theme: str = 'slate'
    launch_browser: bool = True

    def validate(self) -> None:
        """Validate HTTP settings."""
        if self.port < 21 or self.port > 65535:
            raise ConfigError("HTTP port must be between 21 and 65535")
        if self.timeout < 1:
            raise ConfigError("HTTP timeout must be at least 1 second")


@dataclass
class GeneralSettings:
    """General application settings."""
    # User account settings
    user_accounts: bool = False
    single_user: bool = False
    admin_email: str = ''

    # Logging settings
    log_dir: str = ''
    log_limit: int = 500
    log_files: int = 10
    log_size: int = 204800
    log_level: int = 1

    # Display settings
    wall_columns: int = 6
    display_length: int = 10
    hist_refresh: int = 1000

    # Permissions
    file_perm: str = '0o644'
    dir_perm: str = '0o755'

    # UI tabs
    audio_tab: bool = True
    toggles: bool = True

    # Images
    author_img: bool = True
    book_img: bool = True

    # Sorting
    sort_definite: bool = False
    sort_surname: bool = False

    # API
    api_enabled: bool = False
    api_key: str = ''

    # Proxy
    proxy_host: str = ''
    proxy_type: str = ''
    proxy_local: str = ''

    # System
    sys_encoding: str = ''
    blocklist_timer: int = 3600
    cache_age: int = 30
    task_age: int = 2


@dataclass
class SearchSettings:
    """Search and matching settings."""
    # Intervals (in hours)
    book_interval: int = 360
    scan_interval: int = 10
    rss_interval: int = 20
    wishlist_interval: int = 24

    # Match ratios
    match_ratio: int = 80
    dload_ratio: int = 90
    name_ratio: int = 90
    name_partial: int = 95
    name_partname: int = 95

    # Pagination
    max_pages: int = 0
    max_bookpages: int = 0
    max_wall: int = 0

    # Options
    delay_search: bool = False


@dataclass
class DownloadSettings:
    """Download directory settings."""
    ebook_dir: str = ''
    audio_dir: str = ''
    download_dir: str = ''
    alternate_dir: str = ''
    destination_copy: bool = False
    delete_csv: bool = False


@dataclass
class UsenetSettings:
    """Usenet download settings."""
    # SABnzbd
    sab_host: str = ''
    sab_port: int = 0
    sab_subdir: str = ''
    sab_user: str = ''
    sab_pass: str = ''
    sab_api: str = ''
    sab_cat: str = ''
    use_sabnzbd: bool = False

    # NZBGet
    nzbget_host: str = ''
    nzbget_port: int = 0
    nzbget_user: str = ''
    nzbget_pass: str = ''
    nzbget_category: str = ''
    nzbget_priority: int = 0
    use_nzbget: bool = False

    # General
    use_synology_nzb: bool = False
    use_blackhole: bool = False
    blackhole_dir: str = ''
    retention: int = 0


@dataclass
class TorrentSettings:
    """Torrent download settings."""
    # General torrent settings
    use_blackhole: bool = False
    convert_magnet: bool = False
    number_of_seeders: int = 10
    keep_seeding: bool = True
    seed_wait: bool = True
    prefer_magnet: bool = True
    torrent_dir: str = ''

    # qBittorrent
    qbittorrent_host: str = ''
    qbittorrent_port: int = 0
    qbittorrent_user: str = ''
    qbittorrent_pass: str = ''
    qbittorrent_label: str = ''
    qbittorrent_dir: str = ''
    use_qbittorrent: bool = False

    # Transmission
    transmission_host: str = ''
    transmission_base: str = ''
    transmission_port: int = 0
    transmission_user: str = ''
    transmission_pass: str = ''
    transmission_dir: str = ''
    use_transmission: bool = False

    # Deluge
    deluge_host: str = ''
    deluge_base: str = ''
    deluge_port: int = 0
    deluge_user: str = ''
    deluge_pass: str = ''
    deluge_label: str = ''
    deluge_dir: str = ''
    deluge_cert: str = ''
    use_deluge: bool = False

    # rTorrent
    rtorrent_host: str = ''
    rtorrent_user: str = ''
    rtorrent_pass: str = ''
    rtorrent_label: str = ''
    rtorrent_dir: str = ''
    use_rtorrent: bool = False

    # uTorrent
    utorrent_host: str = ''
    utorrent_port: int = 0
    utorrent_user: str = ''
    utorrent_pass: str = ''
    utorrent_label: str = ''
    use_utorrent: bool = False

    # Synology
    synology_host: str = ''
    synology_port: int = 0
    synology_user: str = ''
    synology_pass: str = ''
    synology_dir: str = 'Multimedia/Download'
    use_synology: bool = False


@dataclass
class LibrarySettings:
    """Library scanning settings."""
    full_scan: bool = False
    add_author: bool = True
    add_series: bool = True

    # Status for new items
    notfound_status: str = 'Skipped'
    found_status: str = 'Open'
    newbook_status: str = 'Skipped'
    newaudio_status: str = 'Skipped'
    newauthor_status: str = 'Skipped'
    newauthor_audio: str = 'Skipped'
    newauthor_books: bool = False

    # Filtering
    no_future: bool = False
    no_pubdate: bool = False
    no_isbn: bool = False
    no_sets: bool = False
    no_lang: bool = False
    isbn_lookup: bool = True
    imp_ignore: bool = False
    imp_googleimage: bool = False


@dataclass
class PostProcessSettings:
    """Post-processing settings."""
    # eBook destinations
    ebook_dest_folder: str = '$Author/$Title'
    ebook_dest_file: str = '$Title - $Author'

    # Audiobook destinations
    audiobook_dest_file: str = '$Author - $Title Part $Part of $Total'

    # Options
    one_format: bool = False


@dataclass
class FileTypeSettings:
    """File type settings."""
    ebook_type: str = 'epub, mobi, pdf'
    audiobook_type: str = 'mp3'

    # Reject words
    reject_words: str = 'audiobook, mp3'
    reject_audio: str = 'epub, mobi'

    # Size limits
    reject_maxsize: int = 0
    reject_minsize: int = 0
    reject_maxaudio: int = 0
    reject_minaudio: int = 0

    # Extensions
    skipped_ext: str = 'fail, part, bts, !ut, torrent, magnet, nzb, unpack'
    banned_ext: str = 'avi, mp4, mov, iso, m4v'


@dataclass
class NotificationSettings:
    """Notification service settings."""
    # Email
    use_email: bool = False
    email_notify_onsnatch: bool = False
    email_notify_ondownload: bool = False
    email_sendfile_ondownload: bool = False
    email_from: str = ''
    email_to: str = ''
    email_ssl: bool = False
    email_smtp_server: str = ''
    email_smtp_port: int = 25
    email_tls: bool = False
    email_smtp_user: str = ''
    email_smtp_password: str = ''

    # Pushover
    use_pushover: bool = False
    pushover_onsnatch: bool = False
    pushover_ondownload: bool = False
    pushover_keys: str = ''
    pushover_apitoken: str = ''
    pushover_priority: int = 0
    pushover_device: str = ''

    # Pushbullet
    use_pushbullet: bool = False
    pushbullet_notify_onsnatch: bool = False
    pushbullet_notify_ondownload: bool = False
    pushbullet_token: str = ''
    pushbullet_deviceid: str = ''

    # Telegram
    use_telegram: bool = False
    telegram_token: str = ''
    telegram_userid: str = ''
    telegram_onsnatch: bool = False
    telegram_ondownload: bool = False

    # Slack
    use_slack: bool = False
    slack_notify_onsnatch: bool = False
    slack_notify_ondownload: bool = False
    slack_token: str = ''
    slack_url: str = 'https://hooks.slack.com/services/'

    # Custom
    use_custom: bool = False
    custom_notify_onsnatch: bool = False
    custom_notify_ondownload: bool = False
    custom_script: str = ''


@dataclass
class ApiSettings:
    """API key settings."""
    book_api: str = 'GoogleBooks'
    lt_devkey: str = ''
    gb_api: str = ''


@dataclass
class ImportSettings:
    """Import settings."""
    preflang: str = 'en, eng, en-US, en-GB'
    monthlang: str = ''
    autoadd: str = ''
    autoadd_copy: bool = True
    autoadd_bookonly: bool = False
    autosearch: bool = False

    # Calibre
    calibredb: str = ''
    calibre_use_server: bool = False
    calibre_server: str = ''
    calibre_user: str = ''
    calibre_pass: str = ''
    calibre_rename: bool = False

    # Options
    singlebook: bool = False
    rename: bool = False
    convert: str = ''
    preprocess: str = ''

    # Blacklist
    blacklist_failed: bool = True
    blacklist_processed: bool = False


@dataclass
class DateSettings:
    """Date formatting settings."""
    iss_format: str = '$Y-$m-$d'
    date_format: str = '$Y-$m-$d'


@dataclass
class Configuration:
    """Main configuration container.

    This class aggregates all configuration sections and provides
    methods for loading, saving, and accessing configuration.
    """
    http: HttpSettings = field(default_factory=HttpSettings)
    general: GeneralSettings = field(default_factory=GeneralSettings)
    search: SearchSettings = field(default_factory=SearchSettings)
    download: DownloadSettings = field(default_factory=DownloadSettings)
    usenet: UsenetSettings = field(default_factory=UsenetSettings)
    torrent: TorrentSettings = field(default_factory=TorrentSettings)
    library: LibrarySettings = field(default_factory=LibrarySettings)
    postprocess: PostProcessSettings = field(default_factory=PostProcessSettings)
    filetypes: FileTypeSettings = field(default_factory=FileTypeSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    api: ApiSettings = field(default_factory=ApiSettings)
    imports: ImportSettings = field(default_factory=ImportSettings)
    dates: DateSettings = field(default_factory=DateSettings)

    def validate(self) -> None:
        """Validate all configuration settings.

        Raises:
            ConfigError: If any setting is invalid
        """
        self.http.validate()

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to a flat dictionary.

        This provides backward compatibility with the legacy CONFIG dict.

        Returns:
            Dictionary with all settings in flat format
        """
        return asdict(self)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key.

        This method provides backward compatibility with CONFIG dict access.

        Args:
            key: The configuration key (e.g., 'HTTP_PORT', 'SAB_HOST')
            default: Default value if key not found

        Returns:
            The configuration value
        """
        # Map legacy keys to new structure
        key_mapping = self._get_key_mapping()
        if key.upper() in key_mapping:
            section, attr = key_mapping[key.upper()]
            section_obj = getattr(self, section, None)
            if section_obj:
                return getattr(section_obj, attr, default)
        return default

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value by key.

        Args:
            key: The configuration key
            value: The value to set

        Raises:
            ConfigError: If key is not valid
        """
        key_mapping = self._get_key_mapping()
        if key.upper() in key_mapping:
            section, attr = key_mapping[key.upper()]
            section_obj = getattr(self, section, None)
            if section_obj:
                setattr(section_obj, attr, value)
        else:
            raise ConfigError("Unknown configuration key: %s" % key)

    def _get_key_mapping(self) -> Dict[str, tuple]:
        """Get mapping from legacy keys to new structure.

        Returns:
            Dictionary mapping KEY_NAME -> (section, attribute)
        """
        return {
            # HTTP settings
            'HTTP_PORT': ('http', 'port'),
            'HTTP_HOST': ('http', 'host'),
            'HTTP_USER': ('http', 'user'),
            'HTTP_PASS': ('http', 'password'),
            'HTTP_PROXY': ('http', 'proxy'),
            'HTTP_ROOT': ('http', 'root'),
            'HTTP_TIMEOUT': ('http', 'timeout'),
            'HTTP_EXT_TIMEOUT': ('http', 'ext_timeout'),
            'HTTPS_ENABLED': ('http', 'https_enabled'),
            'HTTPS_CERT': ('http', 'https_cert'),
            'HTTPS_KEY': ('http', 'https_key'),
            'SSL_VERIFY': ('http', 'ssl_verify'),
            'LAUNCH_BROWSER': ('http', 'launch_browser'),

            # General settings
            'USER_ACCOUNTS': ('general', 'user_accounts'),
            'SINGLE_USER': ('general', 'single_user'),
            'ADMIN_EMAIL': ('general', 'admin_email'),
            'LOGDIR': ('general', 'log_dir'),
            'LOGLIMIT': ('general', 'log_limit'),
            'LOGFILES': ('general', 'log_files'),
            'LOGSIZE': ('general', 'log_size'),
            'LOGLEVEL': ('general', 'log_level'),
            'WALL_COLUMNS': ('general', 'wall_columns'),
            'DISPLAYLENGTH': ('general', 'display_length'),
            'HIST_REFRESH': ('general', 'hist_refresh'),
            'FILE_PERM': ('general', 'file_perm'),
            'DIR_PERM': ('general', 'dir_perm'),
            'API_ENABLED': ('general', 'api_enabled'),
            'API_KEY': ('general', 'api_key'),

            # Search settings
            'SEARCH_BOOKINTERVAL': ('search', 'book_interval'),
            'SCAN_INTERVAL': ('search', 'scan_interval'),
            'SEARCHRSS_INTERVAL': ('search', 'rss_interval'),
            'WISHLIST_INTERVAL': ('search', 'wishlist_interval'),
            'MATCH_RATIO': ('search', 'match_ratio'),
            'DLOAD_RATIO': ('search', 'dload_ratio'),

            # Download settings
            'EBOOK_DIR': ('download', 'ebook_dir'),
            'AUDIO_DIR': ('download', 'audio_dir'),
            'DOWNLOAD_DIR': ('download', 'download_dir'),
            'ALTERNATE_DIR': ('download', 'alternate_dir'),
            'DESTINATION_COPY': ('download', 'destination_copy'),

            # Post-process settings
            'EBOOK_DEST_FOLDER': ('postprocess', 'ebook_dest_folder'),
            'EBOOK_DEST_FILE': ('postprocess', 'ebook_dest_file'),
            'AUDIOBOOK_DEST_FILE': ('postprocess', 'audiobook_dest_file'),

            # File type settings
            'EBOOK_TYPE': ('filetypes', 'ebook_type'),
            'AUDIOBOOK_TYPE': ('filetypes', 'audiobook_type'),
            'REJECT_WORDS': ('filetypes', 'reject_words'),
            'REJECT_AUDIO': ('filetypes', 'reject_audio'),

            # API settings
            'BOOK_API': ('api', 'book_api'),
            'GB_API': ('api', 'gb_api'),
            'LT_DEVKEY': ('api', 'lt_devkey'),
        }
