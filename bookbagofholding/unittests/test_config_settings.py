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

"""Tests for the type-safe configuration settings."""

import os
import tempfile
import unittest

from bookbagofholding.config.settings import (
    Configuration,
    HttpSettings,
    GeneralSettings,
    SearchSettings,
    DownloadSettings,
    PostProcessSettings,
    FileTypeSettings,
    ConfigError,
)
from bookbagofholding.config.loader import ConfigLoader


class TestHttpSettings(unittest.TestCase):
    """Test cases for HttpSettings."""

    def test_default_values(self):
        """HttpSettings should have correct defaults."""
        settings = HttpSettings()
        self.assertEqual(settings.port, 5299)
        self.assertEqual(settings.host, '0.0.0.0')
        self.assertEqual(settings.timeout, 30)
        self.assertFalse(settings.https_enabled)

    def test_validate_valid_port(self):
        """validate should pass for valid port."""
        settings = HttpSettings(port=8080)
        settings.validate()  # Should not raise

    def test_validate_invalid_port_low(self):
        """validate should raise for port < 21."""
        settings = HttpSettings(port=20)
        with self.assertRaises(ConfigError):
            settings.validate()

    def test_validate_invalid_port_high(self):
        """validate should raise for port > 65535."""
        settings = HttpSettings(port=70000)
        with self.assertRaises(ConfigError):
            settings.validate()

    def test_validate_invalid_timeout(self):
        """validate should raise for timeout < 1."""
        settings = HttpSettings(timeout=0)
        with self.assertRaises(ConfigError):
            settings.validate()


class TestGeneralSettings(unittest.TestCase):
    """Test cases for GeneralSettings."""

    def test_default_values(self):
        """GeneralSettings should have correct defaults."""
        settings = GeneralSettings()
        self.assertFalse(settings.user_accounts)
        self.assertEqual(settings.log_level, 1)
        self.assertEqual(settings.log_size, 204800)
        self.assertEqual(settings.file_perm, '0o644')
        self.assertEqual(settings.dir_perm, '0o755')
        self.assertTrue(settings.author_img)


class TestSearchSettings(unittest.TestCase):
    """Test cases for SearchSettings."""

    def test_default_values(self):
        """SearchSettings should have correct defaults."""
        settings = SearchSettings()
        self.assertEqual(settings.book_interval, 360)
        self.assertEqual(settings.match_ratio, 80)
        self.assertEqual(settings.dload_ratio, 90)


class TestPostProcessSettings(unittest.TestCase):
    """Test cases for PostProcessSettings."""

    def test_default_values(self):
        """PostProcessSettings should have correct defaults."""
        settings = PostProcessSettings()
        self.assertEqual(settings.ebook_dest_folder, '$Author/$Title')
        self.assertEqual(settings.ebook_dest_file, '$Title - $Author')


class TestFileTypeSettings(unittest.TestCase):
    """Test cases for FileTypeSettings."""

    def test_default_values(self):
        """FileTypeSettings should have correct defaults."""
        settings = FileTypeSettings()
        self.assertEqual(settings.ebook_type, 'epub, mobi, pdf')
        self.assertEqual(settings.audiobook_type, 'mp3')
        self.assertEqual(settings.reject_words, 'audiobook, mp3')


class TestConfiguration(unittest.TestCase):
    """Test cases for the main Configuration class."""

    def test_default_initialization(self):
        """Configuration should initialize with all sections."""
        config = Configuration()
        self.assertIsInstance(config.http, HttpSettings)
        self.assertIsInstance(config.general, GeneralSettings)
        self.assertIsInstance(config.search, SearchSettings)
        self.assertIsInstance(config.download, DownloadSettings)
        self.assertIsInstance(config.postprocess, PostProcessSettings)
        self.assertIsInstance(config.filetypes, FileTypeSettings)

    def test_validate(self):
        """validate should call validation on all sections."""
        config = Configuration()
        config.validate()  # Should not raise with defaults

    def test_get_known_key(self):
        """get should return value for known key."""
        config = Configuration()
        config.http.port = 8080

        value = config.get('HTTP_PORT')
        self.assertEqual(value, 8080)

    def test_get_unknown_key(self):
        """get should return default for unknown key."""
        config = Configuration()

        value = config.get('UNKNOWN_KEY', 'default')
        self.assertEqual(value, 'default')

    def test_set_known_key(self):
        """set should update value for known key."""
        config = Configuration()
        config.set('HTTP_PORT', 9000)

        self.assertEqual(config.http.port, 9000)

    def test_set_unknown_key(self):
        """set should raise ConfigError for unknown key."""
        config = Configuration()

        with self.assertRaises(ConfigError):
            config.set('UNKNOWN_KEY', 'value')

    def test_to_dict(self):
        """to_dict should return nested dictionary."""
        config = Configuration()
        config.http.port = 8080

        result = config.to_dict()
        self.assertIsInstance(result, dict)
        self.assertIn('http', result)
        self.assertEqual(result['http']['port'], 8080)


class TestConfigLoader(unittest.TestCase):
    """Test cases for ConfigLoader."""

    def test_from_legacy_dict(self):
        """from_legacy_dict should convert legacy CONFIG."""
        legacy = {
            'HTTP_PORT': 8080,
            'HTTP_HOST': 'localhost',
            'LOGLEVEL': 2,
            'EBOOK_DIR': '/path/to/ebooks',
            'MATCH_RATIO': 85,
        }

        loader = ConfigLoader()
        config = loader.from_legacy_dict(legacy)

        self.assertEqual(config.http.port, 8080)
        self.assertEqual(config.http.host, 'localhost')
        self.assertEqual(config.general.log_level, 2)
        self.assertEqual(config.download.ebook_dir, '/path/to/ebooks')
        self.assertEqual(config.search.match_ratio, 85)

    def test_to_legacy_dict(self):
        """to_legacy_dict should convert to legacy format."""
        config = Configuration()
        config.http.port = 9000
        config.general.log_level = 3
        config.download.ebook_dir = '/books'

        loader = ConfigLoader()
        legacy = loader.to_legacy_dict(config)

        self.assertEqual(legacy['HTTP_PORT'], 9000)
        self.assertEqual(legacy['LOGLEVEL'], 3)
        self.assertEqual(legacy['EBOOK_DIR'], '/books')

    def test_roundtrip_legacy(self):
        """Converting to/from legacy should preserve values."""
        original = {
            'HTTP_PORT': 5299,
            'HTTP_HOST': '0.0.0.0',
            'LOGLEVEL': 1,
            'MATCH_RATIO': 80,
            'EBOOK_TYPE': 'epub, mobi, pdf',
        }

        loader = ConfigLoader()
        config = loader.from_legacy_dict(original)
        result = loader.to_legacy_dict(config)

        self.assertEqual(result['HTTP_PORT'], original['HTTP_PORT'])
        self.assertEqual(result['HTTP_HOST'], original['HTTP_HOST'])
        self.assertEqual(result['LOGLEVEL'], original['LOGLEVEL'])
        self.assertEqual(result['MATCH_RATIO'], original['MATCH_RATIO'])
        self.assertEqual(result['EBOOK_TYPE'], original['EBOOK_TYPE'])

    def test_load_nonexistent_file(self):
        """load should return defaults for nonexistent file."""
        loader = ConfigLoader('/nonexistent/path/config.ini')
        config = loader.load()

        # Should have defaults
        self.assertEqual(config.http.port, 5299)

    def test_save_and_load(self):
        """save should write config that can be loaded."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            config_path = f.name

        try:
            # Create and save config
            config = Configuration()
            config.http.port = 7777
            config.general.log_level = 5

            loader = ConfigLoader(config_path)
            loader.save(config)

            # Load it back
            loader2 = ConfigLoader(config_path)
            loaded = loader2.load()

            self.assertEqual(loaded.http.port, 7777)
            self.assertEqual(loaded.general.log_level, 5)

        finally:
            if os.path.exists(config_path):
                os.unlink(config_path)


class TestConfigLoaderIntegration(unittest.TestCase):
    """Integration tests for ConfigLoader."""

    def test_load_empty_file(self):
        """load should handle empty config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            config_path = f.name
            f.write('')

        try:
            loader = ConfigLoader(config_path)
            config = loader.load()

            # Should have defaults
            self.assertEqual(config.http.port, 5299)

        finally:
            if os.path.exists(config_path):
                os.unlink(config_path)

    def test_load_partial_config(self):
        """load should handle partial config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            config_path = f.name
            f.write('[General]\n')
            f.write('http_port = 8888\n')

        try:
            loader = ConfigLoader(config_path)
            config = loader.load()

            # Should have the specified value
            self.assertEqual(config.http.port, 8888)

        finally:
            if os.path.exists(config_path):
                os.unlink(config_path)


if __name__ == '__main__':
    unittest.main()
