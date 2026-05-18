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
Unit tests for bookbagofholding.database module.

Tests cover:
- DBConnection initialization
- CRUD operations (action, select, match, upsert)
- Error handling for database operations
- Thread safety with db_lock
"""

import os
import sqlite3
import tempfile
import threading
import time

import pytest

import bookbagofholding
from bookbagofholding.database import DBConnection, db_lock


class TestDBConnectionInit:
    """Tests for DBConnection initialization."""

    def test_connection_creates_successfully(self, temp_db):
        """DBConnection should create a valid connection."""
        db_path, _ = temp_db
        db = DBConnection()
        assert db.connection is not None

    def test_connection_uses_wal_mode(self, temp_db):
        """DBConnection should enable WAL journal mode."""
        db_path, _ = temp_db
        db = DBConnection()
        result = db.connection.execute("PRAGMA journal_mode").fetchone()
        assert result[0].lower() == 'wal'

    def test_connection_enables_foreign_keys(self, temp_db):
        """DBConnection should enable foreign key constraints."""
        db_path, _ = temp_db
        db = DBConnection()
        result = db.connection.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1

    def test_connection_uses_row_factory(self, temp_db):
        """DBConnection should use sqlite3.Row as row_factory."""
        db_path, _ = temp_db
        db = DBConnection()
        assert db.connection.row_factory == sqlite3.Row


class TestDBConnectionAction:
    """Tests for DBConnection.action() method."""

    def test_action_returns_none_for_empty_query(self, temp_db):
        """action() should return None for empty query."""
        db_path, _ = temp_db
        db = DBConnection()
        result = db.action('')
        assert result is None

    def test_action_returns_none_for_none_query(self, temp_db):
        """action() should return None for None query."""
        db_path, _ = temp_db
        db = DBConnection()
        result = db.action(None)
        assert result is None

    def test_action_executes_insert(self, temp_db, sample_author_data):
        """action() should successfully execute INSERT statements."""
        db_path, _ = temp_db
        db = DBConnection()

        query = "INSERT INTO authors (AuthorID, AuthorName, Status) VALUES (?, ?, ?)"
        result = db.action(query, [
            sample_author_data['AuthorID'],
            sample_author_data['AuthorName'],
            sample_author_data['Status']
        ])

        assert result is not None

        # Verify the insert worked
        verify = db.connection.execute(
            "SELECT AuthorName FROM authors WHERE AuthorID = ?",
            [sample_author_data['AuthorID']]
        ).fetchone()
        assert verify['AuthorName'] == sample_author_data['AuthorName']

    def test_action_executes_update(self, temp_db, sample_author_data):
        """action() should successfully execute UPDATE statements."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert first
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName, Status) VALUES (?, ?, ?)",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName'], 'Active']
        )

        # Update
        db.action(
            "UPDATE authors SET Status = ? WHERE AuthorID = ?",
            ['Paused', sample_author_data['AuthorID']]
        )

        # Verify
        result = db.connection.execute(
            "SELECT Status FROM authors WHERE AuthorID = ?",
            [sample_author_data['AuthorID']]
        ).fetchone()
        assert result['Status'] == 'Paused'

    def test_action_executes_delete(self, temp_db, sample_author_data):
        """action() should successfully execute DELETE statements."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert first
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName']]
        )

        # Delete
        db.action(
            "DELETE FROM authors WHERE AuthorID = ?",
            [sample_author_data['AuthorID']]
        )

        # Verify deletion
        result = db.connection.execute(
            "SELECT * FROM authors WHERE AuthorID = ?",
            [sample_author_data['AuthorID']]
        ).fetchone()
        assert result is None

    def test_action_handles_integrity_error_with_suppress(self, temp_db, sample_author_data):
        """action() should suppress UNIQUE constraint errors when suppress='UNIQUE'."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert first time
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName']]
        )

        # Insert again with suppress - should not raise
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName']],
            suppress='UNIQUE'
        )

    def test_action_raises_integrity_error_without_suppress(self, temp_db, sample_author_data):
        """action() should raise IntegrityError for duplicate keys without suppress."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert first time
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName']]
        )

        # Insert again without suppress - should raise
        with pytest.raises(sqlite3.IntegrityError):
            db.action(
                "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
                [sample_author_data['AuthorID'], sample_author_data['AuthorName']]
            )

    def test_action_raises_database_error_for_invalid_sql(self, temp_db):
        """action() should raise DatabaseError for invalid SQL."""
        db_path, _ = temp_db
        db = DBConnection()

        with pytest.raises(sqlite3.DatabaseError):
            db.action("SELECT * FROM nonexistent_table_xyz")


class TestDBConnectionSelect:
    """Tests for DBConnection.select() method."""

    def test_select_returns_empty_list_for_no_results(self, temp_db):
        """select() should return empty list when no rows match."""
        db_path, _ = temp_db
        db = DBConnection()

        result = db.select("SELECT * FROM authors WHERE AuthorID = ?", ['nonexistent'])
        assert result == []

    def test_select_returns_multiple_rows(self, temp_db):
        """select() should return list of all matching rows."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert multiple authors
        for i in range(3):
            db.action(
                "INSERT INTO authors (AuthorID, AuthorName, Status) VALUES (?, ?, ?)",
                [f'author-{i}', f'Author {i}', 'Active']
            )

        result = db.select("SELECT * FROM authors WHERE Status = ?", ['Active'])
        assert len(result) == 3

    def test_select_returns_sqlite_row_objects(self, temp_db, sample_author_data):
        """select() should return sqlite3.Row objects for dict-like access."""
        db_path, _ = temp_db
        db = DBConnection()

        db.action(
            "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName']]
        )

        result = db.select("SELECT * FROM authors")
        assert len(result) == 1
        assert result[0]['AuthorID'] == sample_author_data['AuthorID']
        assert result[0]['AuthorName'] == sample_author_data['AuthorName']

    def test_select_with_order_by(self, temp_db):
        """select() should respect ORDER BY clause."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert in non-alphabetical order
        for name in ['Charlie', 'Alice', 'Bob']:
            db.action(
                "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
                [name.lower(), name]
            )

        result = db.select("SELECT AuthorName FROM authors ORDER BY AuthorName ASC")
        names = [r['AuthorName'] for r in result]
        assert names == ['Alice', 'Bob', 'Charlie']


class TestDBConnectionMatch:
    """Tests for DBConnection.match() method."""

    def test_match_returns_empty_list_for_no_results(self, temp_db):
        """match() should return empty list when no rows match."""
        db_path, _ = temp_db
        db = DBConnection()

        result = db.match("SELECT * FROM authors WHERE AuthorID = ?", ['nonexistent'])
        assert result == []

    def test_match_returns_single_row(self, temp_db, sample_author_data):
        """match() should return single row when match found."""
        db_path, _ = temp_db
        db = DBConnection()

        db.action(
            "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName']]
        )

        result = db.match(
            "SELECT * FROM authors WHERE AuthorID = ?",
            [sample_author_data['AuthorID']]
        )
        assert result['AuthorName'] == sample_author_data['AuthorName']

    def test_match_returns_first_row_when_multiple_match(self, temp_db):
        """match() should return only the first row when multiple match."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert multiple with same status
        for i in range(3):
            db.action(
                "INSERT INTO authors (AuthorID, AuthorName, Status) VALUES (?, ?, ?)",
                [f'author-{i}', f'Author {i}', 'Active']
            )

        result = db.match("SELECT * FROM authors WHERE Status = ?", ['Active'])
        # Should return a single row, not a list
        assert 'AuthorID' in result.keys()


class TestDBConnectionUpsert:
    """Tests for DBConnection.upsert() method."""

    def test_upsert_inserts_new_row(self, temp_db, sample_author_data):
        """upsert() should insert when row doesn't exist."""
        db_path, _ = temp_db
        db = DBConnection()

        db.upsert(
            'authors',
            {'AuthorName': sample_author_data['AuthorName'], 'Status': 'Active'},
            {'AuthorID': sample_author_data['AuthorID']}
        )

        result = db.match(
            "SELECT * FROM authors WHERE AuthorID = ?",
            [sample_author_data['AuthorID']]
        )
        assert result['AuthorName'] == sample_author_data['AuthorName']
        assert result['Status'] == 'Active'

    def test_upsert_updates_existing_row(self, temp_db, sample_author_data):
        """upsert() should update when row exists."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert first
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName, Status) VALUES (?, ?, ?)",
            [sample_author_data['AuthorID'], 'Original Name', 'Active']
        )

        # Upsert with new values
        db.upsert(
            'authors',
            {'AuthorName': 'Updated Name', 'Status': 'Paused'},
            {'AuthorID': sample_author_data['AuthorID']}
        )

        result = db.match(
            "SELECT * FROM authors WHERE AuthorID = ?",
            [sample_author_data['AuthorID']]
        )
        assert result['AuthorName'] == 'Updated Name'
        assert result['Status'] == 'Paused'

    def test_upsert_preserves_unspecified_columns(self, temp_db, sample_author_data):
        """upsert() should not modify columns not in valueDict."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert with HaveBooks value
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName, HaveBooks) VALUES (?, ?, ?)",
            [sample_author_data['AuthorID'], 'Original Name', 10]
        )

        # Upsert only AuthorName
        db.upsert(
            'authors',
            {'AuthorName': 'Updated Name'},
            {'AuthorID': sample_author_data['AuthorID']}
        )

        result = db.match(
            "SELECT * FROM authors WHERE AuthorID = ?",
            [sample_author_data['AuthorID']]
        )
        assert result['AuthorName'] == 'Updated Name'
        assert result['HaveBooks'] == 10  # Should be unchanged


class TestDBConnectionGenParams:
    """Tests for DBConnection.genParams() static method."""

    def test_genParams_creates_parameterized_list(self, temp_db):
        """genParams() should create list of 'key = ?' strings."""
        result = DBConnection.genParams({'name': 'value', 'status': 'active'})
        assert 'name = ?' in result
        assert 'status = ?' in result
        assert len(result) == 2

    def test_genParams_handles_empty_dict(self, temp_db):
        """genParams() should return empty list for empty dict."""
        result = DBConnection.genParams({})
        assert result == []


class TestDBConnectionThreadSafety:
    """Tests for database thread safety."""

    def test_concurrent_reads_succeed(self, temp_db):
        """Multiple threads should be able to read concurrently."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert test data
        for i in range(10):
            db.action(
                "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
                [f'author-{i}', f'Author {i}']
            )

        results = []
        errors = []

        def read_data():
            try:
                db_conn = DBConnection()
                result = db_conn.select("SELECT * FROM authors")
                results.append(len(result))
            except Exception as e:
                errors.append(str(e))

        # Create multiple reader threads
        threads = [threading.Thread(target=read_data) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert all(r == 10 for r in results)

    def test_concurrent_writes_are_serialized(self, temp_db):
        """Concurrent writes should be serialized via db_lock."""
        db_path, _ = temp_db

        write_count = [0]
        errors = []

        def write_data(thread_id):
            try:
                db_conn = DBConnection()
                for i in range(5):
                    db_conn.action(
                        "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
                        [f'author-t{thread_id}-{i}', f'Author T{thread_id} {i}']
                    )
                    write_count[0] += 1
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_data, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Verify all writes succeeded
        db = DBConnection()
        result = db.select("SELECT COUNT(*) as count FROM authors")
        assert result[0]['count'] == 15  # 3 threads * 5 writes each


class TestDBConnectionForeignKeys:
    """Tests for foreign key constraint behavior."""

    def test_cascade_delete_removes_related_books(self, temp_db, sample_author_data, sample_book_data):
        """Deleting an author should cascade delete their books."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert author
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName']]
        )

        # Insert book linked to author
        db.action(
            "INSERT INTO books (BookID, AuthorID, BookName) VALUES (?, ?, ?)",
            [sample_book_data['BookID'], sample_author_data['AuthorID'], sample_book_data['BookName']]
        )

        # Delete author
        db.action(
            "DELETE FROM authors WHERE AuthorID = ?",
            [sample_author_data['AuthorID']]
        )

        # Book should also be deleted
        result = db.match(
            "SELECT * FROM books WHERE BookID = ?",
            [sample_book_data['BookID']]
        )
        assert result == []


class TestDBConnectionEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_special_characters_in_data(self, temp_db):
        """Database should handle special characters in data."""
        db_path, _ = temp_db
        db = DBConnection()

        special_name = "O'Brien & Sons \"Test\" <Author>"
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
            ['special-author', special_name]
        )

        result = db.match("SELECT AuthorName FROM authors WHERE AuthorID = ?", ['special-author'])
        assert result['AuthorName'] == special_name

    def test_unicode_in_data(self, temp_db):
        """Database should handle Unicode characters."""
        db_path, _ = temp_db
        db = DBConnection()

        unicode_name = "José García 日本語 Привет"
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
            ['unicode-author', unicode_name]
        )

        result = db.match("SELECT AuthorName FROM authors WHERE AuthorID = ?", ['unicode-author'])
        assert result['AuthorName'] == unicode_name

    def test_null_values(self, temp_db, sample_author_data):
        """Database should handle NULL values correctly."""
        db_path, _ = temp_db
        db = DBConnection()

        db.action(
            "INSERT INTO authors (AuthorID, AuthorName, AuthorImg) VALUES (?, ?, ?)",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName'], None]
        )

        result = db.match(
            "SELECT AuthorImg FROM authors WHERE AuthorID = ?",
            [sample_author_data['AuthorID']]
        )
        assert result['AuthorImg'] is None

    def test_very_long_text(self, temp_db, sample_book_data, sample_author_data):
        """Database should handle very long text fields."""
        db_path, _ = temp_db
        db = DBConnection()

        # Insert author first
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName) VALUES (?, ?)",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName']]
        )

        long_desc = "A" * 100000  # 100KB of text
        db.action(
            "INSERT INTO books (BookID, AuthorID, BookName, BookDesc) VALUES (?, ?, ?, ?)",
            [sample_book_data['BookID'], sample_author_data['AuthorID'], sample_book_data['BookName'], long_desc]
        )

        result = db.match("SELECT BookDesc FROM books WHERE BookID = ?", [sample_book_data['BookID']])
        assert len(result['BookDesc']) == 100000


class TestAddToBlacklist:
    """Tests for add_to_blacklist() — dedupe by (NZBprov, NZBtitle, BookID, Reason)
    so ephemeral signed URLs (Prowlarr) don't bloat the table with duplicates."""

    @pytest.fixture(autouse=True)
    def setup_blacklist_table(self, temp_db):
        db_path, conn = temp_db
        conn.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                NZBurl TEXT, NZBtitle TEXT, NZBprov TEXT, BookID TEXT,
                AuxInfo TEXT, DateAdded TEXT, Reason TEXT
            )
        ''')
        conn.commit()
        return db_path, conn

    def test_first_insert_creates_row(self, temp_db):
        from bookbagofholding.database import add_to_blacklist, DBConnection
        add_to_blacklist(
            'http://prov/?link=ABC', 'Release Title', 'prov-host:9696/api',
            book_id='book-1', aux_info='eBook', reason='UnsupportedFileType')
        rows = DBConnection().select('SELECT * FROM blacklist')
        assert len(rows) == 1
        assert rows[0]['NZBurl'] == 'http://prov/?link=ABC'
        assert rows[0]['Reason'] == 'UnsupportedFileType'

    def test_duplicate_by_url_only_does_not_insert_new(self, temp_db):
        """The original bug: same (prov, title, bookid, reason) with a different URL
        used to create a fresh row every cycle. Should now collapse into one."""
        from bookbagofholding.database import add_to_blacklist, DBConnection
        add_to_blacklist(
            'http://prov/?link=ABC', 'Release Title', 'prov-host:9696/api',
            book_id='book-1', aux_info='eBook', reason='UnsupportedFileType')
        add_to_blacklist(
            'http://prov/?link=XYZ', 'Release Title', 'prov-host:9696/api',
            book_id='book-1', aux_info='eBook', reason='UnsupportedFileType')
        add_to_blacklist(
            'http://prov/?link=QQQ', 'Release Title', 'prov-host:9696/api',
            book_id='book-1', aux_info='eBook', reason='UnsupportedFileType')

        rows = DBConnection().select('SELECT * FROM blacklist')
        assert len(rows) == 1
        # The latest URL should be retained so the entry reflects the most recent observation.
        assert rows[0]['NZBurl'] == 'http://prov/?link=QQQ'

    def test_different_title_creates_separate_row(self, temp_db):
        """Genuinely different releases (different title) should still get separate rows."""
        from bookbagofholding.database import add_to_blacklist, DBConnection
        add_to_blacklist(
            'http://prov/?link=A', 'Release A', 'prov',
            book_id='book-1', reason='Failed')
        add_to_blacklist(
            'http://prov/?link=B', 'Release B', 'prov',
            book_id='book-1', reason='Failed')
        rows = DBConnection().select('SELECT * FROM blacklist')
        assert len(rows) == 2

    def test_different_reason_creates_separate_row(self, temp_db):
        """Same release, different reason (e.g. Processed vs Failed) should coexist."""
        from bookbagofholding.database import add_to_blacklist, DBConnection
        add_to_blacklist(
            'http://prov/?link=A', 'Title', 'prov',
            book_id='book-1', reason='Failed')
        add_to_blacklist(
            'http://prov/?link=A', 'Title', 'prov',
            book_id='book-1', reason='Processed')
        rows = DBConnection().select('SELECT * FROM blacklist')
        assert len(rows) == 2

    def test_different_bookid_creates_separate_row(self, temp_db):
        """Same release attached to a different book should not collide."""
        from bookbagofholding.database import add_to_blacklist, DBConnection
        add_to_blacklist(
            'http://prov/?link=A', 'Title', 'prov',
            book_id='book-1', reason='Failed')
        add_to_blacklist(
            'http://prov/?link=B', 'Title', 'prov',
            book_id='book-2', reason='Failed')
        rows = DBConnection().select('SELECT * FROM blacklist')
        assert len(rows) == 2

    def test_null_bookid_dedupes_with_null_bookid(self, temp_db):
        """Two inserts with BookID=None should be treated as the same group
        (SQL NULL doesn't compare equal to itself by default — the impl uses IS)."""
        from bookbagofholding.database import add_to_blacklist, DBConnection
        add_to_blacklist(
            'http://prov/?link=A', 'Orphan Title', 'prov',
            book_id=None, reason='Failed')
        add_to_blacklist(
            'http://prov/?link=B', 'Orphan Title', 'prov',
            book_id=None, reason='Failed')
        rows = DBConnection().select('SELECT * FROM blacklist')
        assert len(rows) == 1

    def test_dedupe_refreshes_dateadded(self, temp_db):
        """A duplicate hit should bump DateAdded so callers see the most recent timestamp."""
        from bookbagofholding.database import add_to_blacklist, DBConnection
        import time as t
        add_to_blacklist(
            'http://prov/?link=A', 'Title', 'prov',
            book_id='book-1', reason='Failed')
        first = DBConnection().match('SELECT DateAdded FROM blacklist')['DateAdded']
        t.sleep(1.1)  # ensure now() string differs at second resolution
        add_to_blacklist(
            'http://prov/?link=B', 'Title', 'prov',
            book_id='book-1', reason='Failed')
        second = DBConnection().match('SELECT DateAdded FROM blacklist')['DateAdded']
        assert second != first
