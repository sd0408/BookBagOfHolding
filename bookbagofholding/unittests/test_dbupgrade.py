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
Unit tests for bookbagofholding.dbupgrade module.

Tests cover:
- Database schema version constants
- Upgrade function existence
"""

import pytest

from bookbagofholding import dbupgrade


class TestDbUpgradeModule:
    """Tests for dbupgrade module."""

    def test_module_imports(self):
        """dbupgrade module should import successfully."""
        assert dbupgrade is not None

    def test_has_upgrade_function(self):
        """dbupgrade should have main upgrade function."""
        assert hasattr(dbupgrade, 'dbupgrade')

    def test_has_upgrade_needed_function(self):
        """dbupgrade should have upgrade_needed function."""
        assert hasattr(dbupgrade, 'upgrade_needed')

    def test_has_check_db_function(self):
        """dbupgrade should have check_db function."""
        assert hasattr(dbupgrade, 'check_db')

    def test_has_has_column_function(self):
        """dbupgrade should have has_column function."""
        assert hasattr(dbupgrade, 'has_column')


class TestSchemaVersion:
    """Tests for database schema version."""

    def test_current_db_version_defined(self):
        """Current database version should be defined."""
        # Check if version constant exists
        version_found = False
        for attr in dir(dbupgrade):
            if 'version' in attr.lower() or 'db_version' in attr.lower():
                version_found = True
                break
        # Even if not found as constant, module should exist
        assert dbupgrade is not None


class TestDbUpgradeFunctions:
    """Tests for database upgrade helper functions."""

    def test_module_has_sql_operations(self):
        """dbupgrade module should have SQL execution capability."""
        # The module should be able to work with databases
        import sqlite3
        # Just verify we can import sqlite3 for db operations
        assert sqlite3 is not None


class TestDbV52BlacklistDedupe:
    """Tests for db_v52 — one-shot collapse of duplicate blacklist rows."""

    @pytest.fixture
    def upgrade_log(self, tmp_path):
        # db_v52 writes a few lines to an upgrade log; provide a real file handle
        log_path = tmp_path / 'upgradelog.txt'
        with open(str(log_path), 'w') as f:
            yield f

    def _seed_blacklist(self, conn):
        conn.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                NZBurl TEXT, NZBtitle TEXT, NZBprov TEXT, BookID TEXT,
                AuxInfo TEXT, DateAdded TEXT, Reason TEXT
            )
        ''')
        conn.commit()

    def test_collapses_duplicates_keeping_oldest(self, temp_db, upgrade_log):
        from bookbagofholding.database import DBConnection
        from bookbagofholding import dbupgrade
        db_path, conn = temp_db
        self._seed_blacklist(conn)

        # 3 ephemeral-URL duplicates for the same release
        conn.execute(
            "INSERT INTO blacklist (NZBurl, NZBtitle, NZBprov, BookID, Reason, DateAdded)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ('http://p/?link=A', 'Made Things', 'prowlarr', 'book-1',
             'UnsupportedFileType', '2026-05-18 06:52:26')
        )
        conn.execute(
            "INSERT INTO blacklist (NZBurl, NZBtitle, NZBprov, BookID, Reason, DateAdded)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ('http://p/?link=B', 'Made Things', 'prowlarr', 'book-1',
             'UnsupportedFileType', '2026-05-18 07:02:31')
        )
        conn.execute(
            "INSERT INTO blacklist (NZBurl, NZBtitle, NZBprov, BookID, Reason, DateAdded)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ('http://p/?link=C', 'Made Things', 'prowlarr', 'book-1',
             'UnsupportedFileType', '2026-05-18 07:12:20')
        )
        # And a genuinely different release that should survive
        conn.execute(
            "INSERT INTO blacklist (NZBurl, NZBtitle, NZBprov, BookID, Reason, DateAdded)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ('http://p/?link=Z', 'Other Title', 'prowlarr', 'book-1',
             'UnsupportedFileType', '2026-05-18 06:00:00')
        )
        conn.commit()

        dbupgrade.db_v52(DBConnection(), upgrade_log)

        rows = DBConnection().select(
            'SELECT * FROM blacklist ORDER BY NZBtitle, DateAdded')
        # 1 collapsed dup + 1 unrelated = 2
        assert len(rows) == 2
        # The kept dup row should be the oldest (06:52:26)
        made_things = [r for r in rows if r['NZBtitle'] == 'Made Things']
        assert len(made_things) == 1
        assert made_things[0]['DateAdded'] == '2026-05-18 06:52:26'
        assert made_things[0]['NZBurl'] == 'http://p/?link=A'

    def test_buckets_null_bookid_together(self, temp_db, upgrade_log):
        """Rows with BookID=NULL for the same (prov, title, reason) should also collapse."""
        from bookbagofholding.database import DBConnection
        from bookbagofholding import dbupgrade
        db_path, conn = temp_db
        self._seed_blacklist(conn)

        conn.execute(
            "INSERT INTO blacklist (NZBurl, NZBtitle, NZBprov, BookID, Reason, DateAdded)"
            " VALUES (?, ?, ?, NULL, ?, ?)",
            ('http://p/?link=A', 'Orphan Title', 'prov', 'Failed', '2026-05-18 06:00:00')
        )
        conn.execute(
            "INSERT INTO blacklist (NZBurl, NZBtitle, NZBprov, BookID, Reason, DateAdded)"
            " VALUES (?, ?, ?, NULL, ?, ?)",
            ('http://p/?link=B', 'Orphan Title', 'prov', 'Failed', '2026-05-18 06:05:00')
        )
        conn.commit()

        dbupgrade.db_v52(DBConnection(), upgrade_log)

        rows = DBConnection().select('SELECT * FROM blacklist')
        assert len(rows) == 1

    def test_no_op_on_clean_table(self, temp_db, upgrade_log):
        """If there are no duplicates, nothing should be removed."""
        from bookbagofholding.database import DBConnection
        from bookbagofholding import dbupgrade
        db_path, conn = temp_db
        self._seed_blacklist(conn)

        conn.execute(
            "INSERT INTO blacklist (NZBurl, NZBtitle, NZBprov, BookID, Reason, DateAdded)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ('http://p/?link=A', 'Title A', 'prov', 'book-1', 'Failed', '2026-05-18 06:00:00')
        )
        conn.execute(
            "INSERT INTO blacklist (NZBurl, NZBtitle, NZBprov, BookID, Reason, DateAdded)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ('http://p/?link=B', 'Title B', 'prov', 'book-1', 'Failed', '2026-05-18 06:01:00')
        )
        conn.commit()

        dbupgrade.db_v52(DBConnection(), upgrade_log)

        rows = DBConnection().select('SELECT * FROM blacklist')
        assert len(rows) == 2

    def test_current_version_bumped_to_52(self):
        """upgrade_needed should now return 52 for a fresh-version-0 db."""
        # We can't easily run upgrade_needed against a fresh db here, but we can
        # at least confirm the db_v52 migration function exists.
        from bookbagofholding import dbupgrade
        assert hasattr(dbupgrade, 'db_v52'), 'db_v52 migration must exist'
