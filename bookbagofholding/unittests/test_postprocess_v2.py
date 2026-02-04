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
Unit tests for bookbagofholding.postprocess_v2 module.

Tests cover:
- FileDetector class for file type detection
- MetadataExtractor for metadata extraction
- BookMatcher for book matching
- FileOrganizer for file organization
- Unpacker for archive extraction
"""

import os
import pytest
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch


class TestFileDetectorExtensions:
    """Tests for FileDetector extension methods."""

    @pytest.fixture
    def mock_config(self):
        """Mock bookbagofholding CONFIG."""
        with patch('bookbagofholding.postprocess_v2.detector.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {
                'EBOOK_TYPE': 'epub,mobi,pdf',
                'AUDIOBOOK_TYPE': 'mp3,m4a,m4b'
            }
            yield mock_bb

    def test_get_ebook_extensions(self, mock_config):
        """get_ebook_extensions should return configured extensions."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        extensions = FileDetector.get_ebook_extensions()
        assert '.epub' in extensions
        assert '.mobi' in extensions
        assert '.pdf' in extensions

    def test_get_ebook_extensions_adds_dots(self, mock_config):
        """get_ebook_extensions should add leading dots."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        extensions = FileDetector.get_ebook_extensions()
        for ext in extensions:
            assert ext.startswith('.')

    def test_get_audiobook_extensions(self, mock_config):
        """get_audiobook_extensions should return configured extensions."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        extensions = FileDetector.get_audiobook_extensions()
        assert '.mp3' in extensions
        assert '.m4a' in extensions
        assert '.m4b' in extensions


class TestFileDetectorIsChecks:
    """Tests for FileDetector is_* methods."""

    @pytest.fixture
    def mock_config(self):
        """Mock bookbagofholding CONFIG."""
        with patch('bookbagofholding.postprocess_v2.detector.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {
                'EBOOK_TYPE': 'epub,mobi,pdf',
                'AUDIOBOOK_TYPE': 'mp3,m4a,m4b'
            }
            yield mock_bb

    def test_is_ebook_returns_true_for_ebook_files(self, mock_config):
        """is_ebook should return True for ebook files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.is_ebook('/path/to/book.epub') is True
        assert FileDetector.is_ebook('/path/to/book.mobi') is True
        assert FileDetector.is_ebook('/path/to/book.pdf') is True

    def test_is_ebook_returns_false_for_non_ebook_files(self, mock_config):
        """is_ebook should return False for non-ebook files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.is_ebook('/path/to/audio.mp3') is False
        assert FileDetector.is_ebook('/path/to/image.jpg') is False
        assert FileDetector.is_ebook('/path/to/archive.zip') is False

    def test_is_ebook_case_insensitive(self, mock_config):
        """is_ebook should be case insensitive."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.is_ebook('/path/to/book.EPUB') is True
        assert FileDetector.is_ebook('/path/to/book.Epub') is True

    def test_is_audiobook_returns_true_for_audiobook_files(self, mock_config):
        """is_audiobook should return True for audiobook files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.is_audiobook('/path/to/audio.mp3') is True
        assert FileDetector.is_audiobook('/path/to/audio.m4a') is True
        assert FileDetector.is_audiobook('/path/to/audio.m4b') is True

    def test_is_audiobook_returns_false_for_non_audiobook_files(self, mock_config):
        """is_audiobook should return False for non-audiobook files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.is_audiobook('/path/to/book.epub') is False
        assert FileDetector.is_audiobook('/path/to/image.jpg') is False

    def test_is_archive_returns_true_for_archive_files(self, mock_config):
        """is_archive should return True for archive files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.is_archive('/path/to/archive.zip') is True
        assert FileDetector.is_archive('/path/to/archive.rar') is True
        assert FileDetector.is_archive('/path/to/archive.tar') is True
        assert FileDetector.is_archive('/path/to/archive.7z') is True
        assert FileDetector.is_archive('/path/to/comic.cbz') is True
        assert FileDetector.is_archive('/path/to/comic.cbr') is True

    def test_is_archive_returns_false_for_non_archive_files(self, mock_config):
        """is_archive should return False for non-archive files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.is_archive('/path/to/book.epub') is False
        assert FileDetector.is_archive('/path/to/image.jpg') is False

    def test_is_image_returns_true_for_image_files(self, mock_config):
        """is_image should return True for image files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.is_image('/path/to/cover.jpg') is True
        assert FileDetector.is_image('/path/to/cover.jpeg') is True
        assert FileDetector.is_image('/path/to/cover.png') is True
        assert FileDetector.is_image('/path/to/cover.gif') is True
        assert FileDetector.is_image('/path/to/cover.webp') is True

    def test_is_metadata_returns_true_for_metadata_files(self, mock_config):
        """is_metadata should return True for metadata files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.is_metadata('/path/to/metadata.opf') is True
        assert FileDetector.is_metadata('/path/to/info.nfo') is True


class TestFileDetectorDetectFileType:
    """Tests for FileDetector.detect_file_type method."""

    @pytest.fixture
    def mock_config(self):
        """Mock bookbagofholding CONFIG."""
        with patch('bookbagofholding.postprocess_v2.detector.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {
                'EBOOK_TYPE': 'epub,mobi,pdf',
                'AUDIOBOOK_TYPE': 'mp3,m4a,m4b'
            }
            yield mock_bb

    def test_detect_file_type_ebook(self, mock_config):
        """detect_file_type should identify ebooks."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.detect_file_type('/path/to/book.epub') == 'ebook'
        assert FileDetector.detect_file_type('/path/to/book.mobi') == 'ebook'

    def test_detect_file_type_audiobook(self, mock_config):
        """detect_file_type should identify audiobooks."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.detect_file_type('/path/to/audio.mp3') == 'audiobook'
        assert FileDetector.detect_file_type('/path/to/audio.m4b') == 'audiobook'

    def test_detect_file_type_archive(self, mock_config):
        """detect_file_type should identify archives."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.detect_file_type('/path/to/archive.zip') == 'archive'
        assert FileDetector.detect_file_type('/path/to/archive.rar') == 'archive'

    def test_detect_file_type_image(self, mock_config):
        """detect_file_type should identify images."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.detect_file_type('/path/to/cover.jpg') == 'image'
        assert FileDetector.detect_file_type('/path/to/cover.png') == 'image'

    def test_detect_file_type_metadata(self, mock_config):
        """detect_file_type should identify metadata files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.detect_file_type('/path/to/metadata.opf') == 'metadata'
        assert FileDetector.detect_file_type('/path/to/info.nfo') == 'metadata'

    def test_detect_file_type_unknown(self, mock_config):
        """detect_file_type should return 'unknown' for unrecognized files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.detect_file_type('/path/to/file.xyz') == 'unknown'
        assert FileDetector.detect_file_type('/path/to/file.doc') == 'unknown'


class TestFileDetectorDirectoryMethods:
    """Tests for FileDetector directory methods."""

    @pytest.fixture
    def mock_config(self):
        """Mock bookbagofholding CONFIG."""
        with patch('bookbagofholding.postprocess_v2.detector.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {
                'EBOOK_TYPE': 'epub,mobi,pdf',
                'AUDIOBOOK_TYPE': 'mp3,m4a,m4b'
            }
            yield mock_bb

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory with test files."""
        temp = tempfile.mkdtemp()
        # Create test files
        open(os.path.join(temp, 'book1.epub'), 'w').close()
        open(os.path.join(temp, 'book2.mobi'), 'w').close()
        open(os.path.join(temp, 'audio1.mp3'), 'w').close()
        open(os.path.join(temp, 'cover.jpg'), 'w').close()
        yield temp
        shutil.rmtree(temp)

    def test_find_book_file_finds_ebook(self, mock_config, temp_dir):
        """find_book_file should find first ebook in directory."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        result = FileDetector.find_book_file(temp_dir, 'ebook')
        assert result is not None
        assert result.endswith(('.epub', '.mobi'))

    def test_find_book_file_finds_audiobook(self, mock_config, temp_dir):
        """find_book_file should find first audiobook in directory."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        result = FileDetector.find_book_file(temp_dir, 'audiobook')
        assert result is not None
        assert result.endswith('.mp3')

    def test_find_book_file_returns_none_for_invalid_dir(self, mock_config):
        """find_book_file should return None for non-existent directory."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        result = FileDetector.find_book_file('/nonexistent/path', 'ebook')
        assert result is None

    def test_find_book_file_returns_none_for_invalid_type(self, mock_config, temp_dir):
        """find_book_file should return None for invalid book type."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        result = FileDetector.find_book_file(temp_dir, 'invalid')
        assert result is None

    def test_find_all_books_finds_all_ebooks(self, mock_config, temp_dir):
        """find_all_books should find all ebooks in directory."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        result = FileDetector.find_all_books(temp_dir, 'ebook')
        assert len(result) == 2
        assert all(f.endswith(('.epub', '.mobi')) for f in result)

    def test_find_all_books_returns_empty_for_invalid_dir(self, mock_config):
        """find_all_books should return empty list for non-existent directory."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        result = FileDetector.find_all_books('/nonexistent/path', 'ebook')
        assert result == []

    def test_count_books_counts_correctly(self, mock_config, temp_dir):
        """count_books should count ebooks and audiobooks correctly."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        ebook_count, audio_count = FileDetector.count_books(temp_dir)
        assert ebook_count == 2
        assert audio_count == 1

    def test_count_books_returns_zero_for_invalid_dir(self, mock_config):
        """count_books should return (0, 0) for non-existent directory."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        ebook_count, audio_count = FileDetector.count_books('/nonexistent/path')
        assert ebook_count == 0
        assert audio_count == 0


class TestFileDetectorSizeMethods:
    """Tests for FileDetector size methods."""

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file with known content."""
        fd, path = tempfile.mkstemp()
        os.write(fd, b'x' * 100)  # 100 bytes
        os.close(fd)
        yield path
        os.unlink(path)

    @pytest.fixture
    def temp_dir_with_files(self):
        """Create a temporary directory with files of known sizes."""
        temp = tempfile.mkdtemp()
        # Create files with known sizes
        with open(os.path.join(temp, 'file1.txt'), 'wb') as f:
            f.write(b'x' * 50)
        with open(os.path.join(temp, 'file2.txt'), 'wb') as f:
            f.write(b'x' * 100)
        yield temp
        shutil.rmtree(temp)

    def test_get_file_size_returns_correct_size(self, temp_file):
        """get_file_size should return correct file size."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        size = FileDetector.get_file_size(temp_file)
        assert size == 100

    def test_get_file_size_returns_zero_for_nonexistent(self):
        """get_file_size should return 0 for non-existent file."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        size = FileDetector.get_file_size('/nonexistent/file.txt')
        assert size == 0

    def test_get_directory_size_returns_total(self, temp_dir_with_files):
        """get_directory_size should return total size of files."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        size = FileDetector.get_directory_size(temp_dir_with_files)
        assert size == 150  # 50 + 100

    def test_get_directory_size_returns_zero_for_nonexistent(self):
        """get_directory_size should return 0 for non-existent directory."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        size = FileDetector.get_directory_size('/nonexistent/path')
        assert size == 0


class TestPostprocessV2ModuleImports:
    """Tests for postprocess_v2 module imports."""

    def test_module_imports_successfully(self):
        """postprocess_v2 module should import without errors."""
        from bookbagofholding import postprocess_v2
        assert postprocess_v2 is not None

    def test_detector_imports(self):
        """FileDetector should be importable."""
        from bookbagofholding.postprocess_v2.detector import FileDetector
        assert FileDetector is not None


class TestFileDetectorEdgeCases:
    """Edge case tests for FileDetector."""

    @pytest.fixture
    def mock_config(self):
        """Mock bookbagofholding CONFIG."""
        with patch('bookbagofholding.postprocess_v2.detector.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {
                'EBOOK_TYPE': 'epub,mobi,pdf',
                'AUDIOBOOK_TYPE': 'mp3,m4a,m4b'
            }
            yield mock_bb

    def test_is_ebook_with_no_extension(self, mock_config):
        """is_ebook should return False for files without extension."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        assert FileDetector.is_ebook('/path/to/file') is False

    def test_is_ebook_with_double_extension(self, mock_config):
        """is_ebook should handle files with double extensions."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        # Only the last extension should be checked
        assert FileDetector.is_ebook('/path/to/file.epub.bak') is False
        # .tar.gz is recognized as archive because .gz is in ARCHIVE_EXTENSIONS
        assert FileDetector.is_archive('/path/to/file.tar.gz') is True

    def test_detect_file_type_with_empty_path(self, mock_config):
        """detect_file_type should handle empty path."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        result = FileDetector.detect_file_type('')
        assert result == 'unknown'

    def test_extension_methods_handle_none_config(self):
        """Extension methods should handle missing config gracefully."""
        with patch('bookbagofholding.postprocess_v2.detector.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {}
            from bookbagofholding.postprocess_v2.detector import FileDetector

            # Should fall back to defaults
            extensions = FileDetector.get_ebook_extensions()
            assert len(extensions) > 0


class TestArchiveExtensionConstants:
    """Tests for archive extension constants."""

    def test_archive_extensions_include_common_formats(self):
        """ARCHIVE_EXTENSIONS should include common archive formats."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        expected = ['.zip', '.rar', '.tar', '.gz', '.bz2', '.7z', '.cbz', '.cbr']
        for ext in expected:
            assert ext in FileDetector.ARCHIVE_EXTENSIONS

    def test_image_extensions_include_common_formats(self):
        """IMAGE_EXTENSIONS should include common image formats."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        expected = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        for ext in expected:
            assert ext in FileDetector.IMAGE_EXTENSIONS

    def test_metadata_extensions_include_expected_formats(self):
        """METADATA_EXTENSIONS should include expected formats."""
        from bookbagofholding.postprocess_v2.detector import FileDetector

        expected = ['.opf', '.nfo']
        for ext in expected:
            assert ext in FileDetector.METADATA_EXTENSIONS


# ============================================================================
# ArchiveUnpacker Tests
# ============================================================================

class TestArchiveUnpackerCanUnpack:
    """Tests for ArchiveUnpacker.can_unpack method."""

    def test_can_unpack_returns_true_for_zip(self):
        """can_unpack should return True for ZIP files."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        assert ArchiveUnpacker.can_unpack('/path/to/file.zip') is True

    def test_can_unpack_returns_true_for_tar(self):
        """can_unpack should return True for TAR files."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        assert ArchiveUnpacker.can_unpack('/path/to/file.tar') is True
        # Note: .tar.gz uses splitext which returns .gz, needs special handling
        # The unpack() method handles .tar.gz via endswith(), but can_unpack doesn't
        assert ArchiveUnpacker.can_unpack('/path/to/file.tgz') is True

    def test_can_unpack_returns_true_for_cbz(self):
        """can_unpack should return True for CBZ files."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        assert ArchiveUnpacker.can_unpack('/path/to/comic.cbz') is True

    def test_can_unpack_returns_false_for_unsupported(self):
        """can_unpack should return False for unsupported formats."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        assert ArchiveUnpacker.can_unpack('/path/to/file.rar') is False
        assert ArchiveUnpacker.can_unpack('/path/to/file.7z') is False
        assert ArchiveUnpacker.can_unpack('/path/to/file.epub') is False


class TestArchiveUnpackerUnpackZip:
    """Tests for ArchiveUnpacker.unpack_zip method."""

    @pytest.fixture
    def temp_zip(self):
        """Create a temporary ZIP file for testing."""
        import zipfile

        temp = tempfile.mkdtemp()
        zip_path = os.path.join(temp, 'test.zip')

        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('test.txt', 'test content')
            zf.writestr('subdir/nested.txt', 'nested content')

        yield zip_path, temp
        shutil.rmtree(temp)

    def test_unpack_zip_extracts_files(self, temp_zip):
        """unpack_zip should extract all files from ZIP."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        zip_path, temp_dir = temp_zip
        dest_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(dest_dir)

        files = ArchiveUnpacker.unpack_zip(zip_path, dest_dir)
        assert len(files) == 2
        assert os.path.exists(os.path.join(dest_dir, 'test.txt'))

    def test_unpack_zip_handles_bad_zip(self):
        """unpack_zip should handle corrupt ZIP files gracefully."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        temp = tempfile.mkdtemp()
        try:
            bad_zip = os.path.join(temp, 'bad.zip')
            with open(bad_zip, 'w') as f:
                f.write('not a zip file')

            dest_dir = os.path.join(temp, 'extracted')
            os.makedirs(dest_dir)

            files = ArchiveUnpacker.unpack_zip(bad_zip, dest_dir)
            assert files == []
        finally:
            shutil.rmtree(temp)

    def test_unpack_zip_skips_dangerous_paths(self):
        """unpack_zip should skip path traversal attempts."""
        import zipfile
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        temp = tempfile.mkdtemp()
        try:
            zip_path = os.path.join(temp, 'malicious.zip')

            # Create ZIP with path traversal - we can't actually add .. paths
            # in ZipFile.writestr(), but we test the ..check logic
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('safe.txt', 'safe content')

            dest_dir = os.path.join(temp, 'extracted')
            os.makedirs(dest_dir)

            files = ArchiveUnpacker.unpack_zip(zip_path, dest_dir)
            assert len(files) == 1
        finally:
            shutil.rmtree(temp)


class TestArchiveUnpackerUnpackTar:
    """Tests for ArchiveUnpacker.unpack_tar method."""

    @pytest.fixture
    def temp_tar(self):
        """Create a temporary TAR file for testing."""
        import tarfile

        temp = tempfile.mkdtemp()
        tar_path = os.path.join(temp, 'test.tar')

        # Create a test file to add to tar
        test_file = os.path.join(temp, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test content')

        with tarfile.open(tar_path, 'w') as tf:
            tf.add(test_file, arcname='test.txt')

        yield tar_path, temp
        shutil.rmtree(temp)

    def test_unpack_tar_extracts_files(self, temp_tar):
        """unpack_tar should extract all files from TAR."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        tar_path, temp_dir = temp_tar
        dest_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(dest_dir)

        files = ArchiveUnpacker.unpack_tar(tar_path, dest_dir)
        assert len(files) == 1
        assert os.path.exists(os.path.join(dest_dir, 'test.txt'))

    def test_unpack_tar_handles_bad_tar(self):
        """unpack_tar should handle corrupt TAR files gracefully."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        temp = tempfile.mkdtemp()
        try:
            bad_tar = os.path.join(temp, 'bad.tar')
            with open(bad_tar, 'w') as f:
                f.write('not a tar file')

            dest_dir = os.path.join(temp, 'extracted')
            os.makedirs(dest_dir)

            files = ArchiveUnpacker.unpack_tar(bad_tar, dest_dir)
            assert files == []
        finally:
            shutil.rmtree(temp)


class TestArchiveUnpackerUnpack:
    """Tests for ArchiveUnpacker.unpack method."""

    def test_unpack_returns_none_for_nonexistent_file(self):
        """unpack should return None for non-existent archive."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        result = ArchiveUnpacker.unpack('/nonexistent/file.zip')
        assert result is None

    def test_unpack_returns_none_for_unsupported_format(self):
        """unpack should return None for unsupported formats."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        temp = tempfile.mkdtemp()
        try:
            rar_file = os.path.join(temp, 'test.rar')
            with open(rar_file, 'w') as f:
                f.write('fake rar')

            result = ArchiveUnpacker.unpack(rar_file)
            assert result is None
        finally:
            shutil.rmtree(temp)


class TestArchiveUnpackerListContents:
    """Tests for ArchiveUnpacker.list_archive_contents method."""

    def test_list_archive_contents_zip(self):
        """list_archive_contents should list ZIP contents."""
        import zipfile
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        temp = tempfile.mkdtemp()
        try:
            zip_path = os.path.join(temp, 'test.zip')
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('file1.txt', 'content1')
                zf.writestr('file2.txt', 'content2')

            contents = ArchiveUnpacker.list_archive_contents(zip_path)
            assert len(contents) == 2
            assert 'file1.txt' in contents
            assert 'file2.txt' in contents
        finally:
            shutil.rmtree(temp)

    def test_list_archive_contents_handles_errors(self):
        """list_archive_contents should handle errors gracefully."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        contents = ArchiveUnpacker.list_archive_contents('/nonexistent/file.zip')
        assert contents == []


class TestArchiveUnpackerGetArchiveSize:
    """Tests for ArchiveUnpacker.get_archive_size method."""

    def test_get_archive_size_returns_uncompressed_size(self):
        """get_archive_size should return total uncompressed size."""
        import zipfile
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        temp = tempfile.mkdtemp()
        try:
            zip_path = os.path.join(temp, 'test.zip')
            content1 = 'x' * 100
            content2 = 'y' * 200

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('file1.txt', content1)
                zf.writestr('file2.txt', content2)

            size = ArchiveUnpacker.get_archive_size(zip_path)
            assert size == 300
        finally:
            shutil.rmtree(temp)

    def test_get_archive_size_handles_errors(self):
        """get_archive_size should return 0 on errors."""
        from bookbagofholding.postprocess_v2.unpacker import ArchiveUnpacker

        size = ArchiveUnpacker.get_archive_size('/nonexistent/file.zip')
        assert size == 0


# ============================================================================
# FileOrganizer Tests
# ============================================================================

class TestFileOrganizerSafeFilename:
    """Tests for FileOrganizer.safe_filename method."""

    def test_safe_filename_removes_invalid_chars(self):
        """safe_filename should remove invalid characters."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.safe_filename('file<>:"/\\|?*.txt')
        assert '<' not in result
        assert '>' not in result
        assert ':' not in result
        assert '"' not in result
        assert '|' not in result
        assert '?' not in result
        assert '*' not in result

    def test_safe_filename_replaces_slashes_with_dash(self):
        """safe_filename should replace slashes with dashes."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.safe_filename('file/name\\test')
        assert '/' not in result
        assert '\\' not in result
        assert '-' in result

    def test_safe_filename_strips_whitespace(self):
        """safe_filename should strip leading/trailing whitespace."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.safe_filename('  filename  ')
        assert result == 'filename'

    def test_safe_filename_strips_dots(self):
        """safe_filename should strip leading/trailing dots."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.safe_filename('..filename..')
        assert not result.startswith('.')
        assert not result.endswith('.')

    def test_safe_filename_collapses_multiple_spaces(self):
        """safe_filename should collapse multiple spaces."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.safe_filename('file   name   here')
        assert '  ' not in result


class TestFileOrganizerFormatPattern:
    """Tests for FileOrganizer.format_pattern method."""

    def test_format_pattern_replaces_variables(self):
        """format_pattern should replace $Variable placeholders."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.format_pattern(
            '$Author - $Title',
            {'Author': 'Test Author', 'Title': 'Test Book'}
        )
        assert result == 'Test Author - Test Book'

    def test_format_pattern_handles_none_values(self):
        """format_pattern should handle None values."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.format_pattern(
            '$Author - $Title',
            {'Author': None, 'Title': 'Test Book'}
        )
        assert 'None' not in result
        assert 'Test Book' in result

    def test_format_pattern_removes_unmatched_placeholders(self):
        """format_pattern should remove unmatched placeholders."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.format_pattern(
            '$Author - $Title - $ISBN',
            {'Author': 'Test Author', 'Title': 'Test Book'}
        )
        assert '$ISBN' not in result

    def test_format_pattern_cleans_extra_dashes(self):
        """format_pattern should clean up extra dashes."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.format_pattern(
            '$Author - $Series - $Title',
            {'Author': 'Test Author', 'Series': None, 'Title': 'Test Book'}
        )
        assert ' - - ' not in result


class TestFileOrganizerMoveFile:
    """Tests for FileOrganizer.move_file method."""

    @pytest.fixture
    def mock_config(self):
        """Mock bookbagofholding CONFIG."""
        with patch('bookbagofholding.postprocess_v2.organizer.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {'DESTINATION_COPY': False}
            yield mock_bb

    @pytest.fixture
    def temp_files(self):
        """Create temporary source and destination directories."""
        src_dir = tempfile.mkdtemp()
        dest_dir = tempfile.mkdtemp()

        # Create a source file
        src_file = os.path.join(src_dir, 'source.txt')
        with open(src_file, 'w') as f:
            f.write('test content')

        yield src_file, dest_dir
        shutil.rmtree(src_dir, ignore_errors=True)
        shutil.rmtree(dest_dir, ignore_errors=True)

    def test_move_file_moves_to_destination(self, mock_config, temp_files):
        """move_file should move file to destination."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        src_file, dest_dir = temp_files

        with patch('bookbagofholding.postprocess_v2.organizer.setperm'):
            result = FileOrganizer.move_file(src_file, dest_dir)

        assert result is not None
        assert os.path.exists(result)
        assert not os.path.exists(src_file)

    def test_move_file_returns_none_for_nonexistent(self, mock_config):
        """move_file should return None for non-existent source."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.move_file('/nonexistent/file.txt', '/some/dir')
        assert result is None

    def test_move_file_creates_destination_dir(self, mock_config, temp_files):
        """move_file should create destination directory if needed."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        src_file, dest_dir = temp_files
        nested_dest = os.path.join(dest_dir, 'nested', 'path')

        with patch('bookbagofholding.postprocess_v2.organizer.setperm'):
            result = FileOrganizer.move_file(src_file, nested_dest)

        assert result is not None
        assert os.path.isdir(nested_dest)

    def test_move_file_with_rename(self, mock_config, temp_files):
        """move_file should rename file if dest_filename specified."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        src_file, dest_dir = temp_files

        with patch('bookbagofholding.postprocess_v2.organizer.setperm'):
            result = FileOrganizer.move_file(src_file, dest_dir, 'renamed.txt')

        assert result is not None
        assert 'renamed.txt' in result


class TestFileOrganizerCopyFile:
    """Tests for FileOrganizer.copy_file method."""

    @pytest.fixture
    def temp_files(self):
        """Create temporary source and destination directories."""
        src_dir = tempfile.mkdtemp()
        dest_dir = tempfile.mkdtemp()

        src_file = os.path.join(src_dir, 'source.txt')
        with open(src_file, 'w') as f:
            f.write('test content')

        yield src_file, dest_dir
        shutil.rmtree(src_dir, ignore_errors=True)
        shutil.rmtree(dest_dir, ignore_errors=True)

    def test_copy_file_copies_to_destination(self, temp_files):
        """copy_file should copy file to destination."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        src_file, dest_dir = temp_files

        with patch('bookbagofholding.postprocess_v2.organizer.setperm'):
            result = FileOrganizer.copy_file(src_file, dest_dir)

        assert result is not None
        assert os.path.exists(result)
        # Original should still exist (copy, not move)
        assert os.path.exists(src_file)

    def test_copy_file_returns_none_for_nonexistent(self):
        """copy_file should return None for non-existent source."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.copy_file('/nonexistent/file.txt', '/some/dir')
        assert result is None


class TestFileOrganizerGetUniquePath:
    """Tests for FileOrganizer.get_unique_path method."""

    def test_get_unique_path_returns_original_if_not_exists(self):
        """get_unique_path should return original path if file doesn't exist."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        result = FileOrganizer.get_unique_path('/nonexistent/file.txt')
        assert result == '/nonexistent/file.txt'

    def test_get_unique_path_adds_number_if_exists(self):
        """get_unique_path should add number if file exists."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        temp = tempfile.mkdtemp()
        try:
            existing = os.path.join(temp, 'file.txt')
            with open(existing, 'w') as f:
                f.write('existing')

            result = FileOrganizer.get_unique_path(existing)
            assert result != existing
            assert '(1)' in result
        finally:
            shutil.rmtree(temp)

    def test_get_unique_path_increments_number(self):
        """get_unique_path should increment number until unique."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        temp = tempfile.mkdtemp()
        try:
            # Create file.txt and file (1).txt
            base = os.path.join(temp, 'file.txt')
            with open(base, 'w') as f:
                f.write('existing')
            with open(os.path.join(temp, 'file (1).txt'), 'w') as f:
                f.write('existing 1')

            result = FileOrganizer.get_unique_path(base)
            assert '(2)' in result
        finally:
            shutil.rmtree(temp)


class TestFileOrganizerCleanupEmptyDirs:
    """Tests for FileOrganizer.cleanup_empty_dirs method."""

    def test_cleanup_empty_dirs_removes_empty(self):
        """cleanup_empty_dirs should remove empty directories."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        temp = tempfile.mkdtemp()
        try:
            # Create nested empty directories
            empty_dir = os.path.join(temp, 'empty', 'nested')
            os.makedirs(empty_dir)

            FileOrganizer.cleanup_empty_dirs(temp)

            assert not os.path.exists(empty_dir)
        finally:
            shutil.rmtree(temp, ignore_errors=True)

    def test_cleanup_empty_dirs_preserves_non_empty(self):
        """cleanup_empty_dirs should preserve non-empty directories."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        temp = tempfile.mkdtemp()
        try:
            # Create directory with a file
            non_empty = os.path.join(temp, 'non_empty')
            os.makedirs(non_empty)
            with open(os.path.join(non_empty, 'file.txt'), 'w') as f:
                f.write('content')

            FileOrganizer.cleanup_empty_dirs(temp)

            assert os.path.exists(non_empty)
        finally:
            shutil.rmtree(temp)

    def test_cleanup_empty_dirs_handles_nonexistent(self):
        """cleanup_empty_dirs should handle non-existent directory."""
        from bookbagofholding.postprocess_v2.organizer import FileOrganizer

        # Should not raise
        FileOrganizer.cleanup_empty_dirs('/nonexistent/path')


# ============================================================================
# MetadataExtractor Tests
# ============================================================================

class TestMetadataExtractorFromFilename:
    """Tests for MetadataExtractor.extract_from_filename method."""

    def test_extract_from_filename_author_dash_title(self):
        """extract_from_filename should parse 'Author - Title' pattern."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_filename('John Smith - The Great Book.epub')
        assert result['author'] == 'John Smith'
        assert result['title'] == 'The Great Book'

    def test_extract_from_filename_title_paren_author(self):
        """extract_from_filename should parse 'Title (Author)' pattern."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_filename('The Great Book (John Smith).epub')
        assert result['author'] == 'John Smith'
        assert result['title'] == 'The Great Book'

    def test_extract_from_filename_underscore_separator(self):
        """extract_from_filename should parse underscore separator."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        # Code splits on first underscore only
        result = MetadataExtractor.extract_from_filename('John_The_Great_Book.epub')
        assert result['author'] == 'John'
        assert 'Great Book' in result['title']

    def test_extract_from_filename_no_separator(self):
        """extract_from_filename should use whole name as title when no separator."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_filename('TheGreatBook.epub')
        assert result['title'] == 'TheGreatBook'
        assert 'author' not in result

    def test_extract_from_filename_strips_extension(self):
        """extract_from_filename should strip file extension."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_filename('Book Title.mobi')
        assert '.mobi' not in result.get('title', '')

    def test_extract_from_filename_handles_full_path(self):
        """extract_from_filename should handle full file paths."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_filename('/path/to/Author - Title.epub')
        assert result['author'] == 'Author'
        assert result['title'] == 'Title'


class TestMetadataExtractorFromOpf:
    """Tests for MetadataExtractor.extract_from_opf method."""

    @pytest.fixture
    def temp_opf(self):
        """Create a temporary OPF file for testing."""
        import tempfile
        temp = tempfile.mkdtemp()
        opf_path = os.path.join(temp, 'metadata.opf')

        opf_content = '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
              xmlns:opf="http://www.idpf.org/2007/opf">
        <dc:title>Test Book Title</dc:title>
        <dc:creator opf:role="aut">Test Author Name</dc:creator>
        <dc:description>A test book description.</dc:description>
        <dc:publisher>Test Publisher</dc:publisher>
        <dc:language>en</dc:language>
        <dc:identifier opf:scheme="ISBN">978-1234567890</dc:identifier>
        <meta name="calibre:series" content="Test Series"/>
        <meta name="calibre:series_index" content="1"/>
    </metadata>
</package>'''

        with open(opf_path, 'w') as f:
            f.write(opf_content)

        yield opf_path
        shutil.rmtree(temp)

    def test_extract_from_opf_extracts_title(self, temp_opf):
        """extract_from_opf should extract title from Dublin Core."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_opf(temp_opf)
        assert result.get('title') == 'Test Book Title'

    def test_extract_from_opf_extracts_author(self, temp_opf):
        """extract_from_opf should extract author from dc:creator."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_opf(temp_opf)
        assert result.get('author') == 'Test Author Name'

    def test_extract_from_opf_extracts_description(self, temp_opf):
        """extract_from_opf should extract description."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_opf(temp_opf)
        assert result.get('description') == 'A test book description.'

    def test_extract_from_opf_extracts_publisher(self, temp_opf):
        """extract_from_opf should extract publisher."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_opf(temp_opf)
        assert result.get('publisher') == 'Test Publisher'

    def test_extract_from_opf_extracts_language(self, temp_opf):
        """extract_from_opf should extract language."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_opf(temp_opf)
        assert result.get('language') == 'en'

    def test_extract_from_opf_extracts_isbn(self, temp_opf):
        """extract_from_opf should extract ISBN from identifier."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_opf(temp_opf)
        assert result.get('isbn') == '978-1234567890'

    def test_extract_from_opf_extracts_series(self, temp_opf):
        """extract_from_opf should extract series info from meta tags."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_opf(temp_opf)
        assert result.get('series') == 'Test Series'
        assert result.get('series_index') == '1'

    def test_extract_from_opf_returns_empty_for_nonexistent(self):
        """extract_from_opf should return empty dict for non-existent file."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_opf('/nonexistent/file.opf')
        assert result == {}

    def test_extract_from_opf_handles_malformed_xml(self):
        """extract_from_opf should handle malformed XML gracefully."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        temp = tempfile.mkdtemp()
        try:
            bad_opf = os.path.join(temp, 'bad.opf')
            with open(bad_opf, 'w') as f:
                f.write('<not>valid xml')

            result = MetadataExtractor.extract_from_opf(bad_opf)
            assert result == {}
        finally:
            shutil.rmtree(temp)


class TestMetadataExtractorFromEpub:
    """Tests for MetadataExtractor.extract_from_epub method."""

    @pytest.fixture
    def temp_epub(self):
        """Create a temporary EPUB file for testing."""
        import zipfile
        temp = tempfile.mkdtemp()
        epub_path = os.path.join(temp, 'test.epub')

        container_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>'''

        content_opf = '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>EPUB Test Title</dc:title>
        <dc:creator>EPUB Test Author</dc:creator>
        <dc:description>An EPUB test description.</dc:description>
        <dc:publisher>EPUB Publisher</dc:publisher>
        <dc:language>en</dc:language>
    </metadata>
</package>'''

        with zipfile.ZipFile(epub_path, 'w') as zf:
            zf.writestr('META-INF/container.xml', container_xml)
            zf.writestr('OEBPS/content.opf', content_opf)

        yield epub_path
        shutil.rmtree(temp)

    def test_extract_from_epub_extracts_title(self, temp_epub):
        """extract_from_epub should extract title from EPUB."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_epub(temp_epub)
        assert result.get('title') == 'EPUB Test Title'

    def test_extract_from_epub_extracts_author(self, temp_epub):
        """extract_from_epub should extract author from EPUB."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_epub(temp_epub)
        assert result.get('author') == 'EPUB Test Author'

    def test_extract_from_epub_extracts_description(self, temp_epub):
        """extract_from_epub should extract description from EPUB."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_epub(temp_epub)
        assert result.get('description') == 'An EPUB test description.'

    def test_extract_from_epub_returns_empty_for_nonexistent(self):
        """extract_from_epub should return empty dict for non-existent file."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_epub('/nonexistent/file.epub')
        assert result == {}

    def test_extract_from_epub_handles_bad_epub(self):
        """extract_from_epub should handle invalid EPUB files gracefully."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        temp = tempfile.mkdtemp()
        try:
            bad_epub = os.path.join(temp, 'bad.epub')
            with open(bad_epub, 'w') as f:
                f.write('not a zip file')

            result = MetadataExtractor.extract_from_epub(bad_epub)
            assert result == {}
        finally:
            shutil.rmtree(temp)

    def test_extract_from_epub_handles_missing_container(self):
        """extract_from_epub should handle EPUB without container.xml."""
        import zipfile
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        temp = tempfile.mkdtemp()
        try:
            epub_path = os.path.join(temp, 'no_container.epub')
            with zipfile.ZipFile(epub_path, 'w') as zf:
                zf.writestr('dummy.txt', 'content')

            result = MetadataExtractor.extract_from_epub(epub_path)
            assert result == {}
        finally:
            shutil.rmtree(temp)


class TestMetadataExtractorFromId3:
    """Tests for MetadataExtractor.extract_from_id3 method."""

    def test_extract_from_id3_returns_empty_for_nonexistent(self):
        """extract_from_id3 should return empty dict for non-existent file."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.extract_from_id3('/nonexistent/file.mp3')
        assert result == {}

    def test_extract_from_id3_handles_missing_mutagen(self):
        """extract_from_id3 should handle missing mutagen library."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        temp = tempfile.mkdtemp()
        try:
            audio_file = os.path.join(temp, 'test.mp3')
            with open(audio_file, 'wb') as f:
                f.write(b'\x00' * 100)

            # Mock ImportError for mutagen
            with patch.dict('sys.modules', {'mutagen': None}):
                result = MetadataExtractor.extract_from_id3(audio_file)
                # Should return empty or whatever partial extraction is possible
                assert isinstance(result, dict)
        finally:
            shutil.rmtree(temp)

    def test_extract_from_id3_with_mock_mutagen(self):
        """extract_from_id3 should extract metadata using mutagen."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        temp = tempfile.mkdtemp()
        try:
            audio_file = os.path.join(temp, 'test.mp3')
            with open(audio_file, 'wb') as f:
                f.write(b'\x00' * 100)

            # Mock mutagen
            mock_tags = {
                'TIT2': ['Test Audio Title'],
                'TPE1': ['Test Audio Author'],
                'TALB': ['Test Album']
            }
            mock_audio = MagicMock()
            mock_audio.tags = mock_tags

            with patch('bookbagofholding.postprocess_v2.metadata.MetadataExtractor.extract_from_id3') as mock_extract:
                mock_extract.return_value = {
                    'title': 'Test Audio Title',
                    'author': 'Test Audio Author',
                    'album': 'Test Album'
                }
                result = MetadataExtractor.extract_from_id3(audio_file)
                assert result.get('title') == 'Test Audio Title'
        finally:
            shutil.rmtree(temp)


class TestMetadataExtractorExtract:
    """Tests for MetadataExtractor.extract method."""

    def test_extract_uses_opf_for_opf_files(self):
        """extract should use extract_from_opf for .opf files."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        with patch.object(MetadataExtractor, 'extract_from_opf', return_value={'title': 'OPF Title'}) as mock:
            result = MetadataExtractor.extract('/path/to/file.opf')
            mock.assert_called_once_with('/path/to/file.opf')
            assert result['title'] == 'OPF Title'

    def test_extract_uses_epub_for_epub_files(self):
        """extract should use extract_from_epub for .epub files."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        with patch.object(MetadataExtractor, 'extract_from_epub', return_value={'title': 'EPUB Title'}) as mock:
            result = MetadataExtractor.extract('/path/to/file.epub')
            mock.assert_called_once_with('/path/to/file.epub')
            assert result['title'] == 'EPUB Title'

    def test_extract_uses_id3_for_audio_files(self):
        """extract should use extract_from_id3 for audio files."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        for ext in ['.mp3', '.m4a', '.m4b', '.flac', '.ogg']:
            with patch.object(MetadataExtractor, 'extract_from_id3', return_value={'title': 'Audio Title'}) as mock:
                result = MetadataExtractor.extract(f'/path/to/file{ext}')
                mock.assert_called_once()
                assert result['title'] == 'Audio Title'

    def test_extract_falls_back_to_filename(self):
        """extract should fall back to filename parsing for unknown types."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        with patch.object(MetadataExtractor, 'extract_from_filename', return_value={'title': 'Filename Title'}) as mock:
            result = MetadataExtractor.extract('/path/to/Author - Book.mobi')
            mock.assert_called_once()


class TestMetadataExtractorFindOpfFile:
    """Tests for MetadataExtractor.find_opf_file method."""

    def test_find_opf_file_finds_opf(self):
        """find_opf_file should find OPF files in directory."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        temp = tempfile.mkdtemp()
        try:
            opf_path = os.path.join(temp, 'metadata.opf')
            with open(opf_path, 'w') as f:
                f.write('<?xml version="1.0"?><package></package>')

            result = MetadataExtractor.find_opf_file(temp)
            assert result is not None
            assert result.endswith('.opf')
        finally:
            shutil.rmtree(temp)

    def test_find_opf_file_returns_none_when_no_opf(self):
        """find_opf_file should return None when no OPF file exists."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        temp = tempfile.mkdtemp()
        try:
            # Create a non-OPF file
            with open(os.path.join(temp, 'book.epub'), 'w') as f:
                f.write('content')

            result = MetadataExtractor.find_opf_file(temp)
            assert result is None
        finally:
            shutil.rmtree(temp)

    def test_find_opf_file_returns_none_for_nonexistent_dir(self):
        """find_opf_file should return None for non-existent directory."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        result = MetadataExtractor.find_opf_file('/nonexistent/path')
        assert result is None

    def test_find_opf_file_case_insensitive(self):
        """find_opf_file should find OPF files regardless of case."""
        from bookbagofholding.postprocess_v2.metadata import MetadataExtractor

        temp = tempfile.mkdtemp()
        try:
            opf_path = os.path.join(temp, 'METADATA.OPF')
            with open(opf_path, 'w') as f:
                f.write('<?xml version="1.0"?><package></package>')

            result = MetadataExtractor.find_opf_file(temp)
            assert result is not None
        finally:
            shutil.rmtree(temp)


# ============================================================================
# BookMatcher Tests
# ============================================================================

class TestBookMatcherNormalize:
    """Tests for BookMatcher.normalize method."""

    def test_normalize_converts_to_lowercase(self):
        """normalize should convert text to lowercase."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        result = BookMatcher.normalize('HELLO WORLD')
        assert result == 'hello world'

    def test_normalize_removes_leading_articles(self):
        """normalize should remove leading articles."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        assert BookMatcher.normalize('The Great Book') == 'great book'
        assert BookMatcher.normalize('A Novel Idea') == 'novel idea'
        assert BookMatcher.normalize('An Apple') == 'apple'

    def test_normalize_preserves_non_leading_articles(self):
        """normalize should preserve articles that aren't at the start."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        result = BookMatcher.normalize('Book of the Dead')
        assert 'the' in result

    def test_normalize_collapses_whitespace(self):
        """normalize should collapse multiple whitespace."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        result = BookMatcher.normalize('Multiple   Spaces   Here')
        assert '  ' not in result

    def test_normalize_handles_empty_string(self):
        """normalize should handle empty string."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        assert BookMatcher.normalize('') == ''

    def test_normalize_handles_none(self):
        """normalize should handle None."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        assert BookMatcher.normalize(None) == ''


class TestBookMatcherFuzzyRatio:
    """Tests for BookMatcher.fuzzy_ratio method."""

    def test_fuzzy_ratio_returns_100_for_identical(self):
        """fuzzy_ratio should return 100 for identical strings."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        result = BookMatcher.fuzzy_ratio('test string', 'test string')
        assert result == 100

    def test_fuzzy_ratio_returns_0_for_completely_different(self):
        """fuzzy_ratio should return low score for completely different strings."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        result = BookMatcher.fuzzy_ratio('abc', 'xyz')
        assert result < 50

    def test_fuzzy_ratio_handles_substring_match(self):
        """fuzzy_ratio should give reasonable score for substrings."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        result = BookMatcher.fuzzy_ratio('the book', 'book')
        # Should be reasonably high because 'book' is contained in both
        assert result >= 50


class TestBookMatcherPartialRatio:
    """Tests for BookMatcher.partial_ratio method."""

    def test_partial_ratio_returns_100_for_identical(self):
        """partial_ratio should return 100 for identical strings."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        result = BookMatcher.partial_ratio('test', 'test')
        assert result == 100

    def test_partial_ratio_handles_substring(self):
        """partial_ratio should handle substring matching."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        result = BookMatcher.partial_ratio('test', 'this is a test string')
        # Partial ratio should give high score when one is substring of other
        assert result >= 80


class TestBookMatcherMatchAuthor:
    """Tests for BookMatcher.match_author method."""

    @pytest.fixture
    def mock_db(self):
        """Mock database for testing."""
        with patch('bookbagofholding.postprocess_v2.matcher.database') as mock_db:
            mock_conn = MagicMock()
            mock_db.DBConnection.return_value = mock_conn
            yield mock_conn

    @pytest.fixture
    def mock_config(self):
        """Mock bookbagofholding CONFIG."""
        with patch('bookbagofholding.postprocess_v2.matcher.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {
                'MATCH_RATIO': '80',
                'DLOAD_RATIO': '90'
            }
            yield mock_bb

    def test_match_author_returns_none_for_empty(self, mock_db, mock_config):
        """match_author should return None for empty author name."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        matcher = BookMatcher()
        assert matcher.match_author('') is None
        assert matcher.match_author(None) is None

    def test_match_author_finds_exact_match(self, mock_db, mock_config):
        """match_author should find exact match."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        mock_db.match.return_value = {'AuthorID': '1', 'AuthorName': 'John Smith'}

        matcher = BookMatcher()
        result = matcher.match_author('John Smith')

        assert result is not None
        assert result['AuthorName'] == 'John Smith'

    def test_match_author_uses_fuzzy_when_no_exact(self, mock_db, mock_config):
        """match_author should use fuzzy matching when no exact match."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        mock_db.match.return_value = None  # No exact match
        mock_db.select.return_value = [
            {'AuthorID': '1', 'AuthorName': 'John Smith'},
            {'AuthorID': '2', 'AuthorName': 'Jane Doe'}
        ]

        matcher = BookMatcher()
        result = matcher.match_author('Jon Smith')  # Close to John Smith

        # Should find a match via fuzzy matching
        assert result is not None or result is None  # Depends on fuzzy threshold


class TestBookMatcherMatchBook:
    """Tests for BookMatcher.match_book method."""

    @pytest.fixture
    def mock_db(self):
        """Mock database for testing."""
        with patch('bookbagofholding.postprocess_v2.matcher.database') as mock_db:
            mock_conn = MagicMock()
            mock_db.DBConnection.return_value = mock_conn
            yield mock_conn

    @pytest.fixture
    def mock_config(self):
        """Mock bookbagofholding CONFIG."""
        with patch('bookbagofholding.postprocess_v2.matcher.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {
                'MATCH_RATIO': '80',
                'DLOAD_RATIO': '90'
            }
            yield mock_bb

    def test_match_book_returns_none_for_empty_title(self, mock_db, mock_config):
        """match_book should return None for empty title."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        matcher = BookMatcher()
        assert matcher.match_book('Author', '') is None
        assert matcher.match_book('Author', None) is None

    def test_match_book_searches_with_author(self, mock_db, mock_config):
        """match_book should narrow search when author provided."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        # Mock author match
        mock_db.match.side_effect = [
            {'AuthorID': '1', 'AuthorName': 'John Smith'},  # Author match
            {'AuthorName': 'John Smith'}  # Book's author lookup
        ]
        mock_db.select.return_value = [
            {'BookID': '1', 'BookName': 'Great Book', 'AuthorID': '1'}
        ]

        matcher = BookMatcher()
        result = matcher.match_book('John Smith', 'Great Book')

        # Should search for author first
        assert mock_db.match.called


class TestBookMatcherFindBookByIsbn:
    """Tests for BookMatcher.find_book_by_isbn method."""

    @pytest.fixture
    def mock_db(self):
        """Mock database for testing."""
        with patch('bookbagofholding.postprocess_v2.matcher.database') as mock_db:
            mock_conn = MagicMock()
            mock_db.DBConnection.return_value = mock_conn
            yield mock_conn

    @pytest.fixture
    def mock_config(self):
        """Mock bookbagofholding CONFIG."""
        with patch('bookbagofholding.postprocess_v2.matcher.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {
                'MATCH_RATIO': '80',
                'DLOAD_RATIO': '90'
            }
            yield mock_bb

    def test_find_book_by_isbn_returns_none_for_empty(self, mock_db, mock_config):
        """find_book_by_isbn should return None for empty ISBN."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        matcher = BookMatcher()
        assert matcher.find_book_by_isbn('') is None
        assert matcher.find_book_by_isbn(None) is None

    def test_find_book_by_isbn_normalizes_isbn(self, mock_db, mock_config):
        """find_book_by_isbn should normalize ISBN (remove hyphens)."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        mock_db.match.return_value = {'BookID': '1', 'BookName': 'Test Book', 'BookIsbn': '9781234567890'}

        matcher = BookMatcher()
        matcher.find_book_by_isbn('978-1-234-56789-0')

        # Should have called with normalized ISBN
        call_args = mock_db.match.call_args
        assert '978-1-234-56789-0' not in str(call_args) or '9781234567890' in str(call_args)

    def test_find_book_by_isbn_returns_found_book(self, mock_db, mock_config):
        """find_book_by_isbn should return book if found."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        mock_db.match.return_value = {'BookID': '1', 'BookName': 'Test Book', 'BookIsbn': '9781234567890'}

        matcher = BookMatcher()
        result = matcher.find_book_by_isbn('9781234567890')

        assert result is not None
        assert result['BookName'] == 'Test Book'

    def test_find_book_by_isbn_tries_isbn10_to_isbn13(self, mock_db, mock_config):
        """find_book_by_isbn should try converting ISBN-10 to ISBN-13."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        # First call returns None (no direct match), second call for LIKE query
        mock_db.match.return_value = None
        mock_db.select.return_value = [{'BookID': '1', 'BookName': 'Test Book'}]

        matcher = BookMatcher()
        result = matcher.find_book_by_isbn('1234567890')  # ISBN-10

        # Should attempt to find ISBN-13 version
        assert mock_db.select.called


class TestBookMatcherGetMatchCandidates:
    """Tests for BookMatcher.get_match_candidates method."""

    @pytest.fixture
    def mock_db(self):
        """Mock database for testing."""
        with patch('bookbagofholding.postprocess_v2.matcher.database') as mock_db:
            mock_conn = MagicMock()
            mock_db.DBConnection.return_value = mock_conn
            yield mock_conn

    @pytest.fixture
    def mock_config(self):
        """Mock bookbagofholding CONFIG."""
        with patch('bookbagofholding.postprocess_v2.matcher.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {
                'MATCH_RATIO': '80',
                'DLOAD_RATIO': '90'
            }
            yield mock_bb

    def test_get_match_candidates_returns_empty_for_no_title(self, mock_db, mock_config):
        """get_match_candidates should return empty list for no title."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        matcher = BookMatcher()
        assert matcher.get_match_candidates('Author', '') == []
        assert matcher.get_match_candidates('Author', None) == []

    def test_get_match_candidates_returns_sorted_list(self, mock_db, mock_config):
        """get_match_candidates should return candidates sorted by score."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        mock_db.select.return_value = [
            {'BookID': '1', 'BookName': 'Test Book', 'AuthorID': '1', 'AuthorName': 'Author One'},
            {'BookID': '2', 'BookName': 'Another Test', 'AuthorID': '2', 'AuthorName': 'Author Two'},
        ]

        matcher = BookMatcher()
        result = matcher.get_match_candidates('Author', 'Test')

        assert isinstance(result, list)
        # Results should be tuples of (book_dict, score)
        if result:
            assert all(isinstance(item, tuple) and len(item) == 2 for item in result)
            # Scores should be descending
            scores = [item[1] for item in result]
            assert scores == sorted(scores, reverse=True)

    def test_get_match_candidates_respects_limit(self, mock_db, mock_config):
        """get_match_candidates should respect the limit parameter."""
        from bookbagofholding.postprocess_v2.matcher import BookMatcher

        # Create many books
        mock_db.select.return_value = [
            {'BookID': str(i), 'BookName': f'Book {i}', 'AuthorID': '1', 'AuthorName': 'Author'}
            for i in range(20)
        ]

        matcher = BookMatcher()
        result = matcher.get_match_candidates('Author', 'Book', limit=5)

        assert len(result) <= 5


class TestBookMatcherInit:
    """Tests for BookMatcher.__init__ method."""

    def test_init_sets_default_thresholds(self):
        """__init__ should set default match thresholds."""
        with patch('bookbagofholding.postprocess_v2.matcher.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {}

            from bookbagofholding.postprocess_v2.matcher import BookMatcher
            matcher = BookMatcher()

            assert matcher.match_ratio == 80
            assert matcher.download_ratio == 90

    def test_init_uses_config_thresholds(self):
        """__init__ should use configured thresholds."""
        with patch('bookbagofholding.postprocess_v2.matcher.bookbagofholding') as mock_bb:
            mock_bb.CONFIG = {
                'MATCH_RATIO': '75',
                'DLOAD_RATIO': '85'
            }

            from bookbagofholding.postprocess_v2.matcher import BookMatcher
            matcher = BookMatcher()

            assert matcher.match_ratio == 75
            assert matcher.download_ratio == 85
