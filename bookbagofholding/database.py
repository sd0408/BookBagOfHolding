#  This file is part of Bookbag of Holding.
#
#  Bookbag of Holding is free software':'you can redistribute it and/or modify
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

import sqlite3
import threading
import time

import bookbagofholding
from bookbagofholding import logger

db_lock = threading.Lock()


class DBConnection:
    def __init__(self):
        self.connection = sqlite3.connect(bookbagofholding.DBFILE, 20)
        # journal disabled since we never do rollbacks
        self.connection.execute("PRAGMA journal_mode = WAL")
        # sync less often as using WAL mode
        self.connection.execute("PRAGMA synchronous = NORMAL")
        # 32mb of cache
        self.connection.execute("PRAGMA cache_size=-%s" % (32 * 1024))
        # for cascade deletes
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.row_factory = sqlite3.Row

    # wrapper function with lock
    def action(self, query, args=None, suppress=None):
        if not query:
            return None
        with db_lock:
            return self._action(query, args, suppress)

    # do not use directly, use through action() or upsert() which add lock
    def _action(self, query, args=None, suppress=None):
        sqlResult = None
        attempt = 0

        while attempt < 5:
            try:
                if not args:
                    sqlResult = self.connection.execute(query)
                else:
                    sqlResult = self.connection.execute(query, args)
                self.connection.commit()
                break

            except sqlite3.OperationalError as e:
                if "unable to open database file" in str(e) or "database is locked" in str(e):
                    logger.warn('Database Error: %s' % e)
                    logger.debug("Attempted db query: [%s]" % query)
                    attempt += 1
                    if attempt == 5:
                        logger.error("Failed db query: [%s]" % query)
                    else:
                        time.sleep(1)
                else:
                    logger.error('Database error: %s' % e)
                    logger.error("Failed query: [%s]" % query)
                    raise

            except sqlite3.IntegrityError as e:
                # we could ignore unique errors in sqlite by using "insert or ignore into" statements
                # but this would also ignore null values as we can't specify which errors to ignore :-(
                # Also the python interface to sqlite only returns english text messages, not error codes
                msg = str(e).lower()
                if suppress and 'UNIQUE' in suppress and ('not unique' in msg or 'unique constraint failed' in msg):
                    if bookbagofholding.LOGLEVEL & bookbagofholding.log_dbcomms:
                        logger.debug('Suppressed [%s] %s' % (query, e))
                        logger.debug("Suppressed args: [%s]" % str(args))
                    self.connection.commit()
                    break
                else:
                    logger.error('Database Integrity error: %s' % e)
                    logger.error("Failed query: [%s]" % query)
                    logger.error("Failed args: [%s]" % str(args))
                    raise

            except sqlite3.DatabaseError as e:
                logger.error('Fatal error executing %s :: %s' % (query, e))
                raise

        return sqlResult

    def match(self, query, args=None):
        try:
            # if there are no results, action() returns None and .fetchone() fails
            sqlResults = self.action(query, args).fetchone()
        except sqlite3.Error:
            return []
        if not sqlResults:
            return []

        return sqlResults

    def select(self, query, args=None):
        try:
            # if there are no results, action() returns None and .fetchall() fails
            sqlResults = self.action(query, args).fetchall()
        except sqlite3.Error:
            return []
        if not sqlResults:
            return []

        return sqlResults

    @staticmethod
    def genParams(myDict):
        return [x + " = ?" for x in list(myDict.keys())]

    def upsert(self, tableName, valueDict, keyDict):
        with db_lock:
            changesBefore = self.connection.total_changes

            query = "UPDATE " + tableName + " SET " + ", ".join(self.genParams(valueDict)) + \
                    " WHERE " + " AND ".join(self.genParams(keyDict))

            self._action(query, list(valueDict.values()) + list(keyDict.values()))

            # This version of upsert is not thread safe, each action() is thread safe,
            # but it's possible for another thread to jump in between the
            # UPDATE and INSERT statements so we use suppress=unique to log any conflicts
            # -- update -- should be thread safe now, threading lock moved

            if self.connection.total_changes == changesBefore:
                query = "INSERT INTO " + tableName + " ("
                query += ", ".join(list(valueDict.keys()) + list(keyDict.keys())) + ") VALUES ("
                query += ", ".join(["?"] * len(list(valueDict.keys()) + list(keyDict.keys()))) + ")"
                self._action(query, list(valueDict.values()) + list(keyDict.values()), suppress="UNIQUE")


def add_to_blacklist(nzb_url, nzb_title, nzb_prov, book_id=None, aux_info=None, reason='Processed'):
    """
    Add an entry to the blacklist table to prevent re-downloading.

    Dedupes on (NZBprov, NZBtitle, BookID, Reason) rather than NZBurl alone.
    Indexers like Prowlarr regenerate signed download URLs on every search, so a
    URL-keyed dedupe would let the same release add a fresh row every cycle —
    bloating the table indefinitely and never matching subsequent lookups.
    The (prov, title, bookid, reason) tuple is stable across re-signs, so it
    collapses the duplicates while still letting genuinely different releases
    (different title) coexist as separate entries.

    On a duplicate hit we refresh DateAdded and overwrite NZBurl with the latest
    seen value, so the entry reflects the most recent observation.

    Args:
        nzb_url: The download URL
        nzb_title: The title of the download
        nzb_prov: The provider name
        book_id: Optional book ID reference
        aux_info: Optional auxiliary info (e.g., 'eBook', 'AudioBook')
        reason: Reason for blacklisting (default: 'Processed')
    """
    from bookbagofholding.formatter import now

    myDB = DBConnection()
    timestamp = now()

    # Match on stable fields. NULL comparisons in SQL need IS rather than = —
    # build the predicate so book_id=None matches existing rows where BookID
    # was inserted as NULL rather than treating the row as missing.
    existing = myDB.match(
        'SELECT rowid FROM blacklist WHERE NZBprov=? AND NZBtitle=? AND Reason=? '
        'AND ((BookID IS NULL AND ? IS NULL) OR BookID=?)',
        (nzb_prov, nzb_title, reason, book_id, book_id)
    )
    if existing:
        myDB.action(
            'UPDATE blacklist SET NZBurl=?, AuxInfo=?, DateAdded=? WHERE rowid=?',
            (nzb_url, aux_info, timestamp, existing['rowid'])
        )
        if bookbagofholding.LOGLEVEL & bookbagofholding.log_dlcomms:
            logger.debug("Refreshed blacklist entry: %s from %s (%s)" % (nzb_title, nzb_prov, reason))
    else:
        myDB.action(
            'INSERT INTO blacklist (NZBurl, NZBtitle, NZBprov, BookID, AuxInfo, DateAdded, Reason) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (nzb_url, nzb_title, nzb_prov, book_id, aux_info, timestamp, reason)
        )
        if bookbagofholding.LOGLEVEL & bookbagofholding.log_dlcomms:
            logger.debug("Added to blacklist: %s from %s (%s)" % (nzb_title, nzb_prov, reason))


def add_unmatched_file(filepath, library_type, author=None, title=None, isbn=None,
                       language=None, gr_id=None, gb_id=None, extension=None):
    """
    Add or update an unmatched file entry.

    Args:
        filepath: Full path to the file
        library_type: 'eBook' or 'AudioBook'
        author: Extracted author name
        title: Extracted book title
        isbn: Extracted ISBN
        language: Extracted language
        gr_id: Goodreads ID if found
        gb_id: Google Books ID if found
        extension: File extension

    Returns:
        True if new entry, False if updated existing
    """
    import hashlib
    import os
    from bookbagofholding.formatter import now

    # Normalize filepath to prevent duplicates from different path representations
    # (symlinks, relative paths, case differences on case-insensitive filesystems)
    normalized_path = os.path.realpath(filepath)

    # Generate unique ID from normalized filepath
    file_id = hashlib.md5(normalized_path.encode('utf-8')).hexdigest()

    myDB = DBConnection()

    # Check if already exists
    existing = myDB.match('SELECT FileID, ScanCount, Status FROM unmatchedfiles WHERE FileID=?',
                          (file_id,))

    if existing:
        # Don't update if already matched or ignored
        if existing['Status'] in ['Matched', 'Ignored']:
            return False

        # Update scan count and date
        myDB.action('UPDATE unmatchedfiles SET ScanCount=?, DateScanned=?, '
                    'ExtractedAuthor=?, ExtractedTitle=?, ExtractedISBN=?, '
                    'ExtractedLang=?, ExtractedGRID=?, ExtractedGBID=? '
                    'WHERE FileID=?',
                    (existing['ScanCount'] + 1, now(), author, title, isbn,
                     language, gr_id, gb_id, file_id))
        return False
    else:
        # Get file stats
        file_size = 0
        file_date = None
        file_name = os.path.basename(normalized_path)

        if os.path.isfile(normalized_path):
            try:
                stat = os.stat(normalized_path)
                file_size = stat.st_size
            except OSError:
                pass
        file_date = now()

        myDB.action('INSERT INTO unmatchedfiles '
                    '(FileID, FilePath, FileName, FileSize, FileDate, LibraryType, '
                    'ExtractedAuthor, ExtractedTitle, ExtractedISBN, ExtractedLang, '
                    'ExtractedGRID, ExtractedGBID, FileExtension, Status, '
                    'DateAdded, DateScanned, ScanCount) '
                    'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (file_id, normalized_path, file_name, file_size, file_date, library_type,
                     author, title, isbn, language, gr_id, gb_id, extension,
                     'Unmatched', now(), now(), 1))
        return True


def remove_unmatched_file(file_id):
    """Remove an unmatched file entry by ID."""
    myDB = DBConnection()
    myDB.action('DELETE FROM unmatchedfiles WHERE FileID=?', (file_id,))


def mark_unmatched_file_matched(file_id, book_id, notes=None):
    """Mark an unmatched file as matched to a book."""
    from bookbagofholding.formatter import now

    myDB = DBConnection()
    myDB.action('UPDATE unmatchedfiles SET Status=?, MatchedBookID=?, Notes=?, DateScanned=? '
                'WHERE FileID=?',
                ('Matched', book_id, notes, now(), file_id))


def mark_unmatched_file_ignored(file_id, notes=None):
    """Mark an unmatched file as ignored."""
    from bookbagofholding.formatter import now

    myDB = DBConnection()
    myDB.action('UPDATE unmatchedfiles SET Status=?, Notes=?, DateScanned=? WHERE FileID=?',
                ('Ignored', notes, now(), file_id))


def get_unmatched_files(library_type=None, status='Unmatched'):
    """Get unmatched files, optionally filtered by library type and status."""
    myDB = DBConnection()

    cmd = 'SELECT * FROM unmatchedfiles WHERE 1=1'
    args = []

    if status:
        cmd += ' AND Status=?'
        args.append(status)

    if library_type:
        cmd += ' AND LibraryType=?'
        args.append(library_type)

    cmd += ' ORDER BY DateAdded DESC'

    return myDB.select(cmd, tuple(args))


def cleanup_unmatched_files():
    """Remove entries for files that no longer exist on disk."""
    import os

    myDB = DBConnection()
    files = myDB.select('SELECT FileID, FilePath FROM unmatchedfiles WHERE Status="Unmatched"')

    removed = 0
    for f in files:
        if not os.path.isfile(f['FilePath']):
            myDB.action('DELETE FROM unmatchedfiles WHERE FileID=?', (f['FileID'],))
            removed += 1

    return removed


def dedupe_unmatched_files():
    """
    Remove duplicate entries by normalizing file paths.
    Keeps the entry with the highest ScanCount for each unique file.
    Returns the number of duplicates removed.
    """
    import os
    import hashlib

    myDB = DBConnection()
    files = myDB.select('SELECT FileID, FilePath, ScanCount, DateAdded FROM unmatchedfiles')

    # Group files by their normalized path
    path_groups = {}
    for f in files:
        normalized = os.path.realpath(f['FilePath'])
        normalized_id = hashlib.md5(normalized.encode('utf-8')).hexdigest()

        if normalized_id not in path_groups:
            path_groups[normalized_id] = []
        path_groups[normalized_id].append(f)

    removed = 0
    for normalized_id, group in path_groups.items():
        if len(group) > 1:
            # Sort by ScanCount (highest first), then by DateAdded (newest first)
            group.sort(key=lambda x: (x['ScanCount'] or 0, x['DateAdded'] or ''), reverse=True)

            # Keep the first one (highest scan count / newest), delete the rest
            for f in group[1:]:
                myDB.action('DELETE FROM unmatchedfiles WHERE FileID=?', (f['FileID'],))
                removed += 1

    return removed
