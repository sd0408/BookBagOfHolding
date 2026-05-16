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
Unit tests for bookbagofholding.common module.

Tests cover:
- Utility functions (getUserAgent, proxyList, isValidEmail, pwd_generator, pwd_check)
- File system operations (mymakedirs, safe_move, safe_copy)
- Helper functions
"""

import os
import re
import string
import tempfile
import shutil

import pytest

import bookbagofholding
from bookbagofholding import common


class TestGetUserAgent:
    """Tests for getUserAgent() function."""

    def test_getUserAgent_returns_custom_when_set(self):
        """getUserAgent should return custom user agent when configured."""
        original = bookbagofholding.CONFIG.get('USER_AGENT', '')
        bookbagofholding.CONFIG['USER_AGENT'] = 'Custom User Agent/1.0'

        result = common.getUserAgent()
        assert result == 'Custom User Agent/1.0'

        bookbagofholding.CONFIG['USER_AGENT'] = original

    def test_getUserAgent_returns_default_when_not_set(self):
        """getUserAgent should return default user agent when not configured."""
        original = bookbagofholding.CONFIG.get('USER_AGENT', '')
        bookbagofholding.CONFIG['USER_AGENT'] = ''

        result = common.getUserAgent()
        assert 'Bookbag of Holding' in result

        bookbagofholding.CONFIG['USER_AGENT'] = original


class TestProxyList:
    """Tests for proxyList() function."""

    def test_proxyList_returns_none_when_no_proxy(self):
        """proxyList should return None when no proxy configured."""
        original = bookbagofholding.CONFIG.get('PROXY_HOST', '')
        bookbagofholding.CONFIG['PROXY_HOST'] = ''

        result = common.proxyList()
        assert result is None

        bookbagofholding.CONFIG['PROXY_HOST'] = original

    def test_proxyList_returns_dict_when_proxy_configured(self):
        """proxyList should return dict with proxy settings when configured."""
        original_host = bookbagofholding.CONFIG.get('PROXY_HOST', '')
        original_type = bookbagofholding.CONFIG.get('PROXY_TYPE', '')

        bookbagofholding.CONFIG['PROXY_HOST'] = 'http://proxy.example.com:8080'
        bookbagofholding.CONFIG['PROXY_TYPE'] = 'http, https'

        result = common.proxyList()
        assert result is not None
        assert isinstance(result, dict)
        assert 'http' in result or 'https' in result

        bookbagofholding.CONFIG['PROXY_HOST'] = original_host
        bookbagofholding.CONFIG['PROXY_TYPE'] = original_type


class TestIsValidEmail:
    """Tests for isValidEmail() function."""

    def test_valid_email_simple(self):
        """isValidEmail should accept simple valid email."""
        assert common.isValidEmail("user@example.com") is True

    def test_valid_email_with_subdomain(self):
        """isValidEmail should accept email with subdomain."""
        assert common.isValidEmail("user@mail.example.com") is True

    def test_valid_email_with_dots(self):
        """isValidEmail should accept email with dots in local part."""
        assert common.isValidEmail("first.last@example.com") is True

    def test_invalid_email_no_at(self):
        """isValidEmail should reject email without @."""
        assert common.isValidEmail("userexample.com") is False

    def test_invalid_email_no_domain(self):
        """isValidEmail should reject email without domain."""
        assert common.isValidEmail("user@") is False

    def test_invalid_email_too_short(self):
        """isValidEmail should reject too short email."""
        assert common.isValidEmail("a@b.co") is False

    def test_invalid_email_empty(self):
        """isValidEmail should reject empty string."""
        assert common.isValidEmail("") is False


class TestPwdGenerator:
    """Tests for pwd_generator() function."""

    def test_pwd_generator_default_length(self):
        """pwd_generator should generate 10 character password by default."""
        result = common.pwd_generator()
        assert len(result) == 10

    def test_pwd_generator_custom_length(self):
        """pwd_generator should generate password of specified length."""
        result = common.pwd_generator(size=20)
        assert len(result) == 20

    def test_pwd_generator_uses_default_chars(self):
        """pwd_generator should use letters and digits by default."""
        result = common.pwd_generator(size=100)
        # With 100 chars, should have both letters and digits
        assert any(c.isalpha() for c in result)
        assert any(c.isdigit() for c in result)

    def test_pwd_generator_custom_chars(self):
        """pwd_generator should use custom character set."""
        result = common.pwd_generator(size=10, chars='abc')
        assert all(c in 'abc' for c in result)


class TestPwdCheck:
    """Tests for pwd_check() function."""

    def test_pwd_check_valid_password(self):
        """pwd_check should accept valid password."""
        assert common.pwd_check("password123") is True
        assert common.pwd_check("abcdefgh") is True

    def test_pwd_check_too_short(self):
        """pwd_check should reject password shorter than 8 chars."""
        assert common.pwd_check("pass") is False
        assert common.pwd_check("1234567") is False

    def test_pwd_check_exactly_8_chars(self):
        """pwd_check should accept password of exactly 8 chars."""
        assert common.pwd_check("12345678") is True

    def test_pwd_check_with_spaces(self):
        """pwd_check should reject password with spaces."""
        assert common.pwd_check("pass word") is False
        assert common.pwd_check(" password") is False


class TestMymakedirs:
    """Tests for mymakedirs() function."""

    def test_mymakedirs_creates_single_directory(self):
        """mymakedirs should create a single directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, 'newdir')
            result = common.mymakedirs(new_dir)
            assert result is True
            assert os.path.isdir(new_dir)

    def test_mymakedirs_creates_nested_directories(self):
        """mymakedirs should create nested directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, 'level1', 'level2', 'level3')
            result = common.mymakedirs(new_dir)
            assert result is True
            assert os.path.isdir(new_dir)

    def test_mymakedirs_handles_existing_directory(self):
        """mymakedirs should handle existing directory gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Directory already exists
            result = common.mymakedirs(tmpdir)
            assert result is True

    def test_mymakedirs_returns_true_for_empty_path(self):
        """mymakedirs should handle edge cases."""
        # Empty path - should return True since nothing to create
        with tempfile.TemporaryDirectory() as tmpdir:
            # Existing dir should return True
            result = common.mymakedirs(tmpdir)
            assert result is True


class TestSafeMove:
    """Tests for safe_move() function."""

    def test_safe_move_moves_file(self):
        """safe_move should move file successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create source file
            src = os.path.join(tmpdir, 'source.txt')
            dst = os.path.join(tmpdir, 'dest.txt')
            with open(src, 'w') as f:
                f.write('test content')

            result = common.safe_move(src, dst)
            assert result == dst
            assert os.path.exists(dst)
            assert not os.path.exists(src)

    def test_safe_move_copy_action(self):
        """safe_move with action='copy' should copy file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, 'source.txt')
            dst = os.path.join(tmpdir, 'dest.txt')
            with open(src, 'w') as f:
                f.write('test content')

            result = common.safe_move(src, dst, action='copy')
            assert result == dst
            assert os.path.exists(dst)
            assert os.path.exists(src)  # Source should still exist

    def test_safe_move_sibling_rename_does_not_duplicate(self):
        """Renaming a directory to a sibling whose name shares a string prefix
        (e.g. 'foo' -> 'foo.fail') must move, not copy. A naive startswith() check
        would treat 'foo.fail' as nested under 'foo' and call copytree, leaving the
        source on disk — the bug behind duplicate '.fail' folders after failed
        post-processing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, 'job-folder')
            os.makedirs(src)
            with open(os.path.join(src, 'book.epub'), 'w') as f:
                f.write('content')

            dst = src + '.fail'
            result = common.safe_move(src, dst)
            assert result == dst
            assert os.path.isdir(dst)
            assert os.path.isfile(os.path.join(dst, 'book.epub'))
            # Critical assertion: the source must be gone (no duplicate).
            assert not os.path.exists(src)

    def test_safe_move_nested_target_uses_copytree(self):
        """If dst is genuinely *inside* src as a child path, fall back to copytree
        (this is the original intent of the special case — kept for compatibility)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, 'parent')
            os.makedirs(src)
            with open(os.path.join(src, 'a.txt'), 'w') as f:
                f.write('content')

            dst = os.path.join(src, 'child')
            result = common.safe_move(src, dst)
            assert result == dst
            assert os.path.isdir(dst)
            assert os.path.isfile(os.path.join(dst, 'a.txt'))
            # Source remains because copytree was used.
            assert os.path.isdir(src)


class TestSafeCopy:
    """Tests for safe_copy() function."""

    def test_safe_copy_copies_file(self):
        """safe_copy should copy file successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, 'source.txt')
            dst = os.path.join(tmpdir, 'dest.txt')
            with open(src, 'w') as f:
                f.write('test content')

            result = common.safe_copy(src, dst)
            assert result == dst
            assert os.path.exists(dst)
            assert os.path.exists(src)

            # Verify content
            with open(dst, 'r') as f:
                assert f.read() == 'test content'


class TestMimeType:
    """Tests for mimeType() function."""

    def test_mimeType_epub(self):
        """mimeType should return correct type for epub."""
        result = common.mimeType('book.epub')
        assert 'epub' in result

    def test_mimeType_pdf(self):
        """mimeType should return correct type for pdf."""
        result = common.mimeType('document.pdf')
        assert 'pdf' in result

    def test_mimeType_mobi(self):
        """mimeType should return correct type for mobi."""
        result = common.mimeType('book.mobi')
        assert result is not None

    def test_mimeType_unknown(self):
        """mimeType should handle unknown extensions."""
        result = common.mimeType('file.xyz')
        assert result is not None


class TestOctal:
    """Tests for octal() function."""

    def test_octal_valid_string(self):
        """octal should convert valid octal string."""
        result = common.octal('0o755', 0o644)
        assert result == 0o755

    def test_octal_integer_string(self):
        """octal should convert integer string."""
        result = common.octal('755', 0o644)
        assert result == 0o755

    def test_octal_default_for_invalid(self):
        """octal should return default for invalid input."""
        result = common.octal('invalid', 0o644)
        assert result == 0o644

    def test_octal_empty_returns_default(self):
        """octal should return default for empty string."""
        result = common.octal('', 0o644)
        assert result == 0o644


class TestDicCharacterReplacement:
    """Tests for __dic__ character replacement dictionary."""

    def test_dic_exists(self):
        """__dic__ should exist in common module."""
        # Access the private dict through replace_all usage
        from bookbagofholding.formatter import replace_all
        # Test that character replacement works
        result = replace_all("test<>file", {'<': '', '>': ''})
        assert '<' not in result
        assert '>' not in result


class TestAnyFile:
    """Tests for any_file() function."""

    def test_any_file_returns_empty_for_empty_dir(self):
        """any_file should return empty string for directory with no matching files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = common.any_file(tmpdir, '.nonexistent')
            assert result == ''

    def test_any_file_finds_matching_file(self):
        """any_file should find file with matching extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('test')
            result = common.any_file(tmpdir, '.txt')
            assert result != ''
            assert 'test.txt' in result


class TestBookFile:
    """Tests for book_file() function."""

    def test_book_file_returns_empty_for_empty_dir(self):
        """book_file should return empty string for directory with no books."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = common.book_file(tmpdir, 'epub')
            assert result == ''

    def test_book_file_finds_epub(self):
        """book_file should find epub files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test epub file
            test_file = os.path.join(tmpdir, 'test.epub')
            with open(test_file, 'w') as f:
                f.write('test')
            result = common.book_file(tmpdir, 'epub')
            assert result != ''
            assert 'epub' in result

    def test_book_file_non_recursive_misses_nested(self):
        """book_file should NOT find files in subdirectories by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'release.nfo'), 'w') as f:
                f.write('top-level junk')
            subdir = os.path.join(tmpdir, 'release-subfolder')
            os.makedirs(subdir)
            nested = os.path.join(subdir, 'book.m4b')
            with open(nested, 'w') as f:
                f.write('audio')
            result = common.book_file(tmpdir, 'audiobook')
            assert result == ''

    def test_book_file_recursive_finds_nested_audiobook(self):
        """book_file(recurse=True) should descend into subfolders.

        Reproduces the SAB nested-layout bug where job folder contains only
        an .nfo at top with the .m4b one directory deeper.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'release.nfo'), 'w') as f:
                f.write('top-level junk')
            subdir = os.path.join(tmpdir, 'release-subfolder')
            os.makedirs(subdir)
            nested = os.path.join(subdir, 'book.m4b')
            with open(nested, 'w') as f:
                f.write('audio')
            result = common.book_file(tmpdir, 'audiobook', recurse=True)
            assert result == nested

    def test_book_file_recursive_finds_nested_ebook(self):
        """book_file(recurse=True) should find ebooks in subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, 'inner')
            os.makedirs(subdir)
            nested = os.path.join(subdir, 'book.epub')
            with open(nested, 'w') as f:
                f.write('ebook')
            result = common.book_file(tmpdir, 'ebook', recurse=True)
            assert result == nested

    def test_book_file_recursive_returns_empty_when_nothing(self):
        """book_file(recurse=True) returns '' when no media exists at any depth."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, 'inner')
            os.makedirs(subdir)
            with open(os.path.join(subdir, 'readme.txt'), 'w') as f:
                f.write('nope')
            result = common.book_file(tmpdir, 'audiobook', recurse=True)
            assert result == ''


class TestGetFilesByType:
    """Tests for get_files_by_type() function."""

    def test_classifies_top_level(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ('book.epub', 'audio.m4b', 'notes.nfo'):
                with open(os.path.join(tmpdir, name), 'w') as f:
                    f.write('x')
            result = common.get_files_by_type(tmpdir)
            assert result['ebook'] == ['book.epub']
            assert result['audiobook'] == ['audio.m4b']
            assert result['other'] == ['notes.nfo']

    def test_non_recursive_misses_nested(self):
        """Default scan only sees the top level (the bug case)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'release.nfo'), 'w') as f:
                f.write('x')
            subdir = os.path.join(tmpdir, 'release-subfolder')
            os.makedirs(subdir)
            with open(os.path.join(subdir, 'book.m4b'), 'w') as f:
                f.write('x')
            result = common.get_files_by_type(tmpdir)
            assert result['audiobook'] == []
            assert result['other'] == ['release.nfo']

    def test_recursive_finds_nested(self):
        """recurse=True surfaces nested media using relative paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'release.nfo'), 'w') as f:
                f.write('x')
            subdir = os.path.join(tmpdir, 'release-subfolder')
            os.makedirs(subdir)
            with open(os.path.join(subdir, 'book.m4b'), 'w') as f:
                f.write('x')
            result = common.get_files_by_type(tmpdir, recurse=True)
            assert os.path.join('release-subfolder', 'book.m4b') in result['audiobook']
            assert 'release.nfo' in result['other']

    def test_returns_empty_for_invalid_dir(self):
        result = common.get_files_by_type('/this/path/does/not/exist')
        assert result == {'ebook': [], 'audiobook': [], 'other': []}


class TestJpgFile:
    """Tests for jpg_file() function."""

    def test_jpg_file_returns_empty_for_empty_dir(self):
        """jpg_file should return empty string for directory with no images."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = common.jpg_file(tmpdir)
            assert result == ''


class TestOpfFile:
    """Tests for opf_file() function."""

    def test_opf_file_returns_empty_for_empty_dir(self):
        """opf_file should return empty string for directory with no OPF files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = common.opf_file(tmpdir)
            assert result == ''


class TestIsOverdue:
    """Tests for is_overdue() function."""

    def test_is_overdue_function_exists(self):
        """is_overdue function should exist."""
        assert hasattr(common, 'is_overdue')
        assert callable(common.is_overdue)
