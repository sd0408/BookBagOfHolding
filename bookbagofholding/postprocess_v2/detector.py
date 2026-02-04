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
File type detection for Bookbag of Holding post-processing.

This module provides utilities for detecting file types and validating
that files match expected formats for ebooks, audiobooks, and magazines.
"""

import os
from typing import List, Optional, Tuple

import bookbagofholding
from bookbagofholding.formatter import getList


class FileDetector:
    """File type detection and validation.

    Provides methods for detecting whether files are ebooks, audiobooks,
    archives, or other supported file types.
    """

    # Archive extensions
    ARCHIVE_EXTENSIONS = ['.zip', '.rar', '.tar', '.gz', '.bz2', '.7z', '.cbz', '.cbr']

    # Image extensions
    IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']

    # Metadata extensions
    METADATA_EXTENSIONS = ['.opf', '.nfo']

    @staticmethod
    def get_ebook_extensions() -> List[str]:
        """Get configured ebook extensions.

        Returns:
            List of ebook file extensions (lowercase, with leading dot)
        """
        extensions = getList(bookbagofholding.CONFIG.get('EBOOK_TYPE', 'epub,mobi,pdf'))
        return ['.' + ext.lower().lstrip('.') for ext in extensions if ext]

    @staticmethod
    def get_audiobook_extensions() -> List[str]:
        """Get configured audiobook extensions.

        Returns:
            List of audiobook file extensions (lowercase, with leading dot)
        """
        extensions = getList(bookbagofholding.CONFIG.get('AUDIOBOOK_TYPE', 'mp3,m4a,m4b'))
        return ['.' + ext.lower().lstrip('.') for ext in extensions if ext]

    @classmethod
    def is_ebook(cls, filepath: str) -> bool:
        """Check if a file is an ebook.

        Args:
            filepath: Path to the file

        Returns:
            True if the file has an ebook extension
        """
        ext = os.path.splitext(filepath)[1].lower()
        return ext in cls.get_ebook_extensions()

    @classmethod
    def is_audiobook(cls, filepath: str) -> bool:
        """Check if a file is an audiobook.

        Args:
            filepath: Path to the file

        Returns:
            True if the file has an audiobook extension
        """
        ext = os.path.splitext(filepath)[1].lower()
        return ext in cls.get_audiobook_extensions()

    @classmethod
    def is_archive(cls, filepath: str) -> bool:
        """Check if a file is an archive.

        Args:
            filepath: Path to the file

        Returns:
            True if the file has an archive extension
        """
        ext = os.path.splitext(filepath)[1].lower()
        return ext in cls.ARCHIVE_EXTENSIONS

    @classmethod
    def is_image(cls, filepath: str) -> bool:
        """Check if a file is an image.

        Args:
            filepath: Path to the file

        Returns:
            True if the file has an image extension
        """
        ext = os.path.splitext(filepath)[1].lower()
        return ext in cls.IMAGE_EXTENSIONS

    @classmethod
    def is_metadata(cls, filepath: str) -> bool:
        """Check if a file is a metadata file.

        Args:
            filepath: Path to the file

        Returns:
            True if the file has a metadata extension
        """
        ext = os.path.splitext(filepath)[1].lower()
        return ext in cls.METADATA_EXTENSIONS

    @classmethod
    def detect_file_type(cls, filepath: str) -> str:
        """Detect the type of a file.

        Args:
            filepath: Path to the file

        Returns:
            File type string: 'ebook', 'audiobook', 'archive',
            'image', 'metadata', or 'unknown'
        """
        if cls.is_ebook(filepath):
            return 'ebook'
        elif cls.is_audiobook(filepath):
            return 'audiobook'
        elif cls.is_archive(filepath):
            return 'archive'
        elif cls.is_image(filepath):
            return 'image'
        elif cls.is_metadata(filepath):
            return 'metadata'
        else:
            return 'unknown'

    @classmethod
    def find_book_file(cls, directory: str, booktype: str = 'ebook') -> Optional[str]:
        """Find a book file in a directory.

        Args:
            directory: Directory to search
            booktype: Type of book to find ('ebook' or 'audiobook')

        Returns:
            Path to the book file, or None if not found
        """
        if not os.path.isdir(directory):
            return None

        if booktype == 'ebook':
            extensions = cls.get_ebook_extensions()
        elif booktype == 'audiobook':
            extensions = cls.get_audiobook_extensions()
        else:
            return None

        for filename in os.listdir(directory):
            ext = os.path.splitext(filename)[1].lower()
            if ext in extensions:
                return os.path.join(directory, filename)

        return None

    @classmethod
    def find_all_books(cls, directory: str, booktype: str = 'ebook') -> List[str]:
        """Find all book files in a directory.

        Args:
            directory: Directory to search
            booktype: Type of books to find ('ebook' or 'audiobook')

        Returns:
            List of paths to book files
        """
        if not os.path.isdir(directory):
            return []

        if booktype == 'ebook':
            extensions = cls.get_ebook_extensions()
        elif booktype == 'audiobook':
            extensions = cls.get_audiobook_extensions()
        else:
            return []

        books = []
        for filename in os.listdir(directory):
            ext = os.path.splitext(filename)[1].lower()
            if ext in extensions:
                books.append(os.path.join(directory, filename))

        return books

    @classmethod
    def count_books(cls, directory: str) -> Tuple[int, int]:
        """Count ebook and audiobook files in a directory.

        Args:
            directory: Directory to search

        Returns:
            Tuple of (ebook_count, audiobook_count)
        """
        if not os.path.isdir(directory):
            return 0, 0

        ebook_count = 0
        audiobook_count = 0

        ebook_exts = cls.get_ebook_extensions()
        audio_exts = cls.get_audiobook_extensions()

        for filename in os.listdir(directory):
            ext = os.path.splitext(filename)[1].lower()
            if ext in ebook_exts:
                ebook_count += 1
            elif ext in audio_exts:
                audiobook_count += 1

        return ebook_count, audiobook_count

    @staticmethod
    def get_file_size(filepath: str) -> int:
        """Get file size in bytes.

        Args:
            filepath: Path to the file

        Returns:
            File size in bytes, or 0 if file doesn't exist
        """
        if os.path.isfile(filepath):
            return os.path.getsize(filepath)
        return 0

    @staticmethod
    def get_directory_size(directory: str) -> int:
        """Get total size of files in a directory.

        Args:
            directory: Directory path

        Returns:
            Total size in bytes
        """
        total_size = 0
        if os.path.isdir(directory):
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)
                if os.path.isfile(filepath):
                    total_size += os.path.getsize(filepath)
        return total_size
