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
Unit tests for bookbagofholding.webServe module.

Tests cover:
- WebInterface class handlers
- serve_template function
- Permission checking
- User authentication flows
- DataTable JSON endpoints
"""

import hashlib
import pytest
from unittest.mock import Mock, patch, MagicMock

import cherrypy
import bookbagofholding
from bookbagofholding.database import DBConnection


# ============================================================================
# Test WebInterface Index/Home Handlers
# ============================================================================

@pytest.mark.web
class TestWebInterfaceIndex:
    """Tests for WebInterface index and home handlers."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_index_redirects_to_home(self, mock_response, mock_request, api_config, temp_db):
        """index() should redirect to home."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        wi = WebInterface()

        with pytest.raises(cherrypy.HTTPRedirect) as excinfo:
            wi.index()

        # HTTPRedirect stores the URLs in the exception
        assert 'home' in str(excinfo.value.urls)

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    @patch('bookbagofholding.webServe.serve_template')
    def test_home_serves_index_template(self, mock_serve, mock_response, mock_request, api_config, temp_db):
        """home() should serve index.html template with Dashboard title."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        mock_serve.return_value = '<html>test</html>'
        bookbagofholding.IGNORED_AUTHORS = 0

        wi = WebInterface()
        result = wi.home()

        mock_serve.assert_called_once()
        call_kwargs = mock_serve.call_args[1]
        assert call_kwargs['templatename'] == 'index.html'
        assert call_kwargs['title'] == 'Dashboard'

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    @patch('bookbagofholding.webServe.serve_template')
    def test_home_shows_ignored_title_when_flag_set(self, mock_serve, mock_response, mock_request, api_config, temp_db):
        """home() should always show Dashboard regardless of IGNORED_AUTHORS flag."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        mock_serve.return_value = '<html>test</html>'
        bookbagofholding.IGNORED_AUTHORS = 1

        wi = WebInterface()
        wi.home()

        call_kwargs = mock_serve.call_args[1]
        # Now always shows Dashboard
        assert call_kwargs['title'] == 'Dashboard'

        bookbagofholding.IGNORED_AUTHORS = 0


# ============================================================================
# Test User Authentication Handlers
# ============================================================================

@pytest.mark.web
class TestWebInterfaceLogout:
    """Tests for logout handler."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_logout_clears_cookie(self, mock_response, mock_request, api_config, temp_db):
        """logout() should clear the ll_uid cookie and redirect."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {'ll_uid': Mock(value='test-user')}
        # Use MagicMock to allow item assignment
        mock_response.cookie = MagicMock()

        wi = WebInterface()

        with pytest.raises(cherrypy.HTTPRedirect) as excinfo:
            wi.logout()

        # Verify redirect to home
        assert 'home' in str(excinfo.value.urls)
        # Verify cookie was set (even if to empty)
        assert mock_response.cookie.__setitem__.called or mock_response.cookie.__getitem__.called


@pytest.mark.web
class TestWebInterfaceLogin:
    """Tests for user login handler."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_user_login_blocks_after_failed_attempts(self, mock_response, mock_request, api_config, temp_db):
        """user_login() should block IP after multiple failed attempts."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        mock_request.remote = Mock(ip='192.168.1.100')
        mock_response.cookie = {}

        # Reset state from other tests
        bookbagofholding.UPDATE_MSG = ''
        bookbagofholding.USER_BLOCKLIST = []

        # Add 5 failed attempts for this IP
        import time
        for i in range(5):
            bookbagofholding.USER_BLOCKLIST.append(('192.168.1.100', int(time.time())))

        wi = WebInterface()
        result = wi.user_login(username='test', password='wrong')

        assert 'blocked' in result.lower()

        bookbagofholding.USER_BLOCKLIST = []

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_user_login_accepts_valid_credentials(self, mock_response, mock_request, api_config, temp_db):
        """user_login() should accept valid username/password (database-backed auth)."""
        from bookbagofholding.webServe import WebInterface
        from bookbagofholding.database import DBConnection

        mock_request.cookie = {}
        mock_request.remote = Mock(ip='127.0.0.1')
        mock_request.headers = {'User-Agent': 'test'}
        mock_response.cookie = MagicMock()

        bookbagofholding.USER_BLOCKLIST = []
        bookbagofholding.SHOWLOGOUT = 0
        bookbagofholding.CONFIG['AUTH_METHOD'] = 'Forms'

        # Create user in database
        pwd_hash = hashlib.md5('testpass'.encode()).hexdigest()
        db = DBConnection()
        db.action(
            "INSERT OR REPLACE INTO users (UserID, UserName, Password, PasswordAlgorithm, Perms, Role) VALUES (?, ?, ?, ?, ?, ?)",
            ['test-user-1', 'testuser', pwd_hash, 'md5', 65535, 'admin']
        )

        wi = WebInterface()

        # Successful login raises HTTPRedirect to home page
        import cherrypy
        with pytest.raises(cherrypy.HTTPRedirect) as exc_info:
            wi.user_login(username='testuser', password='testpass')
        assert exc_info.value.urls[0] == '/'
        assert bookbagofholding.SHOWLOGOUT == 1

        bookbagofholding.USER_BLOCKLIST = []
        bookbagofholding.SHOWLOGOUT = 0

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_user_login_rejects_wrong_password(self, mock_response, mock_request, api_config, temp_db):
        """user_login() should reject wrong password (config-based auth)."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        mock_request.remote = Mock(ip='127.0.0.1')
        mock_response.cookie = {}

        # Reset state from other tests
        bookbagofholding.UPDATE_MSG = ''
        bookbagofholding.USER_BLOCKLIST = []
        bookbagofholding.LOGIN_MSG = ''

        # Set up config-based credentials
        pwd_hash = hashlib.md5('testpass'.encode()).hexdigest()
        bookbagofholding.CONFIG['AUTH_METHOD'] = 'Forms'
        bookbagofholding.CONFIG['AUTH_USERNAME'] = 'wrongpassuser'
        bookbagofholding.CONFIG['AUTH_PASSWORD'] = pwd_hash

        wi = WebInterface()
        result = wi.user_login(username='wrongpassuser', password='wrongpassword')

        # Result is bytes from template render
        if isinstance(result, bytes):
            result = result.decode('utf-8')
        assert 'wrong password' in result.lower() or 'attempt' in result.lower() or 'invalid' in result.lower()

        bookbagofholding.USER_BLOCKLIST = []

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_user_login_rejects_invalid_user(self, mock_response, mock_request, api_config, temp_db):
        """user_login() should reject invalid username (config-based auth)."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        mock_request.remote = Mock(ip='127.0.0.1')
        mock_response.cookie = {}

        # Reset state from other tests
        bookbagofholding.UPDATE_MSG = ''
        bookbagofholding.USER_BLOCKLIST = []

        # Set up config-based credentials
        pwd_hash = hashlib.md5('testpass'.encode()).hexdigest()
        bookbagofholding.CONFIG['AUTH_METHOD'] = 'Forms'
        bookbagofholding.CONFIG['AUTH_USERNAME'] = 'admin'
        bookbagofholding.CONFIG['AUTH_PASSWORD'] = pwd_hash

        wi = WebInterface()
        result = wi.user_login(username='nonexistent', password='anypass')

        # Result is bytes from template render
        if isinstance(result, bytes):
            result = result.decode('utf-8')
        assert 'invalid' in result.lower() or 'incorrect' in result.lower()

        bookbagofholding.USER_BLOCKLIST = []


# ============================================================================
# Test getIndex DataTable Handler
# ============================================================================

@pytest.mark.web
class TestWebInterfaceGetIndex:
    """Tests for getIndex DataTable JSON handler."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_getIndex_returns_json_structure(self, mock_response, mock_request, api_config, temp_db):
        """getIndex() should return proper DataTable JSON structure."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        bookbagofholding.IGNORED_AUTHORS = 0

        wi = WebInterface()
        result = wi.getIndex(iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0='asc', sSearch='')

        assert 'iTotalRecords' in result
        assert 'iTotalDisplayRecords' in result
        assert 'aaData' in result

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_getIndex_returns_authors(self, mock_response, mock_request, api_config, temp_db, sample_author_data):
        """getIndex() should return authors from database."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        bookbagofholding.IGNORED_AUTHORS = 0

        # Insert test author with required columns
        db = DBConnection()
        db.action(
            """INSERT INTO authors (AuthorID, AuthorName, AuthorImg, Status, HaveBooks, UnignoredBooks,
               LastBook, LastDate, LastBookID, AuthorLink, LastLink)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [sample_author_data['AuthorID'], sample_author_data['AuthorName'],
             sample_author_data['AuthorImg'], 'Active', 5, 10, 'Last Book', '2023-01-01',
             'last-book-id', 'http://example.com', 'http://example.com/last']
        )

        wi = WebInterface()
        result = wi.getIndex(iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0='asc', sSearch='')

        assert result['iTotalRecords'] >= 1
        assert len(result['aaData']) >= 1

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_getIndex_handles_empty_database(self, mock_response, mock_request, api_config, temp_db):
        """getIndex() should handle empty database gracefully."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        bookbagofholding.IGNORED_AUTHORS = 0

        wi = WebInterface()
        result = wi.getIndex(iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0='asc', sSearch='')

        assert result['iTotalRecords'] == 0
        assert result['aaData'] == []

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_getIndex_filters_by_search_term(self, mock_response, mock_request, api_config, temp_db, sample_author_data):
        """getIndex() should filter results by search term."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        bookbagofholding.IGNORED_AUTHORS = 0

        # Insert two authors
        db = DBConnection()
        db.action(
            """INSERT INTO authors (AuthorID, AuthorName, AuthorImg, Status, HaveBooks, UnignoredBooks,
               LastBook, LastDate, LastBookID, AuthorLink, LastLink)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [sample_author_data['AuthorID'], 'John Smith', '', 'Active', 5, 10, '', '', '', '', '']
        )
        db.action(
            """INSERT INTO authors (AuthorID, AuthorName, AuthorImg, Status, HaveBooks, UnignoredBooks,
               LastBook, LastDate, LastBookID, AuthorLink, LastLink)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ['other-author', 'Jane Doe', '', 'Active', 3, 8, '', '', '', '', '']
        )

        wi = WebInterface()
        result = wi.getIndex(iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0='asc', sSearch='John')

        assert result['iTotalDisplayRecords'] == 1

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_getIndex_excludes_ignored_authors_by_default(self, mock_response, mock_request, api_config, temp_db):
        """getIndex() should exclude ignored authors when IGNORED_AUTHORS is 0."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        bookbagofholding.IGNORED_AUTHORS = 0

        db = DBConnection()
        db.action(
            """INSERT INTO authors (AuthorID, AuthorName, AuthorImg, Status, HaveBooks, UnignoredBooks,
               LastBook, LastDate, LastBookID, AuthorLink, LastLink)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ['ignored-author', 'Ignored Person', '', 'Ignored', 0, 0, '', '', '', '', '']
        )

        wi = WebInterface()
        result = wi.getIndex(iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0='asc', sSearch='')

        assert result['iTotalRecords'] == 0


# ============================================================================
# Test User Admin Handlers
# ============================================================================

@pytest.mark.web
class TestWebInterfaceAdminDelete:
    """Tests for admin user deletion handler."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_admin_delete_prevents_last_admin_deletion(self, mock_response, mock_request, api_config, temp_db):
        """admin_delete() should prevent deleting the last administrator."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}

        # Create only one admin user (perms & 1 = config permission = admin indicator)
        db = DBConnection()
        db.action("INSERT INTO users (UserID, UserName, Password, Perms) VALUES (?, ?, ?, ?)",
                  ['admin-001', 'lastadmin', 'hash', 65535])

        wi = WebInterface()
        result = wi.admin_delete(user='lastadmin')

        assert 'unable to delete last administrator' in result.lower()

        # Verify user still exists
        user = db.match("SELECT * FROM users WHERE UserName=?", ('lastadmin',))
        assert user is not None

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_admin_delete_allows_deletion_when_multiple_admins(self, mock_response, mock_request, api_config, temp_db):
        """admin_delete() should allow deletion when multiple admins exist."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}

        # Create two admin users
        db = DBConnection()
        db.action("INSERT INTO users (UserID, UserName, Password, Perms) VALUES (?, ?, ?, ?)",
                  ['admin-001', 'admin1', 'hash', 65535])
        db.action("INSERT INTO users (UserID, UserName, Password, Perms) VALUES (?, ?, ?, ?)",
                  ['admin-002', 'admin2', 'hash', 65535])

        wi = WebInterface()
        result = wi.admin_delete(user='admin1')

        assert 'deleted' in result.lower()

        # Verify user was deleted
        user = db.match("SELECT * FROM users WHERE UserName=?", ('admin1',))
        assert user is None or user == []

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_admin_delete_returns_error_for_nonexistent_user(self, mock_response, mock_request, api_config, temp_db):
        """admin_delete() should return error for nonexistent user."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}

        wi = WebInterface()
        result = wi.admin_delete(user='nonexistent')

        assert 'not found' in result.lower()


# ============================================================================
# Test User Registration Handler
# ============================================================================

@pytest.mark.web
class TestWebInterfaceUserRegister:
    """Tests for user registration handler."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    @patch('bookbagofholding.webServe.serve_template')
    def test_user_register_serves_register_template(self, mock_serve, mock_response, mock_request, api_config, temp_db):
        """user_register() should serve register.html template."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        mock_serve.return_value = '<html>register</html>'

        wi = WebInterface()
        wi.user_register()

        mock_serve.assert_called_once()
        call_kwargs = mock_serve.call_args[1]
        assert 'register' in call_kwargs['templatename']


# ============================================================================
# Test User Update Handler
# ============================================================================

@pytest.mark.web
class TestWebInterfaceUserUpdate:
    """Tests for user update handler."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_user_update_rejects_mismatched_passwords(self, mock_response, mock_request, api_config, temp_db):
        """user_update() should reject mismatched passwords."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {'ll_uid': Mock(value='test-user')}

        wi = WebInterface()
        result = wi.user_update(password='pass1', password2='pass2', username='', fullname='', email='', sendto='', booktype='')

        assert 'passwords do not match' in result.lower()

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_user_update_rejects_short_password(self, mock_response, mock_request, api_config, temp_db):
        """user_update() should reject passwords shorter than 8 characters."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {'ll_uid': Mock(value='test-user')}

        wi = WebInterface()
        result = wi.user_update(password='short', password2='short', username='', fullname='', email='', sendto='', booktype='')

        assert 'at least 8' in result.lower()

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_user_update_returns_not_logged_in_without_cookie(self, mock_response, mock_request, api_config, temp_db):
        """user_update() should return 'Not logged in' when no session is present."""
        from bookbagofholding.webServe import WebInterface

        # No cookie means not logged in
        mock_request.cookie = {}

        wi = WebInterface()
        result = wi.user_update(
            password='', password2='',
            username='testuser',
            fullname='Test Name',
            email='test@test.com',
            sendto=''
        )

        assert 'not logged in' in result.lower()


# ============================================================================
# Test Admin User Data Handler
# ============================================================================

@pytest.mark.web
class TestWebInterfaceAdminUserData:
    """Tests for admin user data retrieval handler."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_admin_userdata_returns_user_details(self, mock_response, mock_request, api_config, temp_db):
        """admin_userdata() should return user details as JSON."""
        import json
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}

        # Create test user with all fields
        db = DBConnection()
        db.action(
            """INSERT INTO users (UserID, UserName, Password, Name, Email, Perms,
               CalibreRead, CalibreToRead, SendTo, BookType)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ['user-data-test', 'datauser', 'hash', 'Test Name', 'test@email.com',
             65535, 'read_col', 'toread_col', 'sendto@email.com', 'epub']
        )

        wi = WebInterface()
        result = wi.admin_userdata(user='datauser')

        parsed = json.loads(result)
        assert parsed['email'] == 'test@email.com'
        assert parsed['name'] == 'Test Name'
        assert parsed['userid'] == 'user-data-test'

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_admin_userdata_returns_empty_for_missing_user(self, mock_response, mock_request, api_config, temp_db):
        """admin_userdata() should return empty data for nonexistent user."""
        import json
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}

        wi = WebInterface()
        result = wi.admin_userdata(user='nonexistent')

        parsed = json.loads(result)
        assert parsed['email'] == ''
        assert parsed['userid'] == ''


# ============================================================================
# Test User Admin Handler
# ============================================================================

@pytest.mark.web
class TestWebInterfaceUserAdmin:
    """Tests for user admin listing handler."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    @patch('bookbagofholding.webServe.serve_template')
    def test_userAdmin_serves_users_template(self, mock_serve, mock_response, mock_request, api_config, temp_db):
        """userAdmin() should serve users.html template."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        mock_serve.return_value = '<html>users</html>'

        # Create test users
        db = DBConnection()
        db.action("INSERT INTO users (UserID, UserName, Password, Perms) VALUES (?, ?, ?, ?)",
                  ['user-001', 'testuser1', 'hash', 65535])
        db.action("INSERT INTO users (UserID, UserName, Password, Perms) VALUES (?, ?, ?, ?)",
                  ['user-002', 'testuser2', 'hash', 4320])

        wi = WebInterface()
        wi.userAdmin()

        mock_serve.assert_called()
        call_kwargs = mock_serve.call_args[1]
        assert call_kwargs['templatename'] == 'users.html'
        assert 'users' in call_kwargs
        assert len(call_kwargs['users']) == 2


# ============================================================================
# Test API Key Handlers
# ============================================================================

@pytest.mark.web
class TestWebInterfaceApiKeyHandlers:
    """Tests for API key generation and revocation handlers."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_generateUserApiKey_returns_key(self, mock_response, mock_request, api_config, temp_db):
        """generateUserApiKey() should return a 32-char API key."""
        from bookbagofholding.webServe import WebInterface
        from bookbagofholding.database import DBConnection
        from datetime import datetime, timedelta

        # Create user and session
        db = DBConnection()
        user_id = 'apikey-test-user'
        session_id = 'valid-session-for-apikey'
        expiry = (datetime.now() + timedelta(hours=1)).isoformat()

        db.action(
            "INSERT INTO users (UserID, UserName, Password, Perms) VALUES (?, ?, ?, ?)",
            [user_id, 'apikeyuser', 'hash', 65535]
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            [session_id, user_id, datetime.now().isoformat(), expiry]
        )

        mock_request.cookie = {'ll_uid': MagicMock(value=session_id)}

        wi = WebInterface()
        result = wi.generateUserApiKey()

        assert len(result) == 32
        # Verify key is stored in database
        user = db.match("SELECT ApiKey FROM users WHERE UserID=?", (user_id,))
        assert user['ApiKey'] == result

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_generateUserApiKey_returns_error_without_session(self, mock_response, mock_request, api_config, temp_db):
        """generateUserApiKey() should return error without valid session."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}

        wi = WebInterface()
        result = wi.generateUserApiKey()

        assert 'not logged in' in result.lower()

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_revokeUserApiKey_clears_key(self, mock_response, mock_request, api_config, temp_db):
        """revokeUserApiKey() should clear the user's API key."""
        from bookbagofholding.webServe import WebInterface
        from bookbagofholding.database import DBConnection
        from datetime import datetime, timedelta

        # Create user with API key and session
        db = DBConnection()
        user_id = 'revoke-apikey-user'
        session_id = 'valid-session-for-revoke'
        expiry = (datetime.now() + timedelta(hours=1)).isoformat()

        db.action(
            "INSERT INTO users (UserID, UserName, Password, Perms, ApiKey) VALUES (?, ?, ?, ?, ?)",
            [user_id, 'revokeuser', 'hash', 65535, 'existing-api-key-12345678']
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            [session_id, user_id, datetime.now().isoformat(), expiry]
        )

        mock_request.cookie = {'ll_uid': MagicMock(value=session_id)}

        wi = WebInterface()
        result = wi.revokeUserApiKey()

        assert 'revoked' in result.lower()
        # Verify key is cleared in database
        user = db.match("SELECT ApiKey FROM users WHERE UserID=?", (user_id,))
        assert user['ApiKey'] is None


# ============================================================================
# Test Session Handlers
# ============================================================================

@pytest.mark.web
class TestWebInterfaceSessionHandlers:
    """Tests for session revocation handlers."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_revokeSession_deletes_specific_session(self, mock_response, mock_request, api_config, temp_db):
        """revokeSession() should delete a specific session."""
        from bookbagofholding.webServe import WebInterface
        from bookbagofholding.database import DBConnection
        from datetime import datetime, timedelta

        # Create user with multiple sessions
        db = DBConnection()
        user_id = 'revoke-session-user'
        current_session = 'current-session-id'
        other_session = 'other-session-to-revoke'
        expiry = (datetime.now() + timedelta(hours=1)).isoformat()

        db.action(
            "INSERT INTO users (UserID, UserName, Password, Perms) VALUES (?, ?, ?, ?)",
            [user_id, 'sessionuser', 'hash', 65535]
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            [current_session, user_id, datetime.now().isoformat(), expiry]
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            [other_session, user_id, datetime.now().isoformat(), expiry]
        )

        mock_request.cookie = {'ll_uid': MagicMock(value=current_session)}

        wi = WebInterface()
        result = wi.revokeSession(session_id=other_session)

        assert 'revoked' in result.lower()
        # Verify other session is deleted
        session = db.match("SELECT * FROM sessions WHERE SessionID=?", (other_session,))
        assert not session
        # Verify current session still exists
        session = db.match("SELECT * FROM sessions WHERE SessionID=?", (current_session,))
        assert session is not None

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_revokeSession_requires_session_id(self, mock_response, mock_request, api_config, temp_db):
        """revokeSession() should require session_id parameter."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}

        wi = WebInterface()
        result = wi.revokeSession()

        assert 'missing' in result.lower()

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_revokeAllSessions_keeps_current_session(self, mock_response, mock_request, api_config, temp_db):
        """revokeAllSessions() should delete all sessions except current."""
        from bookbagofholding.webServe import WebInterface
        from bookbagofholding.database import DBConnection
        from datetime import datetime, timedelta

        # Create user with multiple sessions
        db = DBConnection()
        user_id = 'revoke-all-user'
        current_session = 'current-session-keep'
        expiry = (datetime.now() + timedelta(hours=1)).isoformat()

        db.action(
            "INSERT INTO users (UserID, UserName, Password, Perms) VALUES (?, ?, ?, ?)",
            [user_id, 'allsessionsuser', 'hash', 65535]
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            [current_session, user_id, datetime.now().isoformat(), expiry]
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            ['other-session-1', user_id, datetime.now().isoformat(), expiry]
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            ['other-session-2', user_id, datetime.now().isoformat(), expiry]
        )

        mock_request.cookie = {'ll_uid': MagicMock(value=current_session)}

        wi = WebInterface()
        result = wi.revokeAllSessions()

        assert 'revoked' in result.lower()
        assert '2' in result  # Should say "Revoked 2 session(s)"
        # Verify current session still exists
        session = db.match("SELECT * FROM sessions WHERE SessionID=?", (current_session,))
        assert session is not None
        # Verify other sessions are gone
        sessions = db.select("SELECT * FROM sessions WHERE UserID=?", (user_id,))
        assert len(sessions) == 1


# ============================================================================
# Test User Update with Session
# ============================================================================

@pytest.mark.web
class TestWebInterfaceUserUpdateWithSession:
    """Tests for user update handler with valid session."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_user_update_changes_email(self, mock_response, mock_request, api_config, temp_db):
        """user_update() should update email for logged in user."""
        from bookbagofholding.webServe import WebInterface
        from bookbagofholding.database import DBConnection
        from datetime import datetime, timedelta

        # Create user with session
        db = DBConnection()
        user_id = 'update-email-user'
        session_id = 'session-for-update'
        expiry = (datetime.now() + timedelta(hours=1)).isoformat()

        db.action(
            "INSERT INTO users (UserID, UserName, Password, Email, Name, Perms, PasswordAlgorithm) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [user_id, 'updateuser', 'hash', 'old@email.com', 'Old Name', 65535, 'md5']
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            [session_id, user_id, datetime.now().isoformat(), expiry]
        )

        mock_request.cookie = {'ll_uid': MagicMock(value=session_id)}

        wi = WebInterface()
        result = wi.user_update(
            username='updateuser',
            fullname='Old Name',
            email='new@email.com',
            sendto='',
            password='',
            password2=''
        )

        assert 'email' in result.lower()
        # Verify email changed in database
        user = db.match("SELECT Email FROM users WHERE UserID=?", (user_id,))
        assert user['Email'] == 'new@email.com'

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_user_update_changes_name(self, mock_response, mock_request, api_config, temp_db):
        """user_update() should update name for logged in user."""
        from bookbagofholding.webServe import WebInterface
        from bookbagofholding.database import DBConnection
        from datetime import datetime, timedelta

        # Create user with session
        db = DBConnection()
        user_id = 'update-name-user'
        session_id = 'session-for-name-update'
        expiry = (datetime.now() + timedelta(hours=1)).isoformat()

        db.action(
            "INSERT INTO users (UserID, UserName, Password, Email, Name, Perms, PasswordAlgorithm) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [user_id, 'nameuser', 'hash', 'test@email.com', 'Old Name', 65535, 'md5']
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            [session_id, user_id, datetime.now().isoformat(), expiry]
        )

        mock_request.cookie = {'ll_uid': MagicMock(value=session_id)}

        wi = WebInterface()
        result = wi.user_update(
            username='nameuser',
            fullname='New Name',
            email='test@email.com',
            sendto='',
            password='',
            password2=''
        )

        assert 'name' in result.lower()
        # Verify name changed in database
        user = db.match("SELECT Name FROM users WHERE UserID=?", (user_id,))
        assert user['Name'] == 'New Name'

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_user_update_changes_password(self, mock_response, mock_request, api_config, temp_db):
        """user_update() should update password for logged in user."""
        from bookbagofholding.webServe import WebInterface
        from bookbagofholding.database import DBConnection
        from datetime import datetime, timedelta

        # Create user with session
        db = DBConnection()
        user_id = 'update-password-user'
        session_id = 'session-for-password-update'
        old_password_hash = 'oldhash12345'
        expiry = (datetime.now() + timedelta(hours=1)).isoformat()

        db.action(
            "INSERT INTO users (UserID, UserName, Password, Email, Perms, PasswordAlgorithm) VALUES (?, ?, ?, ?, ?, ?)",
            [user_id, 'passuser', old_password_hash, 'test@email.com', 65535, 'md5']
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            [session_id, user_id, datetime.now().isoformat(), expiry]
        )

        mock_request.cookie = {'ll_uid': MagicMock(value=session_id)}

        wi = WebInterface()
        result = wi.user_update(
            username='passuser',
            fullname='',
            email='test@email.com',
            sendto='',
            password='newpassword123',
            password2='newpassword123'
        )

        assert 'password' in result.lower()
        # Verify password changed in database
        user = db.match("SELECT Password FROM users WHERE UserID=?", (user_id,))
        assert user['Password'] != old_password_hash


# ============================================================================
# Test Label Thread Helper
# ============================================================================

@pytest.mark.web
class TestWebInterfaceLabelThread:
    """Tests for label_thread helper method."""

    def test_label_thread_sets_name(self, api_config):
        """label_thread() should set the thread name."""
        import threading
        from bookbagofholding.webServe import WebInterface

        wi = WebInterface()
        wi.label_thread("TEST-THREAD")

        assert threading.currentThread().name == "TEST-THREAD"

    def test_label_thread_sets_webserver_for_generic_threads(self, api_config):
        """label_thread() without name should set WEBSERVER for Thread-* names."""
        import threading
        from bookbagofholding.webServe import WebInterface

        # Save original name
        original_name = threading.currentThread().name

        # Set a Thread- style name
        threading.currentThread().name = "Thread-123"

        wi = WebInterface()
        wi.label_thread()

        assert threading.currentThread().name == "WEBSERVER"

        # Restore original name
        threading.currentThread().name = original_name


# ============================================================================
# Test Profile Handler
# ============================================================================

@pytest.mark.web
class TestWebInterfaceProfile:
    """Tests for user profile handler."""

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    @patch('bookbagofholding.webServe.serve_template')
    def test_profile_serves_profile_template_for_logged_in_user(self, mock_serve, mock_response, mock_request, api_config, temp_db):
        """profile() should serve profile.html for logged in user (database-backed auth)."""
        from bookbagofholding.webServe import WebInterface
        from bookbagofholding.database import DBConnection
        from datetime import datetime, timedelta

        bookbagofholding.CONFIG['AUTH_METHOD'] = 'Forms'

        # Create user and session in database
        db = DBConnection()
        user_id = 'test-profile-user'
        session_id = 'valid-session-id'
        expiry = (datetime.now() + timedelta(hours=1)).isoformat()

        db.action(
            "INSERT OR REPLACE INTO users (UserID, UserName, Password, PasswordAlgorithm, Perms, Role, Email) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [user_id, 'profileuser', 'hash', 'md5', 65535, 'admin', 'test@email.com']
        )
        db.action(
            "INSERT INTO sessions (SessionID, UserID, CreatedAt, ExpiresAt) VALUES (?, ?, ?, ?)",
            [session_id, user_id, datetime.now().isoformat(), expiry]
        )

        mock_request.cookie = {'ll_uid': Mock(value=session_id)}
        mock_request.headers = {}
        mock_serve.return_value = '<html>profile</html>'

        wi = WebInterface()
        wi.profile()

        mock_serve.assert_called()
        call_kwargs = mock_serve.call_args[1]
        assert call_kwargs['templatename'] == 'profile.html'

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    def test_profile_redirects_to_login_without_session(self, mock_response, mock_request, api_config, temp_db):
        """profile() should redirect to login without valid session."""
        from bookbagofholding.webServe import WebInterface
        import cherrypy

        bookbagofholding.CONFIG['AUTH_METHOD'] = 'Forms'

        mock_request.cookie = {}
        mock_request.headers = {}

        wi = WebInterface()

        # Should raise HTTPRedirect to login
        with pytest.raises(cherrypy.HTTPRedirect) as exc_info:
            wi.profile()
        assert 'login' in exc_info.value.urls[0]


# ============================================================================
# Test Interactive Search Handler (category-fallback behavior)
# ============================================================================

@pytest.mark.web
class TestGetInteractiveSearchResults:
    """Tests for getInteractiveSearchResults — verifies the auto-fallback
    behavior when a cat-filtered search returns zero results."""

    def _seed_book(self, db, bookid='book-1', author='Test Author', title='Test Book'):
        db.action(
            "INSERT INTO authors (AuthorID, AuthorName, AuthorImg, Status, HaveBooks, UnignoredBooks,"
            " LastBook, LastDate, LastBookID, AuthorLink, LastLink)"
            " VALUES (?, ?, '', 'Active', 0, 0, '', '', '', '', '')",
            ['author-1', author]
        )
        db.action(
            "INSERT INTO books (BookID, AuthorID, BookName, Status) VALUES (?, ?, ?, 'Wanted')",
            [bookid, 'author-1', title]
        )

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    @patch('bookbagofholding.webServe.searchItem')
    def test_falls_back_to_general_when_cat_returns_zero(
            self, mock_search, mock_response, mock_request, api_config, temp_db):
        """When cat='book' returns nothing, the handler should re-call with cat='general'
        and return its results, marked with used_fallback=True."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        db = DBConnection()
        self._seed_book(db)

        # First call returns nothing, second call (general) returns one result
        mock_search.side_effect = [
            [],
            [{'score': 90, 'title': 'Test Book Edition', 'provider': 'P1',
              'size': '1000000', 'date': 'Fri, 01 Jan 2026 00:00:00 +0000',
              'url': 'http%3A%2F%2Fexample.com%2Fa', 'mode': 'nzb'}],
        ]

        wi = WebInterface()
        result = wi.getInteractiveSearchResults(bookid='book-1', library='eBook', showall='0')

        assert result['success'] is True
        assert result['used_fallback'] is True
        assert result['count'] == 1
        # Two calls: first with cat='book', second with cat='general'
        assert mock_search.call_count == 2
        first_call = mock_search.call_args_list[0]
        second_call = mock_search.call_args_list[1]
        assert first_call[0][2] == 'book'
        assert second_call[0][2] == 'general'

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    @patch('bookbagofholding.webServe.searchItem')
    def test_no_fallback_when_initial_results_nonempty(
            self, mock_search, mock_response, mock_request, api_config, temp_db):
        """When the cat-filtered search already has results, no fallback call should fire."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        db = DBConnection()
        self._seed_book(db)

        mock_search.return_value = [
            {'score': 85, 'title': 'Test Book', 'provider': 'P1',
             'size': '500000', 'date': 'Fri, 01 Jan 2026 00:00:00 +0000',
             'url': 'http%3A%2F%2Fexample.com%2Fb', 'mode': 'nzb'}
        ]

        wi = WebInterface()
        result = wi.getInteractiveSearchResults(bookid='book-1', library='eBook', showall='0')

        assert result['success'] is True
        assert result['used_fallback'] is False
        assert result['count'] == 1
        # Only the initial call — no fallback re-run
        assert mock_search.call_count == 1

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    @patch('bookbagofholding.webServe.searchItem')
    def test_no_fallback_when_showall_already_set(
            self, mock_search, mock_response, mock_request, api_config, temp_db):
        """showall=1 already uses cat='general', so falling back would just repeat the same call."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        db = DBConnection()
        self._seed_book(db)

        mock_search.return_value = []  # zero results even from general

        wi = WebInterface()
        result = wi.getInteractiveSearchResults(bookid='book-1', library='eBook', showall='1')

        assert result['success'] is True
        assert result['used_fallback'] is False
        assert result['count'] == 0
        assert mock_search.call_count == 1
        assert mock_search.call_args_list[0][0][2] == 'general'

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    @patch('bookbagofholding.webServe.searchItem')
    def test_used_fallback_false_when_fallback_also_empty(
            self, mock_search, mock_response, mock_request, api_config, temp_db):
        """If both the initial and the fallback search return nothing, used_fallback stays False
        (no point telling the UI "fallback happened" when there was nothing to surface)."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        db = DBConnection()
        self._seed_book(db)

        mock_search.side_effect = [[], []]

        wi = WebInterface()
        result = wi.getInteractiveSearchResults(bookid='book-1', library='eBook', showall='0')

        assert result['success'] is True
        assert result['used_fallback'] is False
        assert result['count'] == 0
        assert mock_search.call_count == 2

    @patch('cherrypy.request')
    @patch('cherrypy.response')
    @patch('bookbagofholding.webServe.searchItem')
    def test_audiobook_library_falls_back_from_audio(
            self, mock_search, mock_response, mock_request, api_config, temp_db):
        """AudioBook searches should fall back from cat='audio' to cat='general'."""
        from bookbagofholding.webServe import WebInterface

        mock_request.cookie = {}
        db = DBConnection()
        self._seed_book(db)

        mock_search.side_effect = [
            [],
            [{'score': 75, 'title': 'Test Book (Unabridged)', 'provider': 'P1',
              'size': '50000000', 'date': 'Fri, 01 Jan 2026 00:00:00 +0000',
              'url': 'http%3A%2F%2Fexample.com%2Fc', 'mode': 'nzb'}],
        ]

        wi = WebInterface()
        result = wi.getInteractiveSearchResults(bookid='book-1', library='AudioBook', showall='0')

        assert result['success'] is True
        assert result['used_fallback'] is True
        assert mock_search.call_args_list[0][0][2] == 'audio'
        assert mock_search.call_args_list[1][0][2] == 'general'
