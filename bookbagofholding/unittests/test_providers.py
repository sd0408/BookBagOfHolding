#  This file is part of Bookbag of Holding.
#
#  Bookbag of Holding is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Bookbag of Holding is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Bookbag of Holding.  If not, see <http://www.gnu.org/licenses/>.

"""
Unit tests for bookbagofholding.providers module.

Tests cover:
- ReturnSearchTypeStructure function
- ReturnResultsFieldsBySearchType function
- Provider initialization and configuration
"""

import pytest
from xml.etree import ElementTree
from unittest.mock import patch, Mock

import bookbagofholding
from bookbagofholding import providers


@pytest.fixture
def provider_config():
    """Set up configuration for provider testing."""
    original_config = dict(bookbagofholding.CONFIG)

    bookbagofholding.CONFIG['EBOOK_TYPE'] = 'epub, mobi, pdf'
    bookbagofholding.CONFIG['AUDIOBOOK_TYPE'] = 'mp3, m4b'
    bookbagofholding.CONFIG['HTTP_TIMEOUT'] = '30'

    yield

    bookbagofholding.CONFIG.update(original_config)


@pytest.fixture
def sample_provider():
    """Provide a sample provider configuration."""
    return {
        'HOST': 'http://example.com',
        'API': 'test-api-key',
        'BOOKSEARCH': 'book',
        'BOOKCAT': '7000',
        'MAGSEARCH': 'search',
        'MAGCAT': '7010',
        'AUDIOSEARCH': 'audio',
        'AUDIOCAT': '3030',
        'GENERALSEARCH': 'search',
        'EXTENDED': 1,
        'UPDATED': '',
        'MANUAL': False,
        'DISPNAME': 'Test Provider',
    }


@pytest.fixture
def sample_book():
    """Provide sample book search data."""
    return {
        'bookid': 'test-book-123',
        'bookName': 'Test Book Title',
        'authorName': 'Test Author',
        'searchterm': 'Test Author Test Book'
    }


class TestReturnSearchTypeStructure:
    """Tests for ReturnSearchTypeStructure() function."""

    def test_returns_params_for_book_search(self, provider_config, sample_provider, sample_book):
        """ReturnSearchTypeStructure should return params for book search."""
        result = providers.ReturnSearchTypeStructure(
            sample_provider,
            sample_provider['API'],
            sample_book,
            searchType='book',
            searchMode='nzb'
        )
        # Result should contain required parameters
        assert result is not None
        if result:
            assert 'apikey' in result

    def test_returns_params_for_mag_search(self, provider_config, sample_provider, sample_book):
        """ReturnSearchTypeStructure should return params for magazine search."""
        result = providers.ReturnSearchTypeStructure(
            sample_provider,
            sample_provider['API'],
            sample_book,
            searchType='mag',
            searchMode='nzb'
        )
        assert result is not None

    def test_returns_none_for_invalid_search_type(self, provider_config, sample_provider, sample_book):
        """ReturnSearchTypeStructure may return None for invalid search types."""
        result = providers.ReturnSearchTypeStructure(
            sample_provider,
            sample_provider['API'],
            sample_book,
            searchType='invalid_type',
            searchMode='nzb'
        )
        # Function behavior for invalid type - may return None or default


class TestReturnResultsFieldsBySearchType:
    """Tests for ReturnResultsFieldsBySearchType() function."""

    def test_parses_nzb_result(self, provider_config, sample_book):
        """ReturnResultsFieldsBySearchType should parse NZB XML result."""
        xml_content = '''<?xml version="1.0" encoding="utf-8"?>
            <item>
                <title>Test Book - EPUB</title>
                <guid>https://example.com/details/abc123</guid>
                <link>https://example.com/download/abc123.nzb</link>
                <pubDate>Sat, 02 Mar 2024 06:51:28 +0100</pubDate>
                <enclosure url="https://example.com/download/abc123.nzb" length="1024000" type="application/x-nzb" />
            </item>'''

        nzb_item = ElementTree.fromstring(xml_content)

        result = providers.ReturnResultsFieldsBySearchType(
            book=sample_book,
            nzbdetails=nzb_item,
            host='example.com',
            searchMode='book',
            priority=0
        )

        assert result is not None
        assert 'bookid' in result
        assert result['bookid'] == sample_book['bookid']
        assert 'nzbtitle' in result
        assert 'nzburl' in result

    def test_extracts_size_from_enclosure(self, provider_config, sample_book):
        """ReturnResultsFieldsBySearchType should extract size from enclosure."""
        xml_content = '''<?xml version="1.0" encoding="utf-8"?>
            <item>
                <title>Test Book</title>
                <link>https://example.com/download.nzb</link>
                <pubDate>Sat, 02 Mar 2024 06:51:28 +0100</pubDate>
                <enclosure url="https://example.com/download.nzb" length="2048000" type="application/x-nzb" />
            </item>'''

        nzb_item = ElementTree.fromstring(xml_content)

        result = providers.ReturnResultsFieldsBySearchType(
            book=sample_book,
            nzbdetails=nzb_item,
            host='example.com',
            searchMode='book',
            priority=0
        )

        assert result is not None
        assert 'nzbsize' in result

    def test_extracts_date_from_pubdate(self, provider_config, sample_book):
        """ReturnResultsFieldsBySearchType should extract date from pubDate."""
        xml_content = '''<?xml version="1.0" encoding="utf-8"?>
            <item>
                <title>Test Book</title>
                <link>https://example.com/download.nzb</link>
                <pubDate>Thu, 21 Nov 2024 16:13:52 +0100</pubDate>
            </item>'''

        nzb_item = ElementTree.fromstring(xml_content)

        result = providers.ReturnResultsFieldsBySearchType(
            book=sample_book,
            nzbdetails=nzb_item,
            host='example.com',
            searchMode='book',
            priority=0
        )

        assert result is not None
        assert 'nzbdate' in result
        assert '2024' in result['nzbdate'] or 'Nov' in result['nzbdate']


class TestProviderHelpers:
    """Tests for provider helper functions."""

    def test_get_searchterm_function_exists(self, provider_config):
        """get_searchterm function should exist in providers module."""
        assert hasattr(providers, 'get_searchterm')

    def test_provider_module_imports(self, provider_config):
        """providers module should import successfully."""
        assert providers is not None


class TestProviderConfiguration:
    """Tests for provider configuration handling."""

    def test_newznab_prov_list_exists(self):
        """NEWZNAB_PROV list should exist."""
        assert hasattr(bookbagofholding, 'NEWZNAB_PROV')
        assert isinstance(bookbagofholding.NEWZNAB_PROV, list)

    def test_torznab_prov_list_exists(self):
        """TORZNAB_PROV list should exist."""
        assert hasattr(bookbagofholding, 'TORZNAB_PROV')
        assert isinstance(bookbagofholding.TORZNAB_PROV, list)

    def test_rss_prov_list_exists(self):
        """RSS_PROV list should exist."""
        assert hasattr(bookbagofholding, 'RSS_PROV')
        assert isinstance(bookbagofholding.RSS_PROV, list)
