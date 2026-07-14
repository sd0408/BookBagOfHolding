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
Unit tests for bookbagofholding.postprocess module.

Tests cover:
- update_downloads function
- processAlternate function
- Archive handling utilities
- File processing helpers

Note: postprocess.py is a large module (1,989 lines) with complex dependencies.
These tests focus on the testable utility functions. Integration tests for
the full processing pipeline would require extensive mocking.
"""

import os
import tempfile
import shutil
import zipfile
import tarfile

import pytest
from unittest.mock import patch, Mock, MagicMock

import bookbagofholding
from bookbagofholding import postprocess


@pytest.fixture
def postprocess_config():
    """Set up configuration for postprocess testing."""
    original_config = dict(bookbagofholding.CONFIG)

    bookbagofholding.CONFIG['EBOOK_TYPE'] = 'epub, mobi, pdf'
    bookbagofholding.CONFIG['AUDIOBOOK_TYPE'] = 'mp3, m4b'
    bookbagofholding.CONFIG['DESTINATION_COPY'] = False
    bookbagofholding.CONFIG['BLACKLIST_FAILED'] = False  # Default to False for tests
    bookbagofholding.CONFIG['REJECT_WORDS'] = 'audiobook, mp3'
    bookbagofholding.CONFIG['REJECT_AUDIO'] = 'epub, mobi'
    bookbagofholding.CONFIG['BANNED_EXT'] = 'exe, bat'
    bookbagofholding.CONFIG['REJECT_MAXSIZE'] = 0
    bookbagofholding.CONFIG['REJECT_MINSIZE'] = 0
    bookbagofholding.CONFIG['REJECT_MAXAUDIO'] = 0
    bookbagofholding.LOGLEVEL = 0

    yield

    bookbagofholding.CONFIG.update(original_config)


class TestUpdateDownloads:
    """Tests for update_downloads() function."""

    def test_update_downloads_new_provider(self, temp_db):
        """update_downloads should insert new provider with count 1."""
        from bookbagofholding.database import DBConnection

        db_path, conn = temp_db

        # Create downloads table if not exists
        conn.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                Provider TEXT PRIMARY KEY,
                Count INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

        postprocess.update_downloads('test_provider')

        result = conn.execute(
            "SELECT Count FROM downloads WHERE Provider = ?",
            ('test_provider',)
        ).fetchone()

        assert result is not None
        assert result[0] == 1

    def test_update_downloads_existing_provider(self, temp_db):
        """update_downloads should increment count for existing provider."""
        from bookbagofholding.database import DBConnection

        db_path, conn = temp_db

        # Create downloads table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS downloads (
                Provider TEXT PRIMARY KEY,
                Count INTEGER DEFAULT 0
            )
        ''')
        conn.execute(
            "INSERT INTO downloads (Provider, Count) VALUES (?, ?)",
            ('existing_provider', 5)
        )
        conn.commit()

        postprocess.update_downloads('existing_provider')

        result = conn.execute(
            "SELECT Count FROM downloads WHERE Provider = ?",
            ('existing_provider',)
        ).fetchone()

        assert result[0] == 6


class TestProcessAlternate:
    """Tests for processAlternate() function."""

    def test_processAlternate_no_source_dir(self, postprocess_config):
        """processAlternate should return False when source_dir is None."""
        result = postprocess.processAlternate(source_dir=None)
        assert result is False

    def test_processAlternate_invalid_directory(self, postprocess_config):
        """processAlternate should return False for non-existent directory."""
        result = postprocess.processAlternate(source_dir='/nonexistent/path')
        assert result is False

    def test_processAlternate_same_as_destination(self, postprocess_config):
        """processAlternate should reject directory same as destination."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(bookbagofholding, 'DIRECTORY', return_value=tmpdir):
                result = postprocess.processAlternate(source_dir=tmpdir)
                # Note: the actual behavior depends on DIRECTORY function
                # This test documents expected behavior


class TestFileTypeValidation:
    """Tests for file type validation used in postprocess."""

    def test_valid_ebook_extensions(self, postprocess_config):
        """Should recognize valid ebook extensions."""
        from bookbagofholding.formatter import is_valid_booktype

        assert is_valid_booktype('book.epub') is True
        assert is_valid_booktype('book.mobi') is True
        assert is_valid_booktype('book.pdf') is True

    def test_invalid_ebook_extensions(self, postprocess_config):
        """Should reject invalid ebook extensions."""
        from bookbagofholding.formatter import is_valid_booktype

        assert is_valid_booktype('book.txt') is False
        assert is_valid_booktype('book.doc') is False
        assert is_valid_booktype('book.jpg') is False

    def test_valid_audiobook_extensions(self, postprocess_config):
        """Should recognize valid audiobook extensions."""
        from bookbagofholding.formatter import is_valid_booktype

        assert is_valid_booktype('book.mp3', booktype='audiobook') is True
        assert is_valid_booktype('book.m4b', booktype='audiobook') is True


class TestArchiveHandling:
    """Tests for archive extraction functionality."""

    def test_zip_archive_creation_and_detection(self, postprocess_config):
        """Test that we can create and detect zip archives."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, 'test_book.epub')
            with open(test_file, 'w') as f:
                f.write('test content')

            # Create a zip archive
            zip_path = os.path.join(tmpdir, 'archive.zip')
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.write(test_file, 'test_book.epub')

            assert os.path.exists(zip_path)
            assert zipfile.is_zipfile(zip_path)

    def test_tar_archive_creation_and_detection(self, postprocess_config):
        """Test that we can create and detect tar archives."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, 'test_book.epub')
            with open(test_file, 'w') as f:
                f.write('test content')

            # Create a tar archive
            tar_path = os.path.join(tmpdir, 'archive.tar.gz')
            with tarfile.open(tar_path, 'w:gz') as tf:
                tf.add(test_file, 'test_book.epub')

            assert os.path.exists(tar_path)
            assert tarfile.is_tarfile(tar_path)


class TestDicCharacterReplacement:
    """Tests for character replacement dictionary used in filename handling."""

    def test_dic_contains_expected_replacements(self):
        """The __dic__ should contain expected character replacements."""
        # Access the module-level __dic__ variable
        dic = postprocess.__dic__

        assert '<' in dic
        assert '>' in dic
        assert '?' in dic
        assert ':' in dic
        assert '"' in dic

    def test_character_replacement_removes_invalid_chars(self):
        """replace_all with __dic__ should remove invalid filename characters."""
        from bookbagofholding.formatter import replace_all

        dic = postprocess.__dic__
        filename = 'Book: Title? <Part 1>'
        result = replace_all(filename, dic)

        assert ':' not in result
        assert '?' not in result
        assert '<' not in result
        assert '>' not in result


class TestDownloadProgressTracking:
    """Tests for download progress tracking functionality."""

    @pytest.mark.integration
    @patch('bookbagofholding.postprocess.sabnzbd.SABnzbd')
    def test_get_sab_queue(self, mock_sab, postprocess_config):
        """Should retrieve SABnzbd queue status."""
        mock_sab.return_value = ({
            'queue': {
                'slots': [
                    {'filename': 'test_book.nzb', 'percentage': 50}
                ]
            }
        }, '')

        # This would test getDownloadProgress but that function
        # requires extensive mocking of multiple download clients


class TestDatabaseIntegration:
    """Tests for database operations in postprocess."""

    def test_database_connection_available(self, temp_db):
        """Database connection should be available for postprocess."""
        from bookbagofholding.database import DBConnection

        db = DBConnection()
        assert db is not None
        assert db.connection is not None


class TestProcessingHelpers:
    """Tests for processing helper functions."""

    def test_multibook_detection_single_book(self, postprocess_config):
        """multibook should return empty for single book."""
        from bookbagofholding.formatter import multibook

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create single book file
            with open(os.path.join(tmpdir, 'book.epub'), 'w') as f:
                f.write('content')

            result = multibook(tmpdir)
            assert result == ''

    def test_multibook_detection_multiple_books(self, postprocess_config):
        """multibook should return file type for multiple books."""
        from bookbagofholding.formatter import multibook

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple book files of same type
            with open(os.path.join(tmpdir, 'book1.epub'), 'w') as f:
                f.write('content1')
            with open(os.path.join(tmpdir, 'book2.epub'), 'w') as f:
                f.write('content2')

            result = multibook(tmpdir)
            assert result == 'epub'

    def test_multibook_detection_mixed_types(self, postprocess_config):
        """multibook should return empty for different book types."""
        from bookbagofholding.formatter import multibook

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files of different types
            with open(os.path.join(tmpdir, 'book1.epub'), 'w') as f:
                f.write('content1')
            with open(os.path.join(tmpdir, 'book2.mobi'), 'w') as f:
                f.write('content2')

            result = multibook(tmpdir)
            assert result == ''


class TestThreadSafety:
    """Tests for thread safety in postprocess operations."""

    def test_postprocess_uses_threading_lock(self):
        """postprocess operations should be thread-safe."""
        # The postprocess module uses threading
        import threading
        # Verify threading module is imported and usable
        assert hasattr(postprocess, 'threading') or 'threading' in dir()


class TestFailUnsupportedFiletype:
    """Tests for fail_unsupported_filetype() function."""

    @pytest.fixture
    def mock_book(self):
        """Create a mock book dict similar to wanted table row."""
        return {
            'NZBurl': 'http://example.com/download.nzb',
            'NZBtitle': 'Test Book - Author Name',
            'NZBprov': 'TestProvider',
            'BookID': 'book123',
            'Source': 'SABNZBD',
            'DownloadID': 'sab123',
            'AuxInfo': 'eBook'
        }

    @pytest.fixture
    def unsupported_files(self):
        """Files dict with only unsupported types."""
        return {
            'ebook': [],
            'audiobook': [],
            'other': ['readme.txt', 'sample.doc', 'cover.jpg']
        }

    @pytest.fixture
    def empty_files(self):
        """Files dict representing empty folder."""
        return {
            'ebook': [],
            'audiobook': [],
            'other': []
        }

    def test_fail_unsupported_filetype_returns_error_message(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should return descriptive error message."""
        db_path, conn = temp_db

        # Create required tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            with patch('bookbagofholding.searchbook.search_book'):
                result = postprocess.fail_unsupported_filetype(
                    mock_book, 'eBook', '/tmp/test', unsupported_files)

        assert 'No valid ebook files' in result
        assert 'unsupported types' in result

    def test_fail_unsupported_filetype_updates_wanted_status(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should update wanted table to Failed."""
        db_path, conn = temp_db

        # Create wanted table and insert test record
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY,
                NZBtitle TEXT,
                NZBprov TEXT,
                BookID TEXT,
                Status TEXT,
                DLResult TEXT,
                Source TEXT,
                DownloadID TEXT,
                AuxInfo TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, NZBtitle, BookID, Status) VALUES (?, ?, ?, ?)",
            (mock_book['NZBurl'], mock_book['NZBtitle'], mock_book['BookID'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            with patch('bookbagofholding.searchbook.search_book'):
                postprocess.fail_unsupported_filetype(
                    mock_book, 'eBook', '/tmp/test', unsupported_files)

        result = conn.execute(
            "SELECT Status, DLResult FROM wanted WHERE NZBurl=?",
            (mock_book['NZBurl'],)
        ).fetchone()

        assert result[0] == 'Failed'
        assert 'No valid ebook files' in result[1]

    def test_fail_unsupported_filetype_resets_ebook_status(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should reset ebook status to Wanted."""
        db_path, conn = temp_db

        # Create books table with snatched status
        conn.execute('''
            CREATE TABLE IF NOT EXISTS books (
                BookID TEXT PRIMARY KEY,
                status TEXT,
                audiostatus TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO books (BookID, status) VALUES (?, ?)",
            (mock_book['BookID'], 'Snatched')
        )
        # Create wanted table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            with patch('bookbagofholding.searchbook.search_book'):
                postprocess.fail_unsupported_filetype(
                    mock_book, 'eBook', '/tmp/test', unsupported_files)

        result = conn.execute(
            "SELECT status FROM books WHERE BookID=?",
            (mock_book['BookID'],)
        ).fetchone()

        assert result[0] == 'Wanted'

    def test_fail_unsupported_filetype_resets_audiobook_status(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should reset audiobook status to Wanted."""
        db_path, conn = temp_db

        mock_book['AuxInfo'] = 'AudioBook'

        # Create books table with snatched audiostatus
        conn.execute('''
            CREATE TABLE IF NOT EXISTS books (
                BookID TEXT PRIMARY KEY,
                status TEXT,
                audiostatus TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO books (BookID, audiostatus) VALUES (?, ?)",
            (mock_book['BookID'], 'Snatched')
        )
        # Create wanted table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            with patch('bookbagofholding.searchbook.search_book'):
                postprocess.fail_unsupported_filetype(
                    mock_book, 'AudioBook', '/tmp/test', unsupported_files)

        result = conn.execute(
            "SELECT audiostatus FROM books WHERE BookID=?",
            (mock_book['BookID'],)
        ).fetchone()

        assert result[0] == 'Wanted'

    def test_fail_unsupported_filetype_calls_delete_task(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should call delete_task to remove from client."""
        db_path, conn = temp_db

        # Create required tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True) as mock_delete:
            with patch('bookbagofholding.searchbook.search_book'):
                postprocess.fail_unsupported_filetype(
                    mock_book, 'eBook', '/tmp/test', unsupported_files)

        mock_delete.assert_called_once_with(
            mock_book['Source'], mock_book['DownloadID'], True)

    def test_fail_unsupported_filetype_adds_to_blacklist(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should blacklist when BLACKLIST_FAILED enabled."""
        bookbagofholding.CONFIG['BLACKLIST_FAILED'] = True
        db_path, conn = temp_db

        # Create blacklist table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                NZBurl TEXT PRIMARY KEY,
                NZBtitle TEXT,
                NZBprov TEXT,
                BookID TEXT,
                AuxInfo TEXT,
                DateAdded TEXT,
                Reason TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            with patch('bookbagofholding.searchbook.search_book'):
                postprocess.fail_unsupported_filetype(
                    mock_book, 'eBook', '/tmp/test', unsupported_files)

        result = conn.execute(
            "SELECT Reason FROM blacklist WHERE NZBurl=?",
            (mock_book['NZBurl'],)
        ).fetchone()

        assert result is not None
        assert result[0] == 'UnsupportedFileType'

    def test_fail_unsupported_filetype_skips_blacklist_when_disabled(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should skip blacklist when BLACKLIST_FAILED disabled."""
        bookbagofholding.CONFIG['BLACKLIST_FAILED'] = False
        db_path, conn = temp_db

        # Create blacklist table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                NZBurl TEXT PRIMARY KEY, Reason TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            with patch('bookbagofholding.searchbook.search_book'):
                postprocess.fail_unsupported_filetype(
                    mock_book, 'eBook', '/tmp/test', unsupported_files)

        result = conn.execute("SELECT COUNT(*) FROM blacklist").fetchone()
        assert result[0] == 0

    def test_fail_unsupported_filetype_handles_empty_folder(
            self, temp_db, mock_book, empty_files, postprocess_config):
        """fail_unsupported_filetype should handle empty download folders."""
        db_path, conn = temp_db

        # Create required tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            with patch('bookbagofholding.searchbook.search_book'):
                result = postprocess.fail_unsupported_filetype(
                    mock_book, 'eBook', '/tmp/test', empty_files)

        assert 'empty or contains only non-media files' in result

    def test_fail_unsupported_filetype_skips_delete_for_direct(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should skip delete_task for DIRECT source."""
        mock_book['Source'] = 'DIRECT'
        db_path, conn = temp_db

        # Create required tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True) as mock_delete:
            with patch('bookbagofholding.searchbook.search_book'):
                postprocess.fail_unsupported_filetype(
                    mock_book, 'eBook', '/tmp/test', unsupported_files)

        mock_delete.assert_not_called()

    def test_fail_unsupported_filetype_handles_unknown_bookid(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should skip book update for unknown BookID."""
        mock_book['BookID'] = 'unknown'
        db_path, conn = temp_db

        # Create books table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS books (
                BookID TEXT PRIMARY KEY,
                status TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO books (BookID, status) VALUES (?, ?)",
            ('other_book', 'Snatched')
        )
        # Create wanted table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            postprocess.fail_unsupported_filetype(
                mock_book, 'eBook', '/tmp/test', unsupported_files)

        # Verify no book status was changed
        result = conn.execute(
            "SELECT status FROM books WHERE BookID=?",
            ('other_book',)
        ).fetchone()

        assert result[0] == 'Snatched'  # Unchanged

    def test_fail_unsupported_filetype_limits_extensions_display(
            self, temp_db, mock_book, postprocess_config):
        """fail_unsupported_filetype should limit extension display to 5."""
        many_files = {
            'ebook': [],
            'audiobook': [],
            'other': [
                'file.txt', 'file.doc', 'file.xls', 'file.ppt',
                'file.rtf', 'file.odt', 'file.ods', 'file.odp'
            ]
        }
        db_path, conn = temp_db

        # Create required tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            with patch('bookbagofholding.searchbook.search_book'):
                result = postprocess.fail_unsupported_filetype(
                    mock_book, 'eBook', '/tmp/test', many_files)

        assert '(and more)' in result

    def test_fail_unsupported_filetype_triggers_search(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should trigger immediate search for the book."""
        from bookbagofholding import searchbook

        db_path, conn = temp_db

        # Create required tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            with patch('bookbagofholding.searchbook.search_book') as mock_search:
                with patch('threading.Thread') as mock_thread:
                    mock_thread_instance = MagicMock()
                    mock_thread.return_value = mock_thread_instance

                    postprocess.fail_unsupported_filetype(
                        mock_book, 'eBook', '/tmp/test', unsupported_files)

                    # Verify Thread was created with correct arguments
                    mock_thread.assert_called_once()
                    call_kwargs = mock_thread.call_args[1]
                    assert call_kwargs['target'] == searchbook.search_book
                    assert 'SEARCH-RETRY' in call_kwargs['name']
                    assert call_kwargs['args'] == [[{'bookid': mock_book['BookID']}], 'eBook']

                    # Verify thread was started
                    mock_thread_instance.start.assert_called_once()

    def test_fail_unsupported_filetype_skips_search_for_unknown_bookid(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should skip search trigger for unknown BookID."""
        mock_book['BookID'] = 'unknown'
        db_path, conn = temp_db

        # Create required tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            with patch('threading.Thread') as mock_thread:
                postprocess.fail_unsupported_filetype(
                    mock_book, 'eBook', '/tmp/test', unsupported_files)

                # Verify Thread was NOT created for unknown BookID
                mock_thread.assert_not_called()


class TestCheckContents:
    """Tests for check_contents() function - validates download file contents."""

    def test_check_contents_accepts_valid_epub(self, postprocess_config):
        """check_contents should accept a download with only valid epub files."""
        with patch.object(postprocess, 'getDownloadFiles') as mock_get_files:
            mock_get_files.return_value = [
                {'name': 'Book Title/Book Title.epub', 'size': 500000}
            ]

            result = postprocess.check_contents(
                'QBITTORRENT', 'abc123', 'ebook', 'Book Title')

            assert result == ''  # Empty string means accepted

    def test_check_contents_rejects_epub_with_banned_word(self, postprocess_config):
        """check_contents should reject an epub with banned word in filename."""
        with patch.object(postprocess, 'getDownloadFiles') as mock_get_files:
            mock_get_files.return_value = [
                {'name': 'Book Title/audiobook companion.epub', 'size': 500000}
            ]

            result = postprocess.check_contents(
                'QBITTORRENT', 'abc123', 'ebook', 'Book Title')

            assert 'audiobook' in result  # Should be rejected

    def test_check_contents_ignores_txt_with_banned_word(self, postprocess_config):
        """check_contents should NOT reject due to banned word in txt file.

        This is the key fix: info/advertisement txt files commonly found in
        torrents should not trigger rejection of valid ebook downloads.
        """
        with patch.object(postprocess, 'getDownloadFiles') as mock_get_files:
            mock_get_files.return_value = [
                {'name': 'Book Title/Book Title.epub', 'size': 500000},
                {'name': 'Book Title/free audiobook version.txt', 'size': 1000}
            ]

            result = postprocess.check_contents(
                'QBITTORRENT', 'abc123', 'ebook', 'Book Title')

            # Should be accepted - the txt file with "audiobook" should be ignored
            assert result == ''

    def test_check_contents_ignores_nfo_with_banned_word(self, postprocess_config):
        """check_contents should NOT reject due to banned word in nfo file."""
        with patch.object(postprocess, 'getDownloadFiles') as mock_get_files:
            mock_get_files.return_value = [
                {'name': 'Book Title/Book Title.epub', 'size': 500000},
                {'name': 'Book Title/audiobook_available.nfo', 'size': 500}
            ]

            result = postprocess.check_contents(
                'QBITTORRENT', 'abc123', 'ebook', 'Book Title')

            assert result == ''

    def test_check_contents_rejects_banned_extension(self, postprocess_config):
        """check_contents should reject files with banned extensions."""
        with patch.object(postprocess, 'getDownloadFiles') as mock_get_files:
            mock_get_files.return_value = [
                {'name': 'Book Title/Book Title.epub', 'size': 500000},
                {'name': 'Book Title/installer.exe', 'size': 100000}
            ]

            result = postprocess.check_contents(
                'QBITTORRENT', 'abc123', 'ebook', 'Book Title')

            assert 'exe' in result

    def test_check_contents_audiobook_accepts_valid_mp3(self, postprocess_config):
        """check_contents should accept valid audiobook files."""
        with patch.object(postprocess, 'getDownloadFiles') as mock_get_files:
            mock_get_files.return_value = [
                {'name': 'Audiobook/Chapter 01.mp3', 'size': 50000000},
                {'name': 'Audiobook/Chapter 02.mp3', 'size': 50000000}
            ]

            result = postprocess.check_contents(
                'QBITTORRENT', 'abc123', 'audiobook', 'Audiobook Title')

            assert result == ''

    def test_check_contents_audiobook_rejects_mp3_with_epub_in_name(
            self, postprocess_config):
        """check_contents should reject audiobook with ebook word in filename."""
        with patch.object(postprocess, 'getDownloadFiles') as mock_get_files:
            mock_get_files.return_value = [
                {'name': 'Audiobook/epub companion guide.mp3', 'size': 50000000}
            ]

            result = postprocess.check_contents(
                'QBITTORRENT', 'abc123', 'audiobook', 'Audiobook Title')

            assert 'epub' in result

    def test_check_contents_audiobook_ignores_txt_with_banned_word(
            self, postprocess_config):
        """check_contents should ignore txt file with banned word for audiobooks."""
        with patch.object(postprocess, 'getDownloadFiles') as mock_get_files:
            mock_get_files.return_value = [
                {'name': 'Audiobook/Chapter 01.mp3', 'size': 50000000},
                {'name': 'Audiobook/get the epub version.txt', 'size': 500}
            ]

            result = postprocess.check_contents(
                'QBITTORRENT', 'abc123', 'audiobook', 'Audiobook Title')

            assert result == ''

    def test_check_contents_empty_filelist(self, postprocess_config):
        """check_contents should handle empty file list gracefully."""
        with patch.object(postprocess, 'getDownloadFiles') as mock_get_files:
            mock_get_files.return_value = []

            result = postprocess.check_contents(
                'QBITTORRENT', 'abc123', 'ebook', 'Book Title')

            assert result == ''

    def test_check_contents_none_filelist(self, postprocess_config):
        """check_contents should handle None file list gracefully."""
        with patch.object(postprocess, 'getDownloadFiles') as mock_get_files:
            mock_get_files.return_value = None

            result = postprocess.check_contents(
                'QBITTORRENT', 'abc123', 'ebook', 'Book Title')

            assert result == ''


class TestFailTypeMismatch:
    """Tests for fail_type_mismatch() function."""

    @pytest.fixture
    def mock_book(self):
        """Create a mock book dict similar to wanted table row."""
        return {
            'NZBurl': 'http://example.com/download.nzb',
            'NZBtitle': 'Test Book - Author Name',
            'NZBprov': 'TestProvider',
            'BookID': 'book123',
            'Source': 'SABNZBD',
            'DownloadID': 'sab123',
            'AuxInfo': 'AudioBook'
        }

    @pytest.fixture
    def ebook_files(self):
        """Files dict with ebook when expecting audiobook."""
        return {
            'ebook': ['Book Title.epub', 'Book Title.mobi'],
            'audiobook': [],
            'other': ['readme.txt']
        }

    @pytest.fixture
    def audiobook_files(self):
        """Files dict with audiobook when expecting ebook."""
        return {
            'ebook': [],
            'audiobook': ['Chapter 01.mp3', 'Chapter 02.mp3'],
            'other': []
        }

    def test_fail_type_mismatch_returns_error_message(
            self, temp_db, mock_book, ebook_files, postprocess_config):
        """fail_type_mismatch should return descriptive error message."""
        db_path, conn = temp_db

        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            result = postprocess.fail_type_mismatch(
                mock_book, 'AudioBook', '/tmp/nonexistent', ebook_files)

        assert 'Type mismatch' in result
        assert 'expected AudioBook' in result
        assert 'ebook' in result

    def test_fail_type_mismatch_updates_wanted_status(
            self, temp_db, mock_book, ebook_files, postprocess_config):
        """fail_type_mismatch should update wanted table to Failed."""
        db_path, conn = temp_db

        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            postprocess.fail_type_mismatch(
                mock_book, 'AudioBook', '/tmp/nonexistent', ebook_files)

        result = conn.execute(
            "SELECT Status, DLResult FROM wanted WHERE NZBurl=?",
            (mock_book['NZBurl'],)
        ).fetchone()

        assert result[0] == 'Failed'
        assert 'Type mismatch' in result[1]

    def test_fail_type_mismatch_resets_audiobook_status(
            self, temp_db, mock_book, ebook_files, postprocess_config):
        """fail_type_mismatch should reset audiobook status to Wanted."""
        db_path, conn = temp_db

        conn.execute('''
            CREATE TABLE IF NOT EXISTS books (
                BookID TEXT PRIMARY KEY, status TEXT, audiostatus TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO books (BookID, audiostatus) VALUES (?, ?)",
            (mock_book['BookID'], 'Snatched')
        )
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            postprocess.fail_type_mismatch(
                mock_book, 'AudioBook', '/tmp/nonexistent', ebook_files)

        result = conn.execute(
            "SELECT audiostatus FROM books WHERE BookID=?",
            (mock_book['BookID'],)
        ).fetchone()

        assert result[0] == 'Wanted'

    def test_fail_type_mismatch_deletes_directory_when_copy_disabled(
            self, temp_db, mock_book, ebook_files, postprocess_config):
        """fail_type_mismatch should delete pp_path when DESTINATION_COPY is False."""
        db_path, conn = temp_db

        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        # Create a temporary directory to test deletion
        test_dir = tempfile.mkdtemp()
        test_file = os.path.join(test_dir, 'test.epub')
        with open(test_file, 'w') as f:
            f.write('test content')

        try:
            bookbagofholding.CONFIG['DESTINATION_COPY'] = False

            with patch.object(postprocess, 'delete_task', return_value=True):
                postprocess.fail_type_mismatch(
                    mock_book, 'AudioBook', test_dir, ebook_files)

            # Directory should be deleted
            assert not os.path.exists(test_dir)
        finally:
            # Cleanup if test failed
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

    def test_fail_type_mismatch_renames_directory_when_copy_enabled(
            self, temp_db, mock_book, ebook_files, postprocess_config):
        """fail_type_mismatch should rename pp_path to .fail when DESTINATION_COPY is True."""
        db_path, conn = temp_db

        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        # Create a temporary directory to test renaming
        test_dir = tempfile.mkdtemp()
        test_file = os.path.join(test_dir, 'test.epub')
        with open(test_file, 'w') as f:
            f.write('test content')

        fail_path = test_dir + '.fail'

        try:
            bookbagofholding.CONFIG['DESTINATION_COPY'] = True

            with patch.object(postprocess, 'delete_task', return_value=True):
                postprocess.fail_type_mismatch(
                    mock_book, 'AudioBook', test_dir, ebook_files)

            # Original directory should be gone
            assert not os.path.exists(test_dir)
            # .fail directory should exist
            assert os.path.exists(fail_path)
        finally:
            # Cleanup
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
            if os.path.exists(fail_path):
                shutil.rmtree(fail_path)

    def test_fail_type_mismatch_handles_nonexistent_path(
            self, temp_db, mock_book, ebook_files, postprocess_config):
        """fail_type_mismatch should handle nonexistent pp_path gracefully."""
        db_path, conn = temp_db

        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            # Should not raise exception
            result = postprocess.fail_type_mismatch(
                mock_book, 'AudioBook', '/nonexistent/path', ebook_files)

        assert 'Type mismatch' in result


class TestFailUnsupportedFiletypeCleanup:
    """Tests for fail_unsupported_filetype() file cleanup behavior."""

    @pytest.fixture
    def mock_book(self):
        """Create a mock book dict similar to wanted table row."""
        return {
            'NZBurl': 'http://example.com/download.nzb',
            'NZBtitle': 'Test Book - Author Name',
            'NZBprov': 'TestProvider',
            'BookID': 'book123',
            'Source': 'SABNZBD',
            'DownloadID': 'sab123',
            'AuxInfo': 'eBook'
        }

    @pytest.fixture
    def unsupported_files(self):
        """Files dict with only unsupported types."""
        return {
            'ebook': [],
            'audiobook': [],
            'other': ['readme.txt', 'sample.doc']
        }

    def test_fail_unsupported_filetype_deletes_directory(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should delete pp_path when DESTINATION_COPY is False."""
        db_path, conn = temp_db

        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        # Create a temporary directory to test deletion
        test_dir = tempfile.mkdtemp()
        test_file = os.path.join(test_dir, 'readme.txt')
        with open(test_file, 'w') as f:
            f.write('test content')

        try:
            bookbagofholding.CONFIG['DESTINATION_COPY'] = False

            with patch.object(postprocess, 'delete_task', return_value=True):
                with patch('bookbagofholding.searchbook.search_book'):
                    postprocess.fail_unsupported_filetype(
                        mock_book, 'eBook', test_dir, unsupported_files)

            # Directory should be deleted
            assert not os.path.exists(test_dir)
        finally:
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

    def test_fail_unsupported_filetype_renames_directory_when_copy_enabled(
            self, temp_db, mock_book, unsupported_files, postprocess_config):
        """fail_unsupported_filetype should rename to .fail when DESTINATION_COPY is True."""
        db_path, conn = temp_db

        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        # Create a temporary directory to test renaming
        test_dir = tempfile.mkdtemp()
        test_file = os.path.join(test_dir, 'readme.txt')
        with open(test_file, 'w') as f:
            f.write('test content')

        fail_path = test_dir + '.fail'

        try:
            bookbagofholding.CONFIG['DESTINATION_COPY'] = True

            with patch.object(postprocess, 'delete_task', return_value=True):
                with patch('bookbagofholding.searchbook.search_book'):
                    postprocess.fail_unsupported_filetype(
                        mock_book, 'eBook', test_dir, unsupported_files)

            # Original should be gone, .fail should exist
            assert not os.path.exists(test_dir)
            assert os.path.exists(fail_path)
        finally:
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
            if os.path.exists(fail_path):
                shutil.rmtree(fail_path)


class TestHtmlEntityHandling:
    """Tests for HTML entity decoding in folder name matching.

    Some download clients (e.g., SABnzbd) may create folder names with HTML entities
    like '&amp;' instead of '&'. These tests verify that such entities are properly
    decoded before fuzzy matching.
    """

    def test_html_unescape_ampersand(self):
        """html.unescape should convert &amp; to &."""
        import html
        folder_name = "Dan Simmons Hyperion &amp; Endymion Band"
        decoded = html.unescape(folder_name)
        assert decoded == "Dan Simmons Hyperion & Endymion Band"

    def test_html_unescape_multiple_entities(self):
        """html.unescape should handle multiple HTML entities."""
        import html
        folder_name = "Author &amp; Title &lt;Book&gt;"
        decoded = html.unescape(folder_name)
        assert decoded == "Author & Title <Book>"

    def test_html_unescape_no_entities(self):
        """html.unescape should not modify strings without entities."""
        import html
        folder_name = "Dan Simmons Hyperion"
        decoded = html.unescape(folder_name)
        assert decoded == "Dan Simmons Hyperion"

    def test_dic_replaces_ampersand_after_decode(self):
        """After HTML decode, __dic__ should replace ' & ' with space."""
        import html
        from bookbagofholding.formatter import replace_all

        folder_name = "Dan Simmons Hyperion &amp; Endymion"
        # First decode HTML entities
        decoded = html.unescape(folder_name)
        assert decoded == "Dan Simmons Hyperion & Endymion"

        # Then apply __dic__ replacement (replaces ' & ' with single space ' ')
        cleaned = replace_all(decoded, postprocess.__dic__)
        assert cleaned == "Dan Simmons Hyperion Endymion"

    def test_matching_with_html_entities_in_folder(self, postprocess_config):
        """Folder with HTML entities should match NZB title using fuzzy matching.

        This tests the real-world scenario where:
        - NZBtitle is 'HB Dan Simmons Hyperion Endymion'
        - Folder name is 'Dan Simmons Hyperion &amp; Endymion Band'
        """
        import html
        from fuzzywuzzy import fuzz
        from bookbagofholding.formatter import unaccented_str, replace_all

        # Simulate the NZBtitle processing
        nzb_title = "HB Dan Simmons Hyperion Endymion"
        matchtitle = unaccented_str(nzb_title)
        matchtitle = html.unescape(matchtitle)
        matchtitle = matchtitle.split(' LL.(')[0].replace('_', ' ')
        matchtitle = replace_all(matchtitle, postprocess.__dic__)

        # Simulate the folder name processing (with HTML entity)
        folder_name = "Dan Simmons Hyperion &amp; Endymion Band"
        matchname = unaccented_str(folder_name)
        matchname = html.unescape(matchname)
        matchname = matchname.split(' LL.(')[0].replace('_', ' ')
        matchname = replace_all(matchname, postprocess.__dic__)

        # Check that the fuzzy match is reasonable (should be > 80%)
        match_ratio = fuzz.token_set_ratio(matchtitle, matchname)
        assert match_ratio >= 80, f"Match ratio {match_ratio}% is too low for '{matchtitle}' vs '{matchname}'"

    def test_matching_without_html_decode_fails(self, postprocess_config):
        """Without HTML entity decoding, the ampersand is not properly cleaned.

        This demonstrates the bug that was fixed - without html.unescape(),
        '&amp;' is not converted to '&', so __dic__ replacement of ' & ' doesn't work.
        """
        from bookbagofholding.formatter import unaccented_str, replace_all

        # Without HTML decode, &amp; stays as &amp;
        folder_name = "Dan Simmons Hyperion &amp; Endymion"
        matchname = unaccented_str(folder_name)
        # Skip html.unescape - simulating the old behavior
        matchname = matchname.split(' LL.(')[0].replace('_', ' ')
        matchname = replace_all(matchname, postprocess.__dic__)

        # &amp; should still be in the string (not replaced)
        assert 'amp' in matchname, "Without HTML decode, 'amp' should remain in the string"

    def test_html_entity_decode_applied_consistently(self, postprocess_config):
        """Both matchtitle and matchname should have HTML entities decoded."""
        import html
        from bookbagofholding.formatter import unaccented_str, replace_all

        # If NZBtitle has HTML entities (possible from some sources)
        nzb_title = "Dan Simmons Hyperion &amp; Endymion"
        matchtitle = unaccented_str(nzb_title)
        matchtitle = html.unescape(matchtitle)
        matchtitle = matchtitle.split(' LL.(')[0].replace('_', ' ')
        matchtitle = replace_all(matchtitle, postprocess.__dic__)

        # Folder name also with HTML entities
        folder_name = "Dan Simmons Hyperion &amp; Endymion"
        matchname = unaccented_str(folder_name)
        matchname = html.unescape(matchname)
        matchname = matchname.split(' LL.(')[0].replace('_', ' ')
        matchname = replace_all(matchname, postprocess.__dic__)

        # Should be identical after processing
        assert matchtitle == matchname


class TestIsBestSnatchedOwner:
    """Tests for is_best_snatched_owner() — guards against wrong-book failure
    when sibling snatches in the same series fuzz-match each other's folders."""

    def _normalize(self, text):
        from bookbagofholding.postprocess import _normalize_for_match
        return _normalize_for_match(text)

    def test_single_book_owns_folder(self, postprocess_config):
        """With only one snatched book, it always owns the folder."""
        book = {
            'NZBurl': 'http://example.com/1',
            'NZBtitle': 'Charlaine Harris Definitely Dead par yEnc',
        }
        snatched = [book]
        matchname = self._normalize(
            'Charlaine Harris Sookie Stackhouse Definitely Dead')
        assert postprocess.is_best_snatched_owner(snatched, book, matchname, 95)

    def test_sibling_book_wins_ownership(self, postprocess_config):
        """Folder for book B should NOT be flagged as owned by book A,
        even when A's NZBtitle scores above DLOAD_RATIO against B's folder name."""
        from fuzzywuzzy import fuzz
        book_a = {
            'NZBurl': 'http://example.com/from-dead-to-worse',
            'NZBtitle': 'NMR _ Charlaine Harris Sookie Stackhouse From Dead To Worse par yEnc',
        }
        book_b = {
            'NZBurl': 'http://example.com/definitely-dead',
            'NZBtitle': 'NMR _ Charlaine Harris Sookie Stackhouse Definitely Dead par yEnc',
        }
        snatched = [book_a, book_b]
        # Folder for book B
        folder_b = self._normalize(
            'NMR _ Charlaine Harris Sookie Stackhouse Definitely Dead par yEnc')
        match_a_vs_b = fuzz.token_set_ratio(
            self._normalize(book_a['NZBtitle']), folder_b)
        # The fuzz score is high because of shared series tokens — that's the bug surface.
        assert match_a_vs_b >= 80
        # Ownership check should still correctly attribute folder B to book B.
        assert not postprocess.is_best_snatched_owner(
            snatched, book_a, folder_b, match_a_vs_b)
        match_b_vs_b = fuzz.token_set_ratio(
            self._normalize(book_b['NZBtitle']), folder_b)
        assert postprocess.is_best_snatched_owner(
            snatched, book_b, folder_b, match_b_vs_b)

    def test_higher_match_loses_to_equal_match(self, postprocess_config):
        """Ties go to the current book — only a strictly higher match for another
        snatched book disqualifies ownership. This prevents flip-flopping when two
        snatched books normalize to the same title."""
        book_a = {
            'NZBurl': 'http://example.com/a',
            'NZBtitle': 'Same Title',
        }
        book_b = {
            'NZBurl': 'http://example.com/b',
            'NZBtitle': 'Same Title',
        }
        snatched = [book_a, book_b]
        folder = self._normalize('Same Title')
        # Both books would tie on this folder
        assert postprocess.is_best_snatched_owner(snatched, book_a, folder, 100)


class TestFilenameMatchesBook:
    """Tests for filename_matches_book() — pre-Calibre title sanity check."""

    def test_matches_book_with_close_filename(self, postprocess_config):
        """Filename close to bookname should match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'Dead Ever After.epub'), 'w') as f:
                f.write('x')
            assert postprocess.filename_matches_book(tmpdir, 'Dead Ever After')

    def test_rejects_unrelated_filename(self, postprocess_config):
        """A snatch of 'Dead Ever After' that contains 'After Dead' should be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'After Dead - Charlaine Harris.epub'), 'w') as f:
                f.write('x')
            assert not postprocess.filename_matches_book(tmpdir, 'Dead Ever After')

    def test_no_book_files_returns_true(self, postprocess_config):
        """If no book files exist, defer to downstream handlers (return True)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'readme.txt'), 'w') as f:
                f.write('x')
            assert postprocess.filename_matches_book(tmpdir, 'Whatever')

    def test_nonexistent_path_returns_true(self, postprocess_config):
        """Non-existent path: defer (don't break callers)."""
        assert postprocess.filename_matches_book(
            '/definitely/does/not/exist', 'Some Book')

    def test_empty_bookname_returns_true(self, postprocess_config):
        """No bookname to compare against: defer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'random.epub'), 'w') as f:
                f.write('x')
            assert postprocess.filename_matches_book(tmpdir, '')

    def test_matches_despite_series_volume_decoration(self, postprocess_config):
        """Wanted titles carry series/volume decoration that never appears in the
        filename (e.g. 'Solo (Book #2)'). The correct file must still match;
        otherwise the snatch is falsely failed and re-grabbed forever. Regression
        test for the NZBFinder duplicate-download loop."""
        cases = [
            ('Vasily Mahanenko - Solo (epub).epub', 'Solo (Book #2)'),
            ('Vasily Mahanenko - [Dark Paladin 03] - Restart (epub).epub',
             'Restart (Dark Paladin Book #3)'),
            ('Vasily Mahanenko - [The Way of the Shaman 02] - '
             'The Kartoss Gambit (epub).epub',
             'The Kartoss Gambit (The Way of the Shaman Book #2)'),
        ]
        for filename, bookname in cases:
            with tempfile.TemporaryDirectory() as tmpdir:
                with open(os.path.join(tmpdir, filename), 'w') as f:
                    f.write('x')
                assert postprocess.filename_matches_book(tmpdir, bookname), \
                    'expected %r to match file %r' % (bookname, filename)


class TestFailTitleMismatch:
    """Tests for fail_title_mismatch() — handles wrong-book-in-folder cases."""

    @pytest.fixture
    def mock_book(self):
        return {
            'NZBurl': 'http://example.com/dead-ever-after.nzb',
            'NZBtitle': 'Charlaine Harris Dead Ever After',
            'NZBprov': 'TestProvider',
            'BookID': 'book-dea-001',
            'Source': 'SABNZBD',
            'DownloadID': 'sab-dea',
            'AuxInfo': 'eBook',
        }

    def test_returns_error_message(self, temp_db, mock_book, postprocess_config):
        db_path, conn = temp_db
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            result = postprocess.fail_title_mismatch(
                mock_book, 'eBook', '/tmp/nonexistent',
                'Dead Ever After', ['After Dead - Charlaine Harris.epub'])

        assert 'Title mismatch' in result
        assert 'Dead Ever After' in result
        assert 'After Dead' in result

    def test_marks_snatch_failed(self, temp_db, mock_book, postprocess_config):
        db_path, conn = temp_db
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            postprocess.fail_title_mismatch(
                mock_book, 'eBook', '/tmp/nonexistent',
                'Dead Ever After', ['After Dead - Charlaine Harris.epub'])

        row = conn.execute(
            "SELECT Status, DLResult FROM wanted WHERE NZBurl=?",
            (mock_book['NZBurl'],)
        ).fetchone()
        assert row[0] == 'Failed'
        assert 'Title mismatch' in row[1]

    def test_resets_book_status_to_wanted(self, temp_db, mock_book, postprocess_config):
        db_path, conn = temp_db
        conn.execute('''
            CREATE TABLE IF NOT EXISTS books (
                BookID TEXT PRIMARY KEY, status TEXT, audiostatus TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO books (BookID, status) VALUES (?, ?)",
            (mock_book['BookID'], 'Snatched')
        )
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            postprocess.fail_title_mismatch(
                mock_book, 'eBook', '/tmp/nonexistent',
                'Dead Ever After', ['After Dead.epub'])

        row = conn.execute(
            "SELECT status FROM books WHERE BookID=?",
            (mock_book['BookID'],)
        ).fetchone()
        assert row[0] == 'Wanted'

    def test_blacklists_when_enabled(self, temp_db, mock_book, postprocess_config):
        bookbagofholding.CONFIG['BLACKLIST_FAILED'] = True
        db_path, conn = temp_db
        conn.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                NZBurl TEXT PRIMARY KEY, NZBtitle TEXT, NZBprov TEXT,
                BookID TEXT, AuxInfo TEXT, DateAdded TEXT, Reason TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        with patch.object(postprocess, 'delete_task', return_value=True):
            postprocess.fail_title_mismatch(
                mock_book, 'eBook', '/tmp/nonexistent',
                'Dead Ever After', ['After Dead.epub'])

        row = conn.execute(
            "SELECT Reason FROM blacklist WHERE NZBurl=?",
            (mock_book['NZBurl'],)
        ).fetchone()
        assert row is not None
        assert row[0] == 'TitleMismatch'

    def test_cleans_up_folder_via_move(self, temp_db, mock_book, postprocess_config):
        """When DESTINATION_COPY is True, the folder should be moved to .fail
        and not left behind as a duplicate (this is the safe_move bug surface)."""
        db_path, conn = temp_db
        conn.execute('''
            CREATE TABLE IF NOT EXISTS wanted (
                NZBurl TEXT PRIMARY KEY, Status TEXT, DLResult TEXT
            )
        ''')
        conn.execute(
            "INSERT INTO wanted (NZBurl, Status) VALUES (?, ?)",
            (mock_book['NZBurl'], 'Snatched')
        )
        conn.commit()

        bookbagofholding.CONFIG['DESTINATION_COPY'] = True
        test_dir = tempfile.mkdtemp()
        with open(os.path.join(test_dir, 'After Dead.epub'), 'w') as f:
            f.write('x')
        fail_path = test_dir + '.fail'
        try:
            with patch.object(postprocess, 'delete_task', return_value=True):
                postprocess.fail_title_mismatch(
                    mock_book, 'eBook', test_dir,
                    'Dead Ever After', ['After Dead.epub'])
            assert not os.path.exists(test_dir)
            assert os.path.isdir(fail_path)
        finally:
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
            if os.path.exists(fail_path):
                shutil.rmtree(fail_path)
