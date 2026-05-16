#  This file is part of Bookbag of Holding.
#  Bookbag of Holding is free software':'you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  Bookbag of Holding is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with Bookbag of Holding.  If not, see <http://www.gnu.org/licenses/>.


import datetime
import hashlib
import os
import random
import re
import threading
import time
import traceback
from shutil import copyfile, rmtree

from urllib.parse import quote_plus, unquote_plus, urlsplit, urlunsplit
import json as simplejson

import cherrypy
import bookbagofholding
from cherrypy.lib.static import serve_file
from bookbagofholding import logger, database, \
    qbittorrent, utorrent, rtorrent, transmission, sabnzbd, nzbget, deluge, synology
from bookbagofholding.database import add_to_blacklist, mark_unmatched_file_matched, mark_unmatched_file_ignored
from bookbagofholding.cache import cache_img
from bookbagofholding.calibre import calibreTest, syncCalibreList, calibredb, calibreImportBook
from bookbagofholding.common import showJobs, showStats, restartJobs, clearLog, scheduleJob, checkRunningJobs, setperm, \
    aaUpdate, csv_file, saveLog, logHeader, pwd_generator, pwd_check, isValidEmail, mimeType, zipAudio, runScript
from bookbagofholding.csvfile import import_CSV, export_CSV, dump_table, restore_table
from bookbagofholding.downloadmethods import NZBDownloadMethod, TORDownloadMethod, DirectDownloadMethod
from bookbagofholding.formatter import unaccented, unaccented_str, plural, now, today, check_int, replace_all, \
    safe_unicode, cleanName, surnameFirst, sortDefinite, getList, makeUnicode, makeBytestr, md5_utf8, dateFormat, \
    check_year, dispName
from bookbagofholding.gb import GoogleBooks
from bookbagofholding.images import getBookCover, createMagCover
from bookbagofholding.importer import addAuthorToDB, addAuthorNameToDB, update_totals, search_for
from bookbagofholding.librarysync import LibraryScan
from bookbagofholding.manualbook import searchItem
from bookbagofholding.postprocess import processAlternate, processDir, delete_task, getDownloadProgress
from bookbagofholding.providers import test_provider
from bookbagofholding.searchbook import search_book
from bookbagofholding.searchrss import search_wishlist
from bookbagofholding.rssfeed import genFeed
from bookbagofholding.opds import OPDS
from bookbagofholding.bookrename import nameVars
from bookbagofholding.deluge_client import DelugeRPCClient
from mako import exceptions
from mako.lookup import TemplateLookup


def serve_template(templatename, **kwargs):
    """Serve a Mako template with database-backed authentication.

    AUTH_METHOD options:
    - None: No authentication, everyone has admin access
    - Forms: Login page with username/password (database users)
    - Basic: HTTP Basic Auth (handled by CherryPy in webStart.py)
    - External: Trust reverse proxy header (AUTH_HEADER config)
    """
    from bookbagofholding.web.auth import (
        get_user_count, get_current_user, get_session_from_cookie,
        get_user_by_session, get_user_by_username, create_user,
        PERM_ADMIN, PERM_GUEST
    )

    threading.currentThread().name = "WEBSERVER"
    interface_dir = os.path.join(str(bookbagofholding.PROG_DIR), 'data/interfaces/')
    template_dir = os.path.join(str(interface_dir), 'modern')

    _hplookup = TemplateLookup(directories=[template_dir], input_encoding='utf-8')
    # noinspection PyBroadException
    try:
        # Check for database upgrade in progress
        if bookbagofholding.UPDATE_MSG:
            template = _hplookup.get_template("dbupdate.html")
            return template.render(perm=0, message="Database upgrade in progress, please wait...",
                                   title="Database Upgrade", timer=5)

        # First-run check: If no users exist, show setup wizard
        auth_exempt_pages = ["login.html", "response.html", "setup.html"]
        user_count = get_user_count()
        if user_count == 0:
            if templatename not in auth_exempt_pages:
                template = _hplookup.get_template("setup.html")
                return template.render(perm=0, title="Initial Setup", message='')
            else:
                template = _hplookup.get_template(templatename)
                return template.render(perm=0, **kwargs)

        auth_method = bookbagofholding.CONFIG.get('AUTH_METHOD', 'Forms')
        username = ''
        fullname = ''
        perm = 0
        role = ''
        authenticated = False

        # Check authentication based on method
        if auth_method == 'None':
            # No authentication - everyone is admin
            authenticated = True
            username = 'admin'
            fullname = 'Admin'
            perm = PERM_ADMIN
            role = 'admin'
            bookbagofholding.SHOWLOGOUT = 0

        elif auth_method == 'External':
            # Trust reverse proxy header
            header_name = bookbagofholding.CONFIG.get('AUTH_HEADER', 'X-Forwarded-User')
            ext_username = cherrypy.request.headers.get(header_name, '')
            if ext_username:
                # Look up or create external user in database
                user = get_user_by_username(ext_username)
                if not user:
                    # Auto-create external users as guests
                    import secrets
                    create_user(ext_username, secrets.token_hex(32), role='guest')
                    user = get_user_by_username(ext_username)
                if user:
                    authenticated = True
                    username = user['UserName'] if user['UserName'] else ext_username
                    fullname = user['Name'] if user['Name'] else username
                    perm = user['Perms'] if user['Perms'] else PERM_GUEST
                    role = user['Role'] if user['Role'] else 'guest'
                    bookbagofholding.SHOWLOGOUT = 0
            else:
                logger.debug("External auth: No %s header found" % header_name)

        elif auth_method == 'Forms':
            # Check for session in database
            session_id = get_session_from_cookie()
            if session_id:
                user = get_user_by_session(session_id)
                if user:
                    authenticated = True
                    username = user['UserName'] if user['UserName'] else 'admin'
                    fullname = user['Name'] if user['Name'] else username
                    perm = user['Perms'] if user['Perms'] else PERM_ADMIN
                    role = user['Role'] if user['Role'] else 'admin'
                    bookbagofholding.SHOWLOGOUT = 1

        elif auth_method == 'Basic':
            # HTTP Basic Auth is handled by CherryPy in webStart.py
            # If we get here, user passed basic auth - look up in database
            basic_user = bookbagofholding.CONFIG.get('HTTP_USER', 'admin')
            user = get_user_by_username(basic_user)
            if user:
                authenticated = True
                username = user['UserName'] if user['UserName'] else basic_user
                fullname = user['Name'] if user['Name'] else username
                perm = user['Perms'] if user['Perms'] else PERM_ADMIN
                role = user['Role'] if user['Role'] else 'admin'
            else:
                # No matching database user - grant admin access for basic auth
                authenticated = True
                username = basic_user
                fullname = 'Admin'
                perm = PERM_ADMIN
                role = 'admin'
            bookbagofholding.SHOWLOGOUT = 0

        # Handle unauthenticated users for Forms auth
        if not authenticated and auth_method in ('Forms', 'External'):
            if templatename not in auth_exempt_pages:
                templatename = "login.html"
                kwargs['message'] = "Please log in to continue"

        if bookbagofholding.LOGLEVEL & bookbagofholding.log_admin:
            logger.debug("Auth: method=%s user=%s perm=%s auth=%s template=%s" %
                        (auth_method, username, perm, authenticated, templatename))

        template = _hplookup.get_template(templatename)
        if templatename == "login.html":
            message = kwargs.get('message', '')
            return template.render(perm=0, title="Login Required", message=message)
        else:
            # Remove auth-related keys from kwargs to avoid conflicts
            kwargs.pop('user', None)
            kwargs.pop('perm', None)
            kwargs.pop('role', None)
            kwargs.pop('fullname', None)
            # noinspection PyArgumentList
            return template.render(perm=perm, user=username, fullname=fullname, role=role, **kwargs)
    except Exception:
        return exceptions.html_error_template().render()


# noinspection PyProtectedMember
class WebInterface(object):
    @cherrypy.expose
    def index(self):
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def home(self):
        # Show dashboard with statistics
        return self._serve_dashboard()

    def _serve_dashboard(self):
        """Serve the modern theme dashboard with statistics and activity."""
        myDB = database.DBConnection()
        stats = {}
        activity = []

        # Gather statistics
        # Authors
        res = myDB.match("SELECT COUNT(*) as cnt FROM authors WHERE Status != 'Ignored'")
        stats['authors'] = res['cnt'] if res else 0
        res = myDB.match("SELECT COUNT(*) as cnt FROM authors WHERE Status = 'Active'")
        stats['authors_active'] = res['cnt'] if res else 0

        # Books (ebooks only - those with a Status set, excluding ignored)
        res = myDB.match("SELECT COUNT(*) as cnt FROM books WHERE Status IS NOT NULL AND Status != '' AND Status != 'Ignored'")
        stats['books'] = res['cnt'] if res else 0
        res = myDB.match("SELECT COUNT(*) as cnt FROM books WHERE Status = 'Open'")
        stats['books_have'] = res['cnt'] if res else 0

        # AudioBooks (excluding ignored)
        res = myDB.match("SELECT COUNT(*) as cnt FROM books WHERE AudioStatus IS NOT NULL AND AudioStatus != '' AND AudioStatus != 'Ignored'")
        stats['audiobooks'] = res['cnt'] if res else 0
        res = myDB.match("SELECT COUNT(*) as cnt FROM books WHERE AudioStatus = 'Open'")
        stats['audiobooks_have'] = res['cnt'] if res else 0

        # Wanted counts
        res = myDB.match("SELECT COUNT(*) as cnt FROM books WHERE Status = 'Wanted'")
        stats['wanted_books'] = res['cnt'] if res else 0
        res = myDB.match("SELECT COUNT(*) as cnt FROM books WHERE AudioStatus = 'Wanted'")
        stats['wanted_audio'] = res['cnt'] if res else 0
        stats['wanted'] = stats['wanted_books'] + stats['wanted_audio']

        # Recent activity from downloads table
        recent = myDB.select(
            "SELECT NZBtitle, NZBprov, NZBdate, Status, Source FROM wanted "
            "WHERE Status IN ('Snatched', 'Processed', 'Failed') "
            "ORDER BY NZBdate DESC LIMIT 10"
        )
        for item in recent:
            act_type = 'download'
            if item['Status'] == 'Failed':
                act_type = 'error'
            elif item['Status'] == 'Snatched':
                act_type = 'search'

            activity.append({
                'type': act_type,
                'title': item['NZBtitle'] or 'Unknown',
                'meta': '%s - %s' % (item['NZBprov'] or 'Unknown', item['NZBdate'] or '')
            })

        return serve_template(
            templatename="index.html",
            title='Dashboard',
            stats=stats,
            activity=activity,
            current_page='dashboard'
        )

    @cherrypy.expose
    def authors(self):
        """Serve the authors list page."""
        title = 'Authors'
        if bookbagofholding.IGNORED_AUTHORS:
            title = 'Ignored Authors'
        return serve_template(templatename="authors.html", title=title, authors=[], current_page='authors')

    @cherrypy.expose
    def profile(self):
        """Show user profile page with database-backed user info."""
        title = 'User Profile'
        from bookbagofholding.web.auth import (
            get_session_from_cookie, get_user_by_session, get_user_sessions
        )

        # Get current user from session
        session_id = get_session_from_cookie()
        user = get_user_by_session(session_id)

        if not user:
            # Not authenticated - redirect to login
            raise cherrypy.HTTPRedirect("login")

        # Get user's active sessions
        sessions = get_user_sessions(user['UserID'])

        return serve_template(
            templatename="profile.html", title=title,
            profile_user=user, sessions=sessions
        )

    @cherrypy.expose
    def generateUserApiKey(self):
        """Generate a new API key for the current user."""
        self.label_thread("APIKEY")
        from bookbagofholding.web.auth import (
            get_session_from_cookie, get_user_by_session, generate_user_api_key
        )

        session_id = get_session_from_cookie()
        user = get_user_by_session(session_id)

        if not user:
            return "Not logged in"

        api_key = generate_user_api_key(user['UserID'])
        return api_key

    @cherrypy.expose
    def revokeUserApiKey(self):
        """Revoke the current user's API key."""
        self.label_thread("APIKEY")
        from bookbagofholding.web.auth import (
            get_session_from_cookie, get_user_by_session, revoke_user_api_key
        )

        session_id = get_session_from_cookie()
        user = get_user_by_session(session_id)

        if not user:
            return "Not logged in"

        revoke_user_api_key(user['UserID'])
        return "API key revoked"

    @cherrypy.expose
    def revokeSession(self, session_id=None):
        """Revoke a specific session."""
        self.label_thread("SESSION")
        from bookbagofholding.web.auth import (
            get_session_from_cookie, get_user_by_session, revoke_session
        )

        if not session_id:
            return "Missing session ID"

        # Get current user from their session
        current_session_id = get_session_from_cookie()
        user = get_user_by_session(current_session_id)

        if not user:
            return "Not logged in"

        # Verify the session to revoke belongs to this user
        myDB = database.DBConnection()
        session = myDB.match(
            'SELECT UserID FROM sessions WHERE SessionID=?',
            (session_id,)
        )

        if session and session['UserID'] == user['UserID']:
            if revoke_session(session_id):
                return "Session revoked"
        return "Session not found or access denied"

    @cherrypy.expose
    def revokeAllSessions(self):
        """Revoke all sessions for the current user except the current one."""
        self.label_thread("SESSION")
        from bookbagofholding.web.auth import (
            get_session_from_cookie, get_user_by_session, revoke_user_sessions
        )

        current_session_id = get_session_from_cookie()
        user = get_user_by_session(current_session_id)

        if not user:
            return "Not logged in"

        revoked = revoke_user_sessions(user['UserID'], except_session_id=current_session_id)
        return "Revoked %s session(s)" % revoked

    # noinspection PyUnusedLocal
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getIndex(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            # kwargs is used by datatables to pass params
            # for arg in kwargs:
            #     print arg, kwargs[arg]
            myDB = database.DBConnection()
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            bookbagofholding.CONFIG['DISPLAYLENGTH'] = iDisplayLength

            cmd = 'SELECT AuthorImg,AuthorName,LastBook,LastDate,Status'
            cmd += ',AuthorLink,LastLink,HaveBooks,UnignoredBooks,AuthorID,LastBookID from authors '
            if bookbagofholding.IGNORED_AUTHORS:
                cmd += 'where Status == "Ignored" '
            else:
                cmd += 'where Status != "Ignored" '
            cmd += 'order by AuthorName COLLATE NOCASE'

            if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                logger.debug("getIndex %s" % cmd)

            rowlist = myDB.select(cmd)

            # Get book stats for all authors in one query
            ebook_stats = {}
            audio_stats = {}

            # eBook stats by author
            ebook_query = myDB.select(
                "SELECT AuthorID, Status, COUNT(*) as cnt FROM books GROUP BY AuthorID, Status")
            for row in ebook_query:
                aid = row['AuthorID']
                status = row['Status']
                count = row['cnt']
                if aid not in ebook_stats:
                    ebook_stats[aid] = {'total': 0, 'have': 0, 'skipped': 0, 'ignored': 0}
                ebook_stats[aid]['total'] += count
                if status == 'Open':
                    ebook_stats[aid]['have'] += count
                elif status == 'Skipped':
                    ebook_stats[aid]['skipped'] += count
                elif status == 'Ignored':
                    ebook_stats[aid]['ignored'] += count

            # AudioBook stats by author
            if bookbagofholding.SHOW_AUDIO:
                audio_query = myDB.select(
                    "SELECT AuthorID, AudioStatus, COUNT(*) as cnt FROM books "
                    "WHERE AudioStatus IS NOT NULL AND AudioStatus != '' GROUP BY AuthorID, AudioStatus")
                for row in audio_query:
                    aid = row['AuthorID']
                    status = row['AudioStatus']
                    count = row['cnt']
                    if aid not in audio_stats:
                        audio_stats[aid] = {'total': 0, 'have': 0, 'skipped': 0, 'ignored': 0}
                    audio_stats[aid]['total'] += count
                    if status == 'Open':
                        audio_stats[aid]['have'] += count
                    elif status == 'Skipped':
                        audio_stats[aid]['skipped'] += count
                    elif status == 'Ignored':
                        audio_stats[aid]['ignored'] += count

            # At his point we want to sort and filter _before_ adding the html as it's much quicker
            # turn the sqlite rowlist into a list of lists
            if len(rowlist):
                for row in rowlist:  # iterate through the sqlite3.Row objects
                    arow = list(row)
                    if bookbagofholding.CONFIG['SORT_SURNAME']:
                        arow[1] = surnameFirst(arow[1])
                    if bookbagofholding.CONFIG['SORT_DEFINITE']:
                        arow[2] = sortDefinite(arow[2])
                    nrow = arow[:4]
                    havebooks = check_int(arow[7], 0)
                    totalbooks = check_int(arow[8], 0)
                    if totalbooks:
                        percent = int((havebooks * 100.0) / totalbooks)
                    else:
                        percent = 0
                    if percent > 100:
                        percent = 100

                    if percent <= 25:
                        css = 'danger'
                    elif percent <= 50:
                        css = 'warning'
                    elif percent <= 75:
                        css = 'info'
                    else:
                        css = 'success'

                    nrow.append(percent)
                    nrow.extend(arow[4:])
                    nrow.append('')  # progress bar handled by frontend

                    # Add book stats (index 13)
                    author_id = arow[9]  # AuthorID
                    e_stats = ebook_stats.get(author_id, {'total': 0, 'have': 0, 'skipped': 0, 'ignored': 0})
                    a_stats = audio_stats.get(author_id, {'total': 0, 'have': 0, 'skipped': 0, 'ignored': 0})
                    nrow.append(e_stats)  # index 13: ebook_stats
                    nrow.append(a_stats)  # index 14: audio_stats

                    rows.append(nrow)  # add each rowlist to the masterlist
                if sSearch:
                    if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    filtered = [x for x in rows if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rows

                sortcolumn = int(iSortCol_0) - 1

                if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    rows = filtered
                else:
                    rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

            if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                logger.debug("getIndex returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getIndex filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getIndex: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @staticmethod
    def label_thread(name=None):
        if name:
            threading.currentThread().name = name
        else:
            threadname = threading.currentThread().name
            if "Thread-" in threadname:
                threading.currentThread().name = "WEBSERVER"

    # USERS ############################################################

    @cherrypy.expose
    def logout(self):
        cherrypy.response.cookie['ll_uid'] = ''
        cherrypy.response.cookie['ll_uid']['expires'] = 0
        # cherrypy.lib.sessions.expire()
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    @cherrypy.expose
    def setup(self):
        """Show the first-run setup wizard."""
        self.label_thread("SETUP")
        return serve_template(templatename="setup.html", title="Initial Setup")

    @cherrypy.expose
    def setupComplete(self, **kwargs):
        """Process the first-run setup wizard form.

        Creates the first admin user in the database.
        """
        from bookbagofholding.web.auth import get_user_count, create_user, PERM_ADMIN

        self.label_thread("SETUP")

        # Validate required fields
        username = kwargs.get('username', '').strip()
        password = kwargs.get('password', '')
        password2 = kwargs.get('password2', '')
        email = kwargs.get('email', '').strip()

        if not username:
            return serve_template(templatename="setup.html", title="Initial Setup",
                                  message="Username is required.")

        if len(username) < 3:
            return serve_template(templatename="setup.html", title="Initial Setup",
                                  message="Username must be at least 3 characters.")

        if not password:
            return serve_template(templatename="setup.html", title="Initial Setup",
                                  message="Password is required.")

        if password != password2:
            return serve_template(templatename="setup.html", title="Initial Setup",
                                  message="Passwords do not match.")

        if not pwd_check(password):
            return serve_template(templatename="setup.html", title="Initial Setup",
                                  message="Password must be at least 8 characters with no spaces.")

        # Check if users already exist
        if get_user_count() > 0:
            return serve_template(templatename="response.html", title="Setup Error",
                                  message="Setup has already been completed. Users already exist.")

        # Create admin user in database
        try:
            create_user(
                username=username,
                password=password,
                email=email,
                name=username,
                role='admin',
                perms=PERM_ADMIN
            )
        except Exception as e:
            logger.error("Failed to create admin user: %s" % str(e))
            return serve_template(templatename="setup.html", title="Initial Setup",
                                  message="Failed to create user: %s" % str(e))

        # Set AUTH_METHOD to Forms
        bookbagofholding.CONFIG['AUTH_METHOD'] = 'Forms'
        bookbagofholding.config_write('General')

        logger.info("Initial setup complete. Admin user '%s' created in database." % username)

        return serve_template(templatename="response.html", title="Setup Complete",
                              message="Your admin account has been created. You can now log in.",
                              timer=3)

    def user_register(self):
        self.label_thread("REGISTER")
        return serve_template(templatename="register.html", title="User Registration / Contact form")

    @cherrypy.expose
    def user_update(self, **kwargs):
        from bookbagofholding.web.auth import (
            get_session_from_cookie, get_user_by_session, hash_password
        )

        if 'password' in kwargs and 'password2' in kwargs and kwargs['password']:
            if kwargs['password'] != kwargs['password2']:
                return "Passwords do not match"
        if kwargs.get('password'):
            if not pwd_check(kwargs['password']):
                return "Password must be at least 8 digits long\nand not contain spaces"

        # Get current user from session
        session_id = get_session_from_cookie()
        user = get_user_by_session(session_id)

        if not user:
            return "Not logged in"

        userid = user['UserID']
        changes = ''
        myDB = database.DBConnection()

        if kwargs.get('username') and user['UserName'] != kwargs['username']:
            # if username changed, must not have same username as another user
            match = myDB.match('SELECT UserName from users where UserName=?', (kwargs['username'],))
            if match:
                return "Unable to change username: already exists"
            else:
                changes += ' username'
                myDB.action('UPDATE users SET UserName=? WHERE UserID=?', (kwargs['username'], userid))

        # Handle sqlite3.Row objects which don't have .get() method
        user_name = user['Name'] if user['Name'] else ''
        user_email = user['Email'] if user['Email'] else ''

        if kwargs.get('fullname') and user_name != kwargs['fullname']:
            changes += ' name'
            myDB.action('UPDATE users SET Name=? WHERE UserID=?', (kwargs['fullname'], userid))

        if user_email != kwargs.get('email', ''):
            changes += ' email'
            myDB.action('UPDATE users SET Email=? WHERE UserID=?', (kwargs.get('email', ''), userid))

        if kwargs.get('password'):
            pwd_hash, algorithm = hash_password(kwargs['password'])
            changes += ' password'
            myDB.action('UPDATE users SET Password=?, PasswordAlgorithm=? WHERE UserID=?',
                        (pwd_hash, algorithm, userid))

        if changes:
            return 'Updated user details:%s' % changes
        return "No changes made"

    @cherrypy.expose
    def user_login(self, **kwargs):
        """Handle login for Forms authentication (database-backed).

        Validates against users table in database.
        """
        from bookbagofholding.web.auth import (
            get_user_by_username, verify_password, create_session,
            set_session_cookie, hash_password
        )

        self.label_thread("LOGIN")

        # Rate limiting - block IP after 5 failed attempts in 1 hour
        limit = int(time.time()) - 1 * 60 * 60
        bookbagofholding.USER_BLOCKLIST[:] = [x for x in bookbagofholding.USER_BLOCKLIST if x[1] > limit]
        remote_ip = cherrypy.request.remote.ip
        cnt = sum(1 for item in bookbagofholding.USER_BLOCKLIST if item[0] == remote_ip)
        if cnt >= 5:
            msg = "IP address blocked due to too many failed attempts. Try again later."
            logger.warn("Blocked IP %s attempted login" % remote_ip)
            return serve_template(templatename="login.html", message=msg)

        username = kwargs.get('username', '').strip()
        password = kwargs.get('password', '')

        if not username or not password:
            return serve_template(templatename="login.html", message="Please enter username and password")

        # Look up user in database
        user = get_user_by_username(username)
        if not user:
            # Failed login - user not found
            bookbagofholding.USER_BLOCKLIST.append((remote_ip, int(time.time())))
            remaining = 5 - cnt - 1
            if remaining > 0:
                msg = "Invalid username or password. %s attempt%s remaining." % (remaining, plural(remaining))
            else:
                msg = "Invalid username or password. Too many failed attempts."
            logger.warn("Failed login attempt for '%s' from %s (user not found)" % (username, remote_ip))
            return serve_template(templatename="login.html", message=msg)

        # Verify password
        # Handle both dict and sqlite3.Row objects
        algorithm = user['PasswordAlgorithm'] if user['PasswordAlgorithm'] else 'md5'
        if not verify_password(password, user['Password'], algorithm):
            # Failed login - wrong password
            bookbagofholding.USER_BLOCKLIST.append((remote_ip, int(time.time())))
            remaining = 5 - cnt - 1
            if remaining > 0:
                msg = "Invalid username or password. %s attempt%s remaining." % (remaining, plural(remaining))
            else:
                msg = "Invalid username or password. Too many failed attempts."
            logger.warn("Failed login attempt for '%s' from %s (wrong password)" % (username, remote_ip))
            return serve_template(templatename="login.html", message=msg)

        # Success - create session
        user_agent = cherrypy.request.headers.get('User-Agent', '')
        session_id = create_session(user['UserID'], remote_ip, user_agent)
        set_session_cookie(session_id)

        # Update last login timestamp
        myDB = database.DBConnection()
        myDB.action('UPDATE users SET LastLogin=? WHERE UserID=?',
                    (datetime.datetime.now().isoformat(), user['UserID']))

        # Optionally upgrade MD5 password to bcrypt on successful login
        if algorithm == 'md5':
            try:
                new_hash, new_algorithm = hash_password(password, 'bcrypt')
                if new_algorithm == 'bcrypt':
                    myDB.action('UPDATE users SET Password=?, PasswordAlgorithm=?, PasswordChangedAt=? WHERE UserID=?',
                                (new_hash, new_algorithm, datetime.datetime.now().isoformat(), user['UserID']))
                    logger.info("Upgraded password hash to bcrypt for user %s" % username)
            except Exception as e:
                logger.debug("Could not upgrade password to bcrypt: %s" % str(e))

        # Clear failed attempts for this IP
        bookbagofholding.USER_BLOCKLIST[:] = [
            x for x in bookbagofholding.USER_BLOCKLIST if x[0] != remote_ip
        ]
        logger.info("User %s logged in from %s" % (username, remote_ip))
        bookbagofholding.SHOWLOGOUT = 1
        raise cherrypy.HTTPRedirect("/")

    @cherrypy.expose
    def forgotPassword(self, message=''):
        """Show the forgot password page."""
        self.label_thread("FORGOTPWD")
        return serve_template(templatename="forgotpassword.html", message=message)

    @cherrypy.expose
    def requestPasswordReset(self, username='', email=''):
        """Process password reset request."""
        self.label_thread("RESETREQ")

        if not username or not email:
            return serve_template(templatename="forgotpassword.html",
                                  message="Please enter both username and email")

        myDB = database.DBConnection()
        user = myDB.match('SELECT UserID, Email FROM users WHERE UserName=?', (username,))

        if not user:
            # Don't reveal whether user exists
            return serve_template(templatename="forgotpassword.html",
                                  message="If that account exists with that email, a reset link has been sent.")

        stored_email = user['Email'] if user['Email'] else ''
        if not stored_email or stored_email.lower() != email.lower():
            # Don't reveal whether email matches
            return serve_template(templatename="forgotpassword.html",
                                  message="If that account exists with that email, a reset link has been sent.")

        # Generate reset token
        import secrets
        import datetime
        token = secrets.token_urlsafe(32)
        expires = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        expires_str = expires.strftime("%Y-%m-%d %H:%M:%S")

        myDB.action('UPDATE users SET PasswordResetToken=?, PasswordResetExpiry=? WHERE UserID=?',
                    (token, expires_str, user['UserID']))

        # Build reset URL
        http_root = bookbagofholding.CONFIG.get('HTTP_ROOT', '')
        if http_root and not http_root.endswith('/'):
            http_root += '/'
        reset_url = "resetPassword?token=%s" % token

        # Try to send email if configured
        email_sent = False
        if bookbagofholding.CONFIG.get('EMAIL_SMTP_SERVER'):
            try:
                from bookbagofholding.common import notifyMessage
                subject = "Password Reset Request - Bookbag of Holding"
                body = """You requested a password reset for your Bookbag of Holding account.

Click the link below to reset your password:
%s%s

This link will expire in 1 hour.

If you did not request this reset, you can ignore this email.
""" % (cherrypy.request.base + '/' + http_root, reset_url)
                notifyMessage(subject, body, stored_email)
                email_sent = True
            except Exception as e:
                logger.error("Failed to send password reset email: %s" % str(e))

        if email_sent:
            return serve_template(templatename="forgotpassword.html",
                                  message="Password reset link sent! Check your email.")
        else:
            # No email configured - show token directly (for admin-assisted reset)
            logger.info("Password reset token generated for %s: %s" % (username, token))
            return serve_template(templatename="forgotpassword.html",
                                  message="Email not configured. Your reset token is: %s (expires in 1 hour). "
                                          "Use it at: resetPassword?token=%s" % (token, token))

    @cherrypy.expose
    def resetPassword(self, token='', message=''):
        """Show the password reset form."""
        self.label_thread("RESETPWD")

        if not token:
            return serve_template(templatename="login.html",
                                  message="Invalid or missing reset token")

        # Validate token
        import datetime
        myDB = database.DBConnection()
        user = myDB.match(
            'SELECT UserID, UserName, PasswordResetExpiry FROM users WHERE PasswordResetToken=?',
            (token,)
        )

        if not user:
            return serve_template(templatename="login.html",
                                  message="Invalid or expired reset token")

        expiry = user['PasswordResetExpiry'] if user['PasswordResetExpiry'] else ''
        if expiry:
            try:
                expiry_dt = datetime.datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
                if datetime.datetime.utcnow() > expiry_dt:
                    return serve_template(templatename="login.html",
                                          message="Reset token has expired. Please request a new one.")
            except ValueError:
                pass

        return serve_template(templatename="resetpassword.html",
                              token=token, username=user['UserName'], message=message)

    @cherrypy.expose
    def doResetPassword(self, token='', password='', password2=''):
        """Process the password reset."""
        self.label_thread("DORESET")

        if not token:
            return serve_template(templatename="login.html",
                                  message="Invalid reset token")

        if not password or not password2:
            return self.resetPassword(token=token, message="Please enter a password")

        if password != password2:
            return self.resetPassword(token=token, message="Passwords do not match")

        if len(password) < 6:
            return self.resetPassword(token=token, message="Password must be at least 6 characters")

        # Validate token and get user
        import datetime
        myDB = database.DBConnection()
        user = myDB.match(
            'SELECT UserID, UserName, PasswordResetExpiry FROM users WHERE PasswordResetToken=?',
            (token,)
        )

        if not user:
            return serve_template(templatename="login.html",
                                  message="Invalid or expired reset token")

        expiry = user['PasswordResetExpiry'] if user['PasswordResetExpiry'] else ''
        if expiry:
            try:
                expiry_dt = datetime.datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
                if datetime.datetime.utcnow() > expiry_dt:
                    return serve_template(templatename="login.html",
                                          message="Reset token has expired. Please request a new one.")
            except ValueError:
                pass

        # Hash the new password
        from bookbagofholding.web.auth import hash_password
        new_hash, algorithm = hash_password(password, 'bcrypt')
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # Update password and clear token
        myDB.action(
            'UPDATE users SET Password=?, PasswordAlgorithm=?, PasswordChangedAt=?, '
            'PasswordResetToken=NULL, PasswordResetExpiry=NULL WHERE UserID=?',
            (new_hash, algorithm, now, user['UserID'])
        )

        logger.info("Password reset completed for user: %s" % user['UserName'])
        return serve_template(templatename="login.html",
                              message="Password reset successful! You can now log in.")

    @cherrypy.expose
    def user_contact(self, **kwargs):
        self.label_thread('USERCONTACT')
        remote_ip = cherrypy.request.remote.ip
        msg = 'IP: %s\n' % remote_ip
        for item in kwargs:
            if kwargs[item]:
                line = "%s: %s\n" % (item, unaccented(kwargs[item]))
            else:
                line = "%s: \n" % item
            msg += line
        logger.info("Contact form message: %s" % msg)
        return "Message logged. Email notifications are not configured."

    @cherrypy.expose
    def userAdmin(self):
        self.label_thread('USERADMIN')
        myDB = database.DBConnection()
        title = "Manage User Accounts"
        cmd = 'SELECT UserID, UserName, Name, Email, SendTo, Perms, CalibreRead, CalibreToRead, BookType from users'
        users = myDB.select(cmd)
        return serve_template(templatename="users.html", title=title, users=users)

    @cherrypy.expose
    def admin_delete(self, **kwargs):
        myDB = database.DBConnection()
        user = kwargs['user']
        if user:
            match = myDB.match('SELECT Perms from users where UserName=?', (user,))
            if match:
                perm = check_int(match['Perms'], 0)
                if perm & 1:
                    count = 0
                    perms = myDB.select('SELECT Perms from users')
                    for item in perms:
                        val = check_int(item['Perms'], 0)
                        if val & 1:
                            count += 1
                    if count < 2:
                        return "Unable to delete last administrator"
                myDB.action('DELETE from users WHERE UserName=?', (user,))
                return "User %s deleted" % user
            return "User not found"
        return "No user!"

    @cherrypy.expose
    def admin_userdata(self, **kwargs):
        myDB = database.DBConnection()
        match = myDB.match('SELECT * from users where UserName=?', (kwargs['user'],))
        if match:
            # sqlite3.Row doesn't have .get() so we need to handle KeyError
            try:
                role = match['Role'] if 'Role' in match.keys() else ''
            except (KeyError, TypeError):
                role = ''
            try:
                lastlogin = match['LastLogin'] if 'LastLogin' in match.keys() else ''
            except (KeyError, TypeError):
                lastlogin = ''
            res = simplejson.dumps({
                'email': match['Email'],
                'name': match['Name'],
                'perms': match['Perms'],
                'booktype': match['BookType'],
                'userid': match['UserID'],
                'role': role,
                'lastlogin': lastlogin
            })
        else:
            res = simplejson.dumps({
                'email': '', 'name': '', 'perms': '0',
                'booktype': '', 'userid': '', 'role': '', 'lastlogin': ''
            })
        return res

    @cherrypy.expose
    def adminResetPassword(self, username=''):
        """Generate a password reset token for admin use."""
        self.label_thread("ADMINRESET")

        if not username:
            return "Error: No username provided"

        myDB = database.DBConnection()
        user = myDB.match('SELECT UserID FROM users WHERE UserName=?', (username,))

        if not user:
            return "Error: User not found"

        # Generate reset token
        import secrets
        import datetime
        token = secrets.token_urlsafe(32)
        expires = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        expires_str = expires.strftime("%Y-%m-%d %H:%M:%S")

        myDB.action('UPDATE users SET PasswordResetToken=?, PasswordResetExpiry=? WHERE UserID=?',
                    (token, expires_str, user['UserID']))

        logger.info("Admin generated password reset token for user: %s" % username)
        return "resetPassword?token=%s" % token

    @cherrypy.expose
    def admin_users(self, **kwargs):
        myDB = database.DBConnection()
        user = kwargs['user']
        new_user = not user

        if new_user:
            msg = "New user NOT added: "
            if not kwargs['username']:
                return msg + "No username given"
            else:
                # new user must not have same username as an existing one
                match = myDB.match('SELECT UserName from users where UserName=?', (kwargs['username'],))
                if match:
                    return msg + "Username already exists"

            if not kwargs['fullname']:
                return msg + "No fullname given"

            if not kwargs['email']:
                return msg + "No email given"

            if not isValidEmail(kwargs['email']):
                return msg + "Invalid email given"

            perms = check_int(kwargs.get('perms', ''), 0)
            role = kwargs.get('role', '')

            # If no perms but role provided, derive perms from role
            if not perms and role:
                role_permissions = {
                    'admin': bookbagofholding.perm_admin,
                    'manager': 65532,
                    'friend': bookbagofholding.perm_friend,
                    'guest': bookbagofholding.perm_guest,
                    'readonly': 240
                }
                perms = role_permissions.get(role, 0)

            if not perms:
                return msg + "No permissions or invalid permissions given"
            if not kwargs['password']:
                return msg + "No password given"

            if perms == bookbagofholding.perm_admin:
                perm_msg = 'ADMIN'
            elif perms == bookbagofholding.perm_friend:
                perm_msg = 'Friend'
            elif perms == bookbagofholding.perm_guest:
                perm_msg = 'Guest'
            else:
                perm_msg = 'Custom %s' % perms

            # Determine role from permissions if not already set
            if not role:
                from bookbagofholding.web.auth import get_role_from_permissions
                role = get_role_from_permissions(perms)
            now_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            cmd = 'INSERT into users (UserID, UserName, Name, Password, Email, Perms, Role, CreatedAt, PasswordAlgorithm)'
            cmd += ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
            myDB.action(cmd, (pwd_generator(), kwargs['username'], kwargs['fullname'],
                              md5_utf8(kwargs['password']), kwargs['email'], perms,
                              role, now_time, 'md5'))
            msg = "New user added: %s: %s" % (kwargs['username'], perm_msg)
            cnt = myDB.match("select count(*) as counter from users")
            if cnt['counter'] > 1:
                bookbagofholding.SHOWLOGOUT = 1
            return msg

        else:
            if user != kwargs['username']:
                # if username changed, must not have same username as another user
                match = myDB.match('SELECT UserName from users where UserName=?', (kwargs['username'],))
                if match:
                    return "Username already exists"

            changes = ''
            cmd = 'SELECT UserID,Name,Email,SendTo,Password,Perms,Role,CalibreRead,CalibreToRead,BookType'
            cmd += ' from users where UserName=?'
            details = myDB.match(cmd, (user,))

            if details:
                userid = details['UserID']
                if kwargs['username'] and kwargs['username'] != user:
                    changes += ' username'
                    myDB.action('UPDATE users SET UserName=? WHERE UserID=?', (kwargs['username'], userid))

                if kwargs['fullname'] and details['Name'] != kwargs['fullname']:
                    changes += ' name'
                    myDB.action('UPDATE users SET Name=? WHERE UserID=?', (kwargs['fullname'], userid))

                if details['Email'] != kwargs['email']:
                    if kwargs['email']:
                        if not isValidEmail(kwargs['email']):
                            return "Invalid email given"
                    changes += ' email'
                    myDB.action('UPDATE users SET email=? WHERE UserID=?', (kwargs['email'], userid))

                if kwargs['password']:
                    pwd = md5_utf8(kwargs['password'])
                    if pwd != details['Password']:
                        changes += ' password'
                        myDB.action('UPDATE users SET password=? WHERE UserID=?', (pwd, userid))

                if 'calread' in kwargs and details['CalibreRead'] != kwargs['calread']:
                    changes += ' CalibreRead'
                    myDB.action('UPDATE users SET CalibreRead=? WHERE UserID=?', (kwargs['calread'], userid))

                if 'caltoread' in kwargs and details['CalibreToRead'] != kwargs['caltoread']:
                    changes += ' CalibreToRead'
                    myDB.action('UPDATE users SET CalibreToRead=? WHERE UserID=?', (kwargs['caltoread'], userid))

                if kwargs.get('booktype', '') != details['BookType']:
                    changes += ' BookType'
                    myDB.action('UPDATE users SET BookType=? WHERE UserID=?', (kwargs.get('booktype', ''), userid))

                # Update role if provided
                new_role = kwargs.get('role', '')
                if new_role and details['Role'] != new_role:
                    changes += ' Role'
                    myDB.action('UPDATE users SET Role=? WHERE UserID=?', (new_role, userid))

                # Update permissions
                newperm = check_int(kwargs.get('perms', ''), 0)
                # If no explicit perms but role provided, derive from role
                if not newperm and new_role:
                    role_permissions = {
                        'admin': bookbagofholding.perm_admin,
                        'manager': 65532,
                        'friend': bookbagofholding.perm_friend,
                        'guest': bookbagofholding.perm_guest,
                        'readonly': 240
                    }
                    newperm = role_permissions.get(new_role, 0)

                oldperm = check_int(details['Perms'], 0)
                if oldperm != newperm and newperm > 0:
                    if oldperm & 1 and not newperm & 1:
                        count = 0
                        perms = myDB.select('SELECT Perms from users')
                        for item in perms:
                            val = check_int(item['Perms'], 0)
                            if val & 1:
                                count += 1
                        if count < 2:
                            return "Unable to remove last administrator"
                    changes += ' Perms'
                    myDB.action('UPDATE users SET Perms=? WHERE UserID=?', (newperm, userid))

                if changes:
                    return 'Updated user details:%s' % changes
            return "No changes made"

    @cherrypy.expose
    def password_reset(self, **kwargs):
        self.label_thread('PASSWORD_RESET')
        res = {}
        remote_ip = cherrypy.request.remote.ip
        myDB = database.DBConnection()
        if 'username' in kwargs and kwargs['username']:
            logger.debug("Reset password request from %s, IP:%s" % (kwargs['username'], remote_ip))
            res = myDB.match('SELECT UserID,Email from users where username=?', (kwargs['username'],))  # type: dict
            if res:
                if 'email' in kwargs and kwargs['email']:
                    if res['Email']:
                        if kwargs['email'] == res['Email']:
                            msg = ''
                        else:
                            msg = 'Email does not match our records'
                    else:
                        msg = 'No email address registered'
                else:
                    msg = 'No email address supplied'
            else:
                msg = "Unknown username"
        else:
            msg = "Who are you?"

        if res and not msg:
            msg = "Password reset requires email notifications which are not configured"
        else:
            msg = "Password not reset: %s" % msg
        logger.error("%s IP:%s" % (msg, remote_ip))
        return msg

    @cherrypy.expose
    def generatepwd(self):
        return pwd_generator()

    # CONFIG ############################################################

    @cherrypy.expose
    def saveUsers(self):
        self.label_thread('WEBSERVER')
        savedir = bookbagofholding.DATADIR
        users = dump_table('users', savedir)
        msg = "%d user%s exported" % (users, plural(users))
        return msg

    @cherrypy.expose
    def loadUsers(self):
        self.label_thread('WEBSERVER')
        savedir = bookbagofholding.DATADIR
        users = restore_table('users', savedir)
        msg = "%d user%s imported" % (users, plural(users))
        return msg

    @cherrypy.expose
    def config(self):
        self.label_thread('CONFIG')
        status_list = ['Skipped', 'Wanted', 'Have', 'Ignored']

        # Reset api counters if it's a new day
        if bookbagofholding.NABAPICOUNT != today():
            bookbagofholding.NABAPICOUNT = today()
            for provider in bookbagofholding.NEWZNAB_PROV:
                provider['APICOUNT'] = 0
            for provider in bookbagofholding.TORZNAB_PROV:
                provider['APICOUNT'] = 0

        # Don't pass the whole config, no need to pass the
        # bookbagofholding.globals
        config = {
            "status_list": status_list,
            "namevars": nameVars('test'),
        }
        return serve_template(templatename="config.html", title="Settings", config=config)

    @cherrypy.expose
    def configUpdate(self, **kwargs):
        # print len(kwargs)
        # for arg in kwargs:
        #    print arg

        myDB = database.DBConnection()
        adminmsg = ''

        # Handle simplified Radarr-style auth settings
        # AUTH_PASSWORD is handled specially - only update if a new password is provided
        if 'auth_password' in kwargs and kwargs['auth_password']:
            # Hash the new password
            import hashlib
            password_hash = hashlib.md5(kwargs['auth_password'].encode('utf-8')).hexdigest()
            bookbagofholding.CONFIG['AUTH_PASSWORD'] = password_hash
            # Remove from kwargs so it doesn't get processed again
            del kwargs['auth_password']
        elif 'auth_password' in kwargs:
            # Empty password field - don't change existing password
            del kwargs['auth_password']

        # first the non-config options
        if 'current_tab' in kwargs:
            bookbagofholding.CURRENT_TAB = kwargs['current_tab']

        # now the config file entries
        for key in list(bookbagofholding.CONFIG_DEFINITIONS.keys()):
            item_type, section, default = bookbagofholding.CONFIG_DEFINITIONS[key]
            if key.lower() in kwargs:
                value = kwargs[key.lower()]
                if item_type == 'bool':
                    if not value or value == 'False' or value == '0':
                        value = 0
                    else:
                        value = 1
                elif item_type == 'int':
                    value = check_int(value, default)
                bookbagofholding.CONFIG[key] = value
            else:
                # no key is returned for strings not available in config html page so leave these unchanged
                if key in bookbagofholding.CONFIG_NONWEB or key in bookbagofholding.CONFIG_GIT:
                    pass
                # no key is returned for empty tickboxes...
                elif item_type == 'bool':
                    # print "No entry for bool " + key
                    bookbagofholding.CONFIG[key] = 0
                # or empty string values
                else:
                    # print "No entry for str " + key
                    bookbagofholding.CONFIG[key] = ''

        count = 0
        while count < len(bookbagofholding.NEWZNAB_PROV):
            bookbagofholding.NEWZNAB_PROV[count]['ENABLED'] = bool(kwargs.get(
                'newznab_%i_enabled' % count, False))
            bookbagofholding.NEWZNAB_PROV[count]['HOST'] = kwargs.get(
                'newznab_%i_host' % count, '')
            bookbagofholding.NEWZNAB_PROV[count]['API'] = kwargs.get(
                'newznab_%i_api' % count, '')
            bookbagofholding.NEWZNAB_PROV[count]['GENERALSEARCH'] = kwargs.get(
                'newznab_%i_generalsearch' % count, '')
            bookbagofholding.NEWZNAB_PROV[count]['BOOKSEARCH'] = kwargs.get(
                'newznab_%i_booksearch' % count, '')
            bookbagofholding.NEWZNAB_PROV[count]['AUDIOSEARCH'] = kwargs.get(
                'newznab_%i_audiosearch' % count, '')
            bookbagofholding.NEWZNAB_PROV[count]['BOOKCAT'] = kwargs.get(
                'newznab_%i_bookcat' % count, '')
            bookbagofholding.NEWZNAB_PROV[count]['AUDIOCAT'] = kwargs.get(
                'newznab_%i_audiocat' % count, '')
            bookbagofholding.NEWZNAB_PROV[count]['EXTENDED'] = kwargs.get(
                'newznab_%i_extended' % count, '')
            bookbagofholding.NEWZNAB_PROV[count]['UPDATED'] = kwargs.get(
                'newznab_%i_updated' % count, '')
            bookbagofholding.NEWZNAB_PROV[count]['MANUAL'] = bool(kwargs.get(
                'newznab_%i_manual' % count, False))
            bookbagofholding.NEWZNAB_PROV[count]['APILIMIT'] = check_int(kwargs.get(
                'newznab_%i_apilimit' % count, 0), 0)
            bookbagofholding.NEWZNAB_PROV[count]['DLPRIORITY'] = check_int(kwargs.get(
                'newznab_%i_dlpriority' % count, 0), 0)
            bookbagofholding.NEWZNAB_PROV[count]['DLTYPES'] = kwargs.get(
                'newznab_%i_dltypes' % count, 'E')
            bookbagofholding.NEWZNAB_PROV[count]['DISPNAME'] = kwargs.get(
                'newznab_%i_dispname' % count, '')
            count += 1

        count = 0
        while count < len(bookbagofholding.TORZNAB_PROV):
            bookbagofholding.TORZNAB_PROV[count]['ENABLED'] = bool(kwargs.get(
                'torznab_%i_enabled' % count, False))
            bookbagofholding.TORZNAB_PROV[count]['HOST'] = kwargs.get(
                'torznab_%i_host' % count, '')
            bookbagofholding.TORZNAB_PROV[count]['API'] = kwargs.get(
                'torznab_%i_api' % count, '')
            bookbagofholding.TORZNAB_PROV[count]['GENERALSEARCH'] = kwargs.get(
                'torznab_%i_generalsearch' % count, '')
            bookbagofholding.TORZNAB_PROV[count]['BOOKSEARCH'] = kwargs.get(
                'torznab_%i_booksearch' % count, '')
            bookbagofholding.TORZNAB_PROV[count]['AUDIOSEARCH'] = kwargs.get(
                'torznab_%i_audiosearch' % count, '')
            bookbagofholding.TORZNAB_PROV[count]['BOOKCAT'] = kwargs.get(
                'torznab_%i_bookcat' % count, '')
            bookbagofholding.TORZNAB_PROV[count]['AUDIOCAT'] = kwargs.get(
                'torznab_%i_audiocat' % count, '')
            bookbagofholding.TORZNAB_PROV[count]['EXTENDED'] = kwargs.get(
                'torznab_%i_extended' % count, '')
            bookbagofholding.TORZNAB_PROV[count]['UPDATED'] = kwargs.get(
                'torznab_%i_updated' % count, '')
            bookbagofholding.TORZNAB_PROV[count]['MANUAL'] = bool(kwargs.get(
                'torznab_%i_manual' % count, False))
            bookbagofholding.TORZNAB_PROV[count]['APILIMIT'] = check_int(kwargs.get(
                'torznab_%i_apilimit' % count, 0), 0)
            bookbagofholding.TORZNAB_PROV[count]['DLPRIORITY'] = check_int(kwargs.get(
                'torznab_%i_dlpriority' % count, 0), 0)
            bookbagofholding.TORZNAB_PROV[count]['DLTYPES'] = kwargs.get(
                'torznab_%i_dltypes' % count, 'E')
            bookbagofholding.TORZNAB_PROV[count]['DISPNAME'] = kwargs.get(
                'torznab_%i_dispname' % count, '')
            count += 1

        count = 0
        while count < len(bookbagofholding.RSS_PROV):
            bookbagofholding.RSS_PROV[count]['ENABLED'] = bool(kwargs.get('rss_%i_enabled' % count, False))
            bookbagofholding.RSS_PROV[count]['HOST'] = kwargs.get('rss_%i_host' % count, '')
            bookbagofholding.RSS_PROV[count]['DLPRIORITY'] = check_int(kwargs.get(
                'rss_%i_dlpriority' % count, 0), 0)
            bookbagofholding.RSS_PROV[count]['DLTYPES'] = kwargs.get(
                'rss_%i_dltypes' % count, 'E')
            bookbagofholding.RSS_PROV[count]['DISPNAME'] = kwargs.get(
                'rss_%i_dispname' % count, '')
            count += 1

        bookbagofholding.config_write()
        checkRunningJobs()

        if adminmsg:
            return serve_template(templatename="response.html", prefix="",
                                  title="User Accounts", message=adminmsg, timer=0)

        raise cherrypy.HTTPRedirect("config")

    # SEARCH ############################################################

    @cherrypy.expose
    def search(self, name):
        self.label_thread('SEARCH')
        if not name:
            raise cherrypy.HTTPRedirect("home")

        myDB = database.DBConnection()

        authorids = myDB.select("SELECT AuthorID from authors where status != 'Loading'")
        authorlist = []
        for item in authorids:
            authorlist.append(item['AuthorID'])
        authorids = myDB.select("SELECT AuthorID from authors where status = 'Loading'")
        loadlist = []
        for item in authorids:
            loadlist.append(item['AuthorID'])

        booksearch = myDB.select("SELECT Status,BookID from books")
        booklist = []
        for item in booksearch:
            booklist.append(item['BookID'])

        searchresults = search_for(name)
        return serve_template(templatename="searchresults.html", title='Search Results: "' + name + '"',
                              searchresults=searchresults, authorlist=authorlist, loadlist=loadlist,
                              booklist=booklist, booksearch=booksearch)

    # AUTHOR ############################################################

    @cherrypy.expose
    def markAuthors(self, action=None, redirect=None, **args):
        myDB = database.DBConnection()
        for arg in ['author_table_length', 'ignored']:
            args.pop(arg, None)
        if not redirect:
            redirect = "home"
        if action:
            for authorid in args:
                check = myDB.match("SELECT AuthorName from authors WHERE AuthorID=?", (authorid,))
                if not check:
                    logger.warn('Unable to set Status to "%s" for "%s"' % (action, authorid))
                elif action in ["Active", "Wanted", "Paused", "Ignored"]:
                    myDB.upsert("authors", {'Status': action}, {'AuthorID': authorid})
                    logger.info('Status set to "%s" for "%s"' % (action, check['AuthorName']))
                elif action == "Delete":
                    logger.info("Removing author and books: %s" % check['AuthorName'])
                    books = myDB.select("SELECT BookFile from books WHERE AuthorID=? AND BookFile is not null",
                                        (authorid,))
                    for book in books:
                        if os.path.exists(book['BookFile']):
                            try:
                                rmtree(os.path.dirname(book['BookFile']), ignore_errors=True)
                            except Exception as e:
                                logger.warn('rmtree failed on %s, %s %s' %
                                            (book['BookFile'], type(e).__name__, str(e)))

                    myDB.action('DELETE from authors WHERE AuthorID=?', (authorid,))
                elif action == "Remove":
                    logger.info("Removing author: %s" % check['AuthorName'])
                    myDB.action('DELETE from authors WHERE AuthorID=?', (authorid,))

        raise cherrypy.HTTPRedirect(redirect)

    global lastauthor
    # noinspection PyRedeclaration
    lastauthor = ''

    @cherrypy.expose
    def authorPage(self, AuthorID, BookLang=None, library='eBook', Ignored=False):
        global lastauthor
        myDB = database.DBConnection()
        if Ignored:
            languages = myDB.select(
                "SELECT DISTINCT BookLang from books WHERE AuthorID=? AND Status ='Ignored'", (AuthorID,))
        else:
            languages = myDB.select(
                "SELECT DISTINCT BookLang from books WHERE AuthorID=? AND Status !='Ignored'", (AuthorID,))

        author = myDB.match("SELECT * from authors WHERE AuthorID=?", (AuthorID,))

        types = ['eBook']
        if bookbagofholding.SHOW_AUDIO:
            types.append('AudioBook')

        if not author:
            raise cherrypy.HTTPRedirect("home")

        # if we've changed author, reset to first page of new authors books
        if AuthorID == lastauthor:
            firstpage = 'false'
        else:
            lastauthor = AuthorID
            firstpage = 'true'

        authorname = author['AuthorName']
        if not authorname:  # still loading?
            raise cherrypy.HTTPRedirect("home")

        # Calculate separate stats for eBooks and AudioBooks
        ebook_stats = {'total': 0, 'have': 0, 'skipped': 0, 'ignored': 0}
        audio_stats = {'total': 0, 'have': 0, 'skipped': 0, 'ignored': 0}

        # eBook stats (based on Status field)
        ebook_counts = myDB.select(
            "SELECT Status, COUNT(*) as cnt FROM books WHERE AuthorID=? GROUP BY Status", (AuthorID,))
        for row in ebook_counts:
            status = row['Status']
            count = row['cnt']
            ebook_stats['total'] += count
            if status == 'Open':
                ebook_stats['have'] += count
            elif status == 'Skipped':
                ebook_stats['skipped'] += count
            elif status == 'Ignored':
                ebook_stats['ignored'] += count

        # AudioBook stats (based on AudioStatus field)
        if bookbagofholding.SHOW_AUDIO:
            audio_counts = myDB.select(
                "SELECT AudioStatus, COUNT(*) as cnt FROM books WHERE AuthorID=? AND AudioStatus IS NOT NULL AND AudioStatus != '' GROUP BY AudioStatus",
                (AuthorID,))
            for row in audio_counts:
                status = row['AudioStatus']
                count = row['cnt']
                audio_stats['total'] += count
                if status == 'Open':
                    audio_stats['have'] += count
                elif status == 'Skipped':
                    audio_stats['skipped'] += count
                elif status == 'Ignored':
                    audio_stats['ignored'] += count

        return serve_template(
            templatename="author.html", title=quote_plus(authorname),
            author=author, languages=languages, booklang=BookLang, types=types, library=library, ignored=Ignored,
            firstpage=firstpage, ebook_stats=ebook_stats, audio_stats=audio_stats)

    @cherrypy.expose
    def setAuthor(self, AuthorID, status):

        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName from authors WHERE AuthorID=?', (AuthorID,))
        if authorsearch:
            AuthorName = authorsearch['AuthorName']
            logger.info("%s author: %s" % (status, AuthorName))

            controlValueDict = {'AuthorID': AuthorID}
            newValueDict = {'Status': status}
            myDB.upsert("authors", newValueDict, controlValueDict)
            logger.debug(
                'AuthorID [%s]-[%s] %s - redirecting to Author home page' % (AuthorID, AuthorName, status))
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            logger.debug('pauseAuthor Invalid authorid [%s]' % AuthorID)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def pauseAuthor(self, AuthorID):
        self.setAuthor(AuthorID, 'Paused')

    @cherrypy.expose
    def wantAuthor(self, AuthorID):
        self.setAuthor(AuthorID, 'Wanted')

    @cherrypy.expose
    def resumeAuthor(self, AuthorID):
        self.setAuthor(AuthorID, 'Active')

    @cherrypy.expose
    def ignoreAuthor(self, AuthorID):
        self.setAuthor(AuthorID, 'Ignored')

    @cherrypy.expose
    def removeAuthor(self, AuthorID):
        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName from authors WHERE AuthorID=?', (AuthorID,))
        if authorsearch:  # to stop error if try to remove an author while they are still loading
            AuthorName = authorsearch['AuthorName']
            logger.info("Removing all references to author: %s" % AuthorName)
            myDB.action('DELETE from authors WHERE AuthorID=?', (AuthorID,))
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def refreshAuthor(self, AuthorID, ajax=None, **kwargs):
        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName, Status from authors WHERE AuthorID=?', (AuthorID,))
        if authorsearch:
            # Set status to Loading immediately so the UI shows feedback
            if authorsearch['Status'] != 'Loading':
                myDB.action('UPDATE authors SET Status="Loading" WHERE AuthorID=?', (AuthorID,))

            # Start background thread to refresh author
            threading.Thread(target=addAuthorToDB, name='REFRESHAUTHOR', args=[None, True, AuthorID]).start()

            # If AJAX request, return JSON response
            if ajax or cherrypy.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {
                    'success': True,
                    'message': 'Refreshing author: %s' % authorsearch['AuthorName'],
                    'authorid': AuthorID
                }
            # Otherwise redirect back to author page
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            logger.debug('refreshAuthor Invalid authorid [%s]' % AuthorID)
            if ajax or cherrypy.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return {'success': False, 'error': 'Author not found'}
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def libraryScanAuthor(self, AuthorID, ajax=None, **kwargs):
        myDB = database.DBConnection()
        authorsearch = myDB.match('SELECT AuthorName from authors WHERE AuthorID=?', (AuthorID,))
        is_ajax = ajax or cherrypy.request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        library = kwargs.get('library', 'eBook')

        if authorsearch:  # to stop error if try to refresh an author while they are still loading
            AuthorName = authorsearch['AuthorName']

            if library == 'AudioBook':
                authordir = safe_unicode(os.path.join(bookbagofholding.DIRECTORY('AudioBook'), AuthorName))
            else:  # if library == 'eBook':
                authordir = safe_unicode(os.path.join(bookbagofholding.DIRECTORY('eBook'), AuthorName))
            if not os.path.isdir(authordir):
                # books might not be in exact same authorname folder due to capitalisation
                # eg Calibre puts books into folder "Eric Van Lustbader", but
                # goodreads told bookbagofholding he's "Eric van Lustbader", note the lowercase 'v'
                # or calibre calls "Neil deGrasse Tyson" "Neil DeGrasse Tyson" with a capital 'D'
                # so convert the name and try again...
                AuthorName = ' '.join(word[0].upper() + word[1:] for word in AuthorName.split())
                if library == 'AudioBook':
                    authordir = safe_unicode(os.path.join(bookbagofholding.DIRECTORY('Audio'), AuthorName))
                else:  # if library == 'eBook':
                    authordir = safe_unicode(os.path.join(bookbagofholding.DIRECTORY('eBook'), AuthorName))
            if not os.path.isdir(authordir):
                # if still not found, see if we have a book by them, and what directory it's in
                if library == 'AudioBook':
                    sourcefile = 'AudioFile'
                else:
                    sourcefile = 'BookFile'
                cmd = 'SELECT %s from books,authors where books.AuthorID = authors.AuthorID' % sourcefile
                cmd += '  and AuthorName=? and %s <> ""' % sourcefile
                anybook = myDB.match(cmd, (AuthorName,))
                if anybook:
                    authordir = safe_unicode(os.path.dirname(os.path.dirname(anybook[sourcefile])))
            if os.path.isdir(authordir):
                remove = bool(bookbagofholding.CONFIG['FULL_SCAN'])
                try:
                    threading.Thread(target=LibraryScan, name='AUTHOR_SCAN',
                                     args=[authordir, library, AuthorID, remove]).start()
                    if is_ajax:
                        return {
                            'success': True,
                            'message': 'Started %s scan for %s' % (library, authorsearch['AuthorName']),
                            'library': library,
                            'authorid': AuthorID
                        }
                except Exception as e:
                    logger.error('Unable to complete the scan: %s %s' % (type(e).__name__, str(e)))
                    if is_ajax:
                        return {'success': False, 'error': str(e)}
            else:
                # maybe we don't have any of their books
                logger.warn('Unable to find author directory: %s' % authordir)
                if is_ajax:
                    return {
                        'success': False,
                        'error': 'Unable to find author directory for %s' % authorsearch['AuthorName']
                    }

            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s&library=%s" % (AuthorID, library))
        else:
            logger.debug('ScanAuthor Invalid authorid [%s]' % AuthorID)
            if is_ajax:
                return {'success': False, 'error': 'Author not found'}
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def addAuthor(self, AuthorName):
        threading.Thread(target=addAuthorNameToDB, name='ADDAUTHOR', args=[AuthorName, False]).start()
        raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def addAuthorID(self, AuthorID):
        threading.Thread(target=addAuthorToDB, name='ADDAUTHOR', args=['', False, AuthorID]).start()
        time.sleep(2)  # so we get some data before going to authorpage
        raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        # raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def searchForAuthor(self):
        """Serve the author search page."""
        return serve_template(templatename="searchForAuthor.html", title="Search for Author",
                              current_page='authors')

    @cherrypy.expose
    def toggleAuth(self):
        if bookbagofholding.IGNORED_AUTHORS:  # show ignored ones, or active ones
            bookbagofholding.IGNORED_AUTHORS = False
        else:
            bookbagofholding.IGNORED_AUTHORS = True
        raise cherrypy.HTTPRedirect("home")

    # BOOKS #############################################################

    @cherrypy.expose
    def booksearch(self, author=None, title=None, bookid=None, action=''):
        self.label_thread('BOOKSEARCH')
        if '_title' in action:
            searchterm = title
        elif '_author' in action:
            searchterm = author
        else:  # if '_full' in action: or legacy interface
            searchterm = '%s %s' % (author, title)
            searchterm = searchterm.strip()

        if action == 'e_full':
            cat = 'book'
        elif action == 'a_full':
            cat = 'audio'
        elif action:
            cat = 'general'
        else:  # legacy interface
            cat = 'book'

        results = searchItem(searchterm, bookid, cat)
        library = 'eBook'
        if action.startswith('a_'):
            library = 'AudioBook'
        return serve_template(templatename="manualsearch.html", title=library + ' Search Results: "' +
                              searchterm + '"', bookid=bookid, results=results, library=library)

    @cherrypy.expose
    def countProviders(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        count = bookbagofholding.USE_NZB() + bookbagofholding.USE_TOR() + bookbagofholding.USE_RSS() + bookbagofholding.USE_DIRECT()
        return "Searching %s providers, please wait..." % count

    @cherrypy.expose
    def snatchBook(self, bookid=None, mode=None, provider=None, url=None, size=None, library=None, redirect=None, referrer=None):
        # Decode URL if it was URL-encoded by the browser
        if url:
            url = unquote_plus(url)
        logger.debug("snatch bookid %s mode=%s from %s url=[%s]" % (bookid, mode, provider, url))
        myDB = database.DBConnection()
        bookdata = myDB.match('SELECT AuthorID, BookName from books WHERE BookID=?', (bookid,))
        if bookdata:
            size_temp = check_int(size, 1000)  # Need to cater for when this is NONE (Issue 35)
            size = round(float(size_temp) / 1048576, 2)
            controlValueDict = {"NZBurl": url}
            newValueDict = {
                "NZBprov": provider,
                "BookID": bookid,
                "NZBdate": now(),  # when we asked for it
                "NZBsize": size,
                "NZBtitle": bookdata["BookName"],
                "NZBmode": mode,
                "AuxInfo": library,
                "Status": "Snatched"
            }
            myDB.upsert("wanted", newValueDict, controlValueDict)
            AuthorID = bookdata["AuthorID"]
            # bookname = '%s LL.(%s)' % (bookdata["BookName"], bookid)
            if mode == 'direct':
                snatch, res = DirectDownloadMethod(bookid, bookdata["BookName"], url, library)
            elif mode in ["torznab", "torrent", "magnet"]:
                snatch, res = TORDownloadMethod(bookid, bookdata["BookName"], url, library)
            elif mode == 'nzb':
                snatch, res = NZBDownloadMethod(bookid, bookdata["BookName"], url, library)
            else:
                res = 'Unhandled NZBmode [%s] for %s' % (mode, url)
                logger.error(res)
                snatch = False
            if snatch:
                logger.info('Downloading %s %s from %s' % (library, bookdata["BookName"], provider))
                scheduleJob(action='Start', target='PostProcessor')
            else:
                myDB.action('UPDATE wanted SET status="Failed",DLResult=? WHERE NZBurl=?', (res, url))
                # Add to blacklist if BLACKLIST_FAILED is enabled
                if bookbagofholding.CONFIG['BLACKLIST_FAILED']:
                    add_to_blacklist(url, bookdata["BookName"], provider, bookid, library, 'Failed')
            # Redirect based on where the user came from
            if redirect == 'interactive':
                redirect_url = "interactiveSearch?bookid=%s&library=%s" % (bookid, library)
                if referrer:
                    redirect_url += "&referrer=%s" % referrer
                raise cherrypy.HTTPRedirect(redirect_url)
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s&library=%s" % (AuthorID, library))
        else:
            logger.debug('snatchBook Invalid bookid [%s]' % bookid)
            raise cherrypy.HTTPRedirect("home")

    @cherrypy.expose
    def interactiveSearch(self, bookid=None, library=None, referrer=None):
        """
        Display interactive search page for a book.
        Shows all search results from all providers, allowing user to pick which to download.

        referrer: Optional parameter to indicate where the user came from.
                  'author' - came from author page, back button goes to author
                  'wanted' - came from wanted/manage page, back button goes to manage
                  If not specified, defaults to author page behavior.
        """
        self.label_thread('INTSEARCH')
        if not bookid:
            raise cherrypy.HTTPRedirect("home")

        myDB = database.DBConnection()
        bookdata = myDB.match(
            'SELECT books.*, authors.AuthorName FROM books, authors '
            'WHERE books.AuthorID = authors.AuthorID AND BookID=?', (bookid,))

        if not bookdata:
            logger.debug('interactiveSearch: Invalid bookid [%s]' % bookid)
            raise cherrypy.HTTPRedirect("home")

        # Convert sqlite3.Row to dict for template access
        book = dict(bookdata)

        if not library:
            library = 'eBook'

        # Default to author if referrer not specified
        if not referrer:
            referrer = 'author'

        return serve_template(
            templatename="interactivesearch.html",
            title='Interactive Search: %s - %s' % (book['AuthorName'], book['BookName']),
            book=book,
            library=library,
            referrer=referrer
        )

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getInteractiveSearchResults(self, bookid=None, library=None, showall=None):
        """
        AJAX endpoint to fetch search results from all providers for a book.
        Returns JSON with results list, each containing: score, title, provider, size, date, url, mode, blacklisted
        showall: if '1', search all categories (general) instead of filtering by library type
        """
        import traceback
        self.label_thread('INTSEARCH')
        try:
            if not bookid:
                return {'success': False, 'error': 'Missing bookid parameter'}

            myDB = database.DBConnection()
            bookdata = myDB.match(
                'SELECT books.*, authors.AuthorName FROM books, authors '
                'WHERE books.AuthorID = authors.AuthorID AND BookID=?', (bookid,))

            if not bookdata:
                return {'success': False, 'error': 'Book not found'}

            if not library:
                library = 'eBook'

            # Determine search category - use 'general' if showall is enabled
            if showall == '1':
                cat = 'general'
            else:
                cat = 'audio' if library == 'AudioBook' else 'book'

            # Build search term
            searchterm = '%s %s' % (bookdata['AuthorName'], bookdata['BookName'])
            searchterm = searchterm.strip()

            logger.debug('Interactive search for: %s (bookid=%s, cat=%s, showall=%s)' % (searchterm, bookid, cat, showall))

            # Perform search using existing searchItem function
            # Use min_score=0 to show all results for interactive search (user decides)
            results = searchItem(searchterm, bookid, cat, min_score=0)

            # Auto-fallback: if the cat-filtered search returned nothing, retry without
            # the category filter. Indexers (especially Prowlarr-fronted ones) frequently
            # mis-categorise releases — a book ends up under "audiobook" or just "books
            # general" and the strict cat filter drops it. Falling back to general matches
            # what the manual "Show all results" checkbox does, but does it automatically
            # so users don't have to know about the workaround.
            used_fallback = False
            if not results and cat != 'general' and showall != '1':
                logger.debug('Interactive search returned 0 results with cat=%s; falling back to general' % cat)
                results = searchItem(searchterm, bookid, 'general', min_score=0)
                used_fallback = bool(results)

            logger.debug('Interactive search found %d results%s' %
                         (len(results), ' (via general-search fallback)' if used_fallback else ''))

            # Check blacklist status for each result
            for result in results:
                # URL may be bytes or string, handle both
                url_raw = result.get('url', '')
                if isinstance(url_raw, bytes):
                    url_raw = url_raw.decode('utf-8')
                url = unquote_plus(url_raw)
                result_title = result.get('title', '')
                provider = result.get('provider', '')

                # Check if blacklisted for this book AND library type
                blacklisted = myDB.match(
                    'SELECT * FROM blacklist WHERE (NZBurl=? OR (NZBprov=? AND NZBtitle=?)) '
                    'AND BookID=? AND AuxInfo=? AND Reason="UserBlacklisted"',
                    (url, provider, result_title, bookid, library))
                result['blacklisted'] = bool(blacklisted)

                # Format size for display
                try:
                    size_bytes = int(result.get('size', 0))
                    if size_bytes > 1073741824:  # > 1GB
                        result['size_display'] = '%.2f GB' % (size_bytes / 1073741824)
                    elif size_bytes > 1048576:  # > 1MB
                        result['size_display'] = '%.2f MB' % (size_bytes / 1048576)
                    elif size_bytes > 1024:  # > 1KB
                        result['size_display'] = '%.2f KB' % (size_bytes / 1024)
                    else:
                        result['size_display'] = '%d B' % size_bytes
                except (ValueError, TypeError):
                    result['size_display'] = result.get('size', 'Unknown')

            # Sort by score descending
            results = sorted(results, key=lambda x: x.get('score', 0), reverse=True)

            return {
                'success': True,
                'results': results,
                'count': len(results),
                'bookid': bookid,
                'library': library,
                'searchterm': searchterm,
                'used_fallback': used_fallback,
            }
        except Exception as e:
            logger.error('Interactive search error: %s' % traceback.format_exc())
            return {'success': False, 'error': str(e)}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def blacklistSearchResult(self, url=None, title=None, provider=None, bookid=None, library=None):
        """
        AJAX endpoint to blacklist a search result for a specific book.
        Uses per-book blacklisting - the item will only be hidden for this book's searches.
        """
        self.label_thread('BLACKLIST')
        if not url or not title or not provider or not bookid:
            return {'success': False, 'error': 'Missing required parameters'}

        # Decode URL if needed
        url = unquote_plus(url)

        # Add to blacklist with reason "UserBlacklisted" and BookID for per-book scoping
        add_to_blacklist(url, title, provider, bookid, library, 'UserBlacklisted')

        logger.info('User blacklisted "%s" from %s for book %s' % (title, provider, bookid))

        return {'success': True, 'message': 'Result blacklisted successfully'}

    @cherrypy.expose
    def audio(self, BookLang=None):
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            user = cookie['ll_uid'].value
        else:
            user = 0
        myDB = database.DBConnection()
        if not BookLang or BookLang == 'None':
            BookLang = None
        languages = myDB.select(
            'SELECT DISTINCT BookLang from books WHERE AUDIOSTATUS !="Skipped" AND AUDIOSTATUS !="Ignored"')
        return serve_template(templatename="audio.html", title='AudioBooks', books=[],
                              languages=languages, booklang=BookLang, user=user)

    @cherrypy.expose
    def books(self, BookLang=None):
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            user = cookie['ll_uid'].value
        else:
            user = 0
        myDB = database.DBConnection()
        if not BookLang or BookLang == 'None':
            BookLang = None
        languages = myDB.select('SELECT DISTINCT BookLang from books WHERE STATUS !="Skipped" AND STATUS !="Ignored"')
        return serve_template(templatename="books.html", title='Books', books=[],
                              languages=languages, booklang=BookLang, user=user)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getBooks(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        # for arg in kwargs:
        #     print arg, kwargs[arg]
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            bookbagofholding.CONFIG['DISPLAYLENGTH'] = iDisplayLength

            myDB = database.DBConnection()
            ToRead = []
            HaveRead = []
            flagTo = 0
            flagHave = 0
            if not bookbagofholding.CONFIG['USER_ACCOUNTS']:
                perm = bookbagofholding.perm_admin
            else:
                perm = 0
                cookie = cherrypy.request.cookie
                if cookie and 'll_uid' in list(cookie.keys()):
                    res = myDB.match('SELECT UserName,ToRead,HaveRead,Perms from users where UserID=?',
                                     (cookie['ll_uid'].value,))
                    if res:
                        perm = check_int(res['Perms'], 0)
                        ToRead = getList(res['ToRead'])
                        HaveRead = getList(res['HaveRead'])

                        if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                            logger.debug("getBooks userid %s read %s,%s" % (
                                cookie['ll_uid'].value, len(ToRead), len(HaveRead)))

            cmd = 'SELECT bookimg,authorname,bookname,bookrate,bookdate,books.status,bookid,booklang,'
            cmd += 'booksub,booklink,workpage,books.authorid,booklibrary,audiostatus,audiolibrary,'
            cmd += 'bookgenre,seriesdisplay from books,authors where books.AuthorID = authors.AuthorID'

            library = 'eBook'
            status_type = 'books.status'
            if 'library' in kwargs:
                library = kwargs['library']
            if library == 'AudioBook':
                status_type = 'audiostatus'
            args = []
            if kwargs['source'] == "Manage":
                if kwargs['whichStatus'] == 'ToRead':
                    cmd += ' and books.bookID in (' + ', '.join(ToRead) + ')'
                elif kwargs['whichStatus'] == 'Read':
                    cmd += ' and books.bookID in (' + ', '.join(HaveRead) + ')'
                else:
                    cmd += ' and ' + status_type + '="' + kwargs['whichStatus'] + '"'

            elif kwargs['source'] == "Books":
                cmd += ' and books.STATUS !="Skipped" AND books.STATUS !="Ignored"'
            elif kwargs['source'] == "Audio":
                cmd += ' and AUDIOSTATUS !="Skipped" AND AUDIOSTATUS !="Ignored"'
            elif kwargs['source'] == "Author":
                cmd += ' and books.AuthorID=?'
                args.append(kwargs['AuthorID'])
                if 'ignored' in kwargs and kwargs['ignored'] == "True":
                    cmd += ' and %s="Ignored"' % status_type
                else:
                    cmd += ' and %s != "Ignored"' % status_type

            if kwargs['source'] in ["Books", "Author", "Audio"]:
                # for these we need to check and filter on BookLang if set
                if 'booklang' in kwargs and kwargs['booklang'] != '' and kwargs['booklang'] != 'None':
                    cmd += ' and BOOKLANG=?'
                    args.append(kwargs['booklang'])

            if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                logger.debug("getBooks %s: %s" % (cmd, str(args)))
            rowlist = myDB.select(cmd, tuple(args))

            # At his point we want to sort and filter _before_ adding the html as it's much quicker
            # turn the sqlite rowlist into a list of lists
            if len(rowlist):
                for row in rowlist:  # iterate through the sqlite3.Row objects
                    entry = list(row)
                    if bookbagofholding.CONFIG['SORT_SURNAME']:
                        entry[1] = surnameFirst(entry[1])
                    if bookbagofholding.CONFIG['SORT_DEFINITE']:
                        entry[2] = sortDefinite(entry[2])
                    rows.append(entry)  # add each rowlist to the masterlist

                if sSearch:
                    if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    if library is not None:
                        searchFields = ['AuthorName', 'BookName', 'BookDate', 'Status', 'BookID',
                                        'BookLang', 'BookSub', 'AuthorID', 'BookGenre']
                        if library == 'AudioBook':
                            searchFields[3] = 'AudioStatus'

                        filtered = list()
                        sSearch_lower = sSearch.lower()
                        for row in rowlist:
                            _dict = dict(row)
                            for key in searchFields:
                                if _dict[key] and sSearch_lower in _dict[key].lower():
                                    filtered.append(list(row))
                                    break
                    else:
                        filtered = [x for x in rows if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rows

                # table headers and column headers do not match at this point
                sortcolumn = int(iSortCol_0)
                if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                if sortcolumn < 4:  # author, title
                    sortcolumn -= 1
                elif sortcolumn == 8:  # status
                    if status_type == 'audiostatus':
                        sortcolumn = 13
                    else:
                        sortcolumn = 5
                elif sortcolumn == 7:  # added
                    if status_type == 'audiostatus':
                        sortcolumn = 14
                    else:
                        sortcolumn = 12
                else:  # rating, date
                    sortcolumn -= 2

                if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                    logger.debug("final sortcolumn %d" % sortcolumn)

                if sortcolumn in [12, 14]:  # date
                    self.natural_sort(filtered, key=lambda y: y[sortcolumn] if y[sortcolumn] is not None else '',
                                      reverse=sSortDir_0 == "desc")
                elif sortcolumn in [2]:  # title
                    filtered.sort(key=lambda y: (y[sortcolumn] or '').lower(), reverse=sSortDir_0 == "desc")
                else:
                    filtered.sort(key=lambda y: y[sortcolumn] if y[sortcolumn] is not None else '', reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    rows = filtered
                else:
                    rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

                # now add html to the ones we want to display
                d = []  # the masterlist to be filled with the html data
                for row in rows:
                    worklink = ''
                    sitelink = ''
                    bookrate = int(round(float(row[3])))
                    if bookrate > 5:
                        bookrate = 5

                    if row[10] and len(row[10]) > 4:  # is there a workpage link
                        worklink = '<a href="' + row[10] + '" target="_new"><small><i>LibraryThing</i></small></a>'

                    editpage = '<a href="editBook?bookid=' + row[6] + '" target="_new"><small><i>Manual</i></a>'

                    if 'goodreads' in row[9]:
                        sitelink = '<a href="%s" target="_new"><small><i>GoodReads</i></small></a>' % row[9]
                    elif 'books.google.com' in row[9] or 'market.android.com' in row[9]:
                        sitelink = '<a href="%s" target="_new"><small><i>GoogleBooks</i></small></a>' % row[9]
                    title = row[2]
                    if row[8]:  # is there a sub-title
                        title = '%s<br><small><i>%s</i></small>' % (title, row[8])
                    title = title + '<br>' + sitelink + ' ' + worklink
                    bookgenre = row[-1]

                    if perm & bookbagofholding.perm_edit:
                        title = title + ' ' + editpage

                    if bookgenre:
                        title += ' [' + bookgenre + ']'

                    if row[6] in ToRead:
                        flag = '&nbsp;<i class="far fa-bookmark"></i>'
                        flagTo += 1
                    elif row[6] in HaveRead:
                        flag = '&nbsp;<i class="fas fa-bookmark"></i>'
                        flagHave += 1
                    else:
                        flag = ''

                    # Build row data for 7-column layout: checkbox, cover, author(hidden), title, rating, added, status
                    # Render functions reference: row[9]=bookid, row[10]=date, row[11]=status, row[13]=flag
                    if status_type == 'audiostatus':
                        thisrow = [row[6], row[0], row[1], title, bookrate, row[14], row[13],
                                   '', '', row[6], dateFormat(row[14], bookbagofholding.CONFIG['DATE_FORMAT']),
                                   row[13], '', flag]
                        if kwargs['source'] == "Manage":
                            cmd = "SELECT Time,Interval,Count from failedsearch WHERE Bookid=? AND Library='AudioBook'"
                            searches = myDB.match(cmd, (row[6],))
                            if searches:
                                thisrow.append("%s/%s" % (searches['Count'], searches['Interval']))
                                thisrow.append(time.strftime("%d %b %Y", time.localtime(searches['Time'])))
                            else:
                                thisrow.append('0')
                                thisrow.append('')
                        d.append(thisrow)
                    else:
                        thisrow = [row[6], row[0], row[1], title, bookrate, row[12], row[5],
                                   '', '', row[6], dateFormat(row[12], bookbagofholding.CONFIG['DATE_FORMAT']),
                                   row[5], '', flag]
                        if kwargs['source'] == "Manage":
                            cmd = "SELECT Time,Interval,Count from failedsearch WHERE Bookid=? AND Library='eBook'"
                            searches = myDB.match(cmd, (row[6],))
                            if searches:
                                thisrow.append("%s/%s" % (searches['Count'], searches['Interval']))
                                try:
                                    thisrow.append(time.strftime("%d %b %Y", time.localtime(float(searches['Time']))))
                                except (ValueError, TypeError):
                                    thisrow.append('')
                            else:
                                thisrow.append('0')
                                thisrow.append('')
                        d.append(thisrow)
                rows = d

            if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                logger.debug("getBooks %s returning %s to %s, flagged %s,%s" % (
                    kwargs['source'], iDisplayStart, iDisplayStart + iDisplayLength, flagTo, flagHave))
                logger.debug("getBooks filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getBooks: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @staticmethod
    def natural_sort(lst, key=lambda s: s, reverse=False):
        """
        Sort the list into natural alphanumeric order.
        """

        # noinspection PyShadowingNames
        def get_alphanum_key_func(key):
            convert = lambda text: int(text) if text and text.isdigit() else text
            return lambda s: [convert(c) for c in re.split('([0-9]+)', key(s))]

        sort_key = get_alphanum_key_func(key)
        lst.sort(key=sort_key, reverse=reverse)

    @cherrypy.expose
    def addBook(self, bookid=None):
        myDB = database.DBConnection()
        AuthorID = ""
        match = myDB.match('SELECT AuthorID from books WHERE BookID=?', (bookid,))
        if match:
            myDB.upsert("books", {'Status': 'Wanted'}, {'BookID': bookid})
            AuthorID = match['AuthorID']
            update_totals(AuthorID)
        else:
            GB = GoogleBooks(bookid)
            t = threading.Thread(target=GB.find_book, name='GB-BOOK', args=[bookid, "Wanted"])
            t.start()
            t.join(timeout=10)  # 10 s to add book before redirect
        if bookbagofholding.CONFIG['IMP_AUTOSEARCH']:
            books = [{"bookid": bookid}]
            self.startBookSearch(books)

        if AuthorID:
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def startBookSearch(self, books=None, library=None):
        if books:
            if bookbagofholding.USE_NZB() or bookbagofholding.USE_TOR() \
                    or bookbagofholding.USE_RSS() or bookbagofholding.USE_DIRECT():
                threading.Thread(target=search_book, name='SEARCHBOOK', args=[books, library]).start()
                booktype = library
                if not booktype:
                    booktype = 'book'  # all types
                logger.debug("Searching for %s with id: %s" % (booktype, books[0]["bookid"]))
            else:
                logger.warn("Not searching for book, no search methods set, check config.")
        else:
            logger.debug("BookSearch called with no books")

    @cherrypy.expose
    def searchForBook(self, bookid=None, library=None):
        myDB = database.DBConnection()
        AuthorID = ''
        bookdata = myDB.match('SELECT AuthorID from books WHERE BookID=?', (bookid,))
        if bookdata:
            AuthorID = bookdata["AuthorID"]

            # start searchthreads
            books = [{"bookid": bookid}]
            self.startBookSearch(books, library=library)

        if AuthorID:
            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % AuthorID)
        else:
            raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def searchSelectedBooks(self, library=None, **kwargs):
        """
        Search for multiple selected books at once.
        Book IDs are passed as form parameters (bookid_XXXXX=on format from checkboxes).
        """
        self.label_thread('SEARCH_SELECTED')

        # Extract book IDs from kwargs - they come as bookid=on from checkboxes
        books = []
        for key in kwargs:
            if kwargs[key] == 'on':
                books.append({"bookid": key})

        if books:
            logger.info("Searching for %d selected books (%s)" % (len(books), library or 'all types'))
            self.startBookSearch(books, library=library)

        raise cherrypy.HTTPRedirect("manage?whichStatus=Wanted&library=%s" % (library or 'eBook'))

    @cherrypy.expose
    def requestBook(self, **kwargs):
        self.label_thread('REQUEST_BOOK')
        prefix = ''
        title = 'Request Error'
        cookie = cherrypy.request.cookie
        if cookie and 'll_uid' in list(cookie.keys()):
            myDB = database.DBConnection()
            res = myDB.match('SELECT Name,UserName,UserID,Email from users where UserID=?', (cookie['ll_uid'].value,))
            if res:
                cmd = 'SELECT BookFile,AudioFile,AuthorName,BookName from books,authors WHERE BookID=?'
                cmd += ' and books.AuthorID = authors.AuthorID'
                bookdata = myDB.match(cmd, (kwargs['bookid'],))
                kwargs.update(bookdata)
                kwargs.update(res)
                kwargs.update({'message': 'Request to Download'})

                remote_ip = cherrypy.request.remote.ip
                msg = 'IP: %s\n' % remote_ip
                for item in kwargs:
                    if kwargs[item]:
                        line = "%s: %s\n" % (item, unaccented(kwargs[item]))
                    else:
                        line = "%s: \n" % item
                    msg += line
                if 'library' in kwargs and kwargs['library']:
                    booktype = kwargs['library']
                else:
                    booktype = 'book'

                title = "%s: %s" % (booktype, bookdata['BookName'])

                logger.info("User request: %s" % msg)
                prefix = "Request logged"
                msg = "Email notifications are not configured"
            else:
                msg = "Unknown user"
        else:
            msg = "Nobody logged in?"

        if prefix == "Message sent":
            timer = 5
        else:
            timer = 0
        return serve_template(templatename="response.html", prefix=prefix,
                              title=title, message=msg, timer=timer)

    @cherrypy.expose
    def serveBook(self, feedid=None):
        logger.debug("Serve Book [%s]" % feedid)
        return self.serveItem(feedid, "book")

    @cherrypy.expose
    def serveAudio(self, feedid=None):
        logger.debug("Serve Audio [%s]" % feedid)
        return self.serveItem(feedid, "audio")

    @cherrypy.expose
    def serveIssue(self, feedid=None):
        logger.debug("Serve Issue [%s]" % feedid)
        return self.serveItem(feedid, "issue")

    @cherrypy.expose
    def serveItem(self, feedid, ftype):
        userid = feedid[:10]
        itemid = feedid[10:]
        if len(userid) != 10:
            logger.debug("Invalid userID [%s]" % userid)
            return

        myDB = database.DBConnection()
        res = myDB.match('SELECT UserName,Perms,BookType from users where UserID=?', (userid,))
        if res:
            perm = check_int(res['Perms'], 0)
            preftype = res['BookType']
        else:
            logger.debug("Invalid userID [%s]" % userid)
            return

        if not perm & bookbagofholding.perm_download:
            logger.debug("Insufficient permissions for userID [%s]" % userid)
            return

        if ftype == 'audio':
            res = myDB.match('SELECT AudioFile,BookName from books WHERE BookID=?', (itemid,))
            if res:
                basefile = res['AudioFile']
                # zip up all the audiobook parts
                if basefile and os.path.isfile(basefile):
                    target = zipAudio(os.path.dirname(basefile), res['BookName'])
                    return self.send_file(target, name=res['BookName'] + '.zip')

        basefile = None
        if ftype == 'book':
            res = myDB.match('SELECT BookFile from books WHERE BookID=?', (itemid,))
            if res:
                basefile = res['BookFile']
                basename, extn = os.path.splitext(basefile)
                types = []
                for item in getList(bookbagofholding.CONFIG['EBOOK_TYPE']):
                    target = basename + '.' + item
                    if os.path.isfile(target):
                        types.append(item)

                # serve user preferred type if available, or system preferred type
                if preftype and preftype in types:
                    basefile = basename + '.' + preftype
                else:
                    basefile = basename + '.' + types[0]

        if basefile and os.path.isfile(basefile):
            logger.debug('Opening %s %s' % (ftype, basefile))
            return self.send_file(basefile)

        else:
            logger.warn("No file found for %s %s" % (ftype, itemid))

    @cherrypy.expose
    def openBook(self, bookid=None, library=None, redirect=None, booktype=None):
        self.label_thread('OPEN_BOOK')
        # we need to check the user priveleges and see if they can download the book
        myDB = database.DBConnection()
        if not bookbagofholding.CONFIG['USER_ACCOUNTS']:
            perm = bookbagofholding.perm_admin
            preftype = ''
        else:
            perm = 0
            preftype = ''
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in list(cookie.keys()):
                res = myDB.match('SELECT UserName,Perms,BookType from users where UserID=?',
                                 (cookie['ll_uid'].value,))
                if res:
                    perm = check_int(res['Perms'], 0)
                    preftype = res['BookType']

        if booktype is not None:
            preftype = booktype

        cmd = 'SELECT BookFile,AudioFile,AuthorName,BookName from books,authors WHERE BookID=?'
        cmd += ' and books.AuthorID = authors.AuthorID'
        bookdata = myDB.match(cmd, (bookid,))
        if not bookdata:
            logger.warn('Missing bookid: %s' % bookid)
        else:
            if perm & bookbagofholding.perm_download:
                authorName = bookdata["AuthorName"]
                bookName = bookdata["BookName"]
                if library == 'AudioBook':
                    bookfile = bookdata["AudioFile"]
                    if bookfile and os.path.isfile(bookfile):
                        parentdir = os.path.dirname(bookfile)
                        index = os.path.join(parentdir, 'playlist.ll')
                        if os.path.isfile(index):
                            if booktype == 'zip':
                                zipfile = zipAudio(parentdir, bookName)
                                logger.debug('Opening %s %s' % (library, zipfile))
                                return self.send_file(zipfile, name="Audiobook zip of %s" % bookName)
                            idx = check_int(booktype, 0)
                            if idx:
                                with open(index, 'r') as f:
                                    part = f.read().splitlines()[idx - 1]
                                bookfile = os.path.join(parentdir, part)
                                logger.debug('Opening %s %s' % (library, bookfile))
                                return self.send_file(bookfile, name="Audiobook part %s of %s" % (idx, bookName))
                            # noinspection PyUnusedLocal
                            cnt = sum(1 for line in open(index))
                            if cnt <= 1:
                                logger.debug('Opening %s %s' % (library, bookfile))
                                return self.send_file(bookfile, name="Audiobook %s" % bookName)
                            else:
                                msg = "Please select which part to download"
                                item = 1
                                partlist = ''
                                while item <= cnt:
                                    if partlist:
                                        partlist += ' '
                                    partlist += str(item)
                                    item += 1
                                    partlist += ' zip'
                                safetitle = bookName.replace('&', '&amp;').replace("'", "")

                            return serve_template(templatename="choosetype.html", prefix="AudioBook",
                                                  title=safetitle, pop_message=msg,
                                                  pop_types=partlist, bookid=bookid,
                                                  valid=getList(partlist.replace(' ', ',')))
                        else:
                            logger.debug('Opening %s %s' % (library, bookfile))
                            return self.send_file(bookfile, name="Audiobook %s" % bookName)
                else:
                    library = 'eBook'
                    bookfile = bookdata["BookFile"]
                    if bookfile and os.path.isfile(bookfile):
                        basename, extn = os.path.splitext(bookfile)
                        types = []
                        for item in getList(bookbagofholding.CONFIG['EBOOK_TYPE']):
                            target = basename + '.' + item
                            if os.path.isfile(target):
                                types.append(item)

                        if preftype:
                            if preftype in types:
                                bookfile = basename + '.' + preftype
                            else:
                                msg = "%s<br> Not available as %s, only " % (bookName, preftype)
                                typestr = ''
                                for item in types:
                                    if typestr:
                                        typestr += ' '
                                    typestr += item
                                msg += typestr
                                return serve_template(templatename="choosetype.html", prefix="",
                                                      title="Not Available", pop_message=msg,
                                                      pop_types=typestr, bookid=bookid,
                                                      valid=getList(bookbagofholding.CONFIG['EBOOK_TYPE']))
                        elif len(types) > 1:
                            msg = "Please select format to download"
                            typestr = ''
                            for item in types:
                                if typestr:
                                    typestr += ' '
                                typestr += item
                            return serve_template(templatename="choosetype.html", prefix="",
                                                  title="Choose Type", pop_message=msg,
                                                  pop_types=typestr, bookid=bookid,
                                                  valid=getList(bookbagofholding.CONFIG['EBOOK_TYPE']))

                        logger.debug('Opening %s %s' % (library, bookfile))
                        return self.send_file(bookfile, name="eBook %s" % bookName)

                logger.info('Missing %s %s, %s [%s]' % (library, authorName, bookName, bookfile))
            else:
                return self.requestBook(library=library, bookid=bookid, redirect=redirect)

    @cherrypy.expose
    def editAuthor(self, authorid=None):
        self.label_thread('EDIT_AUTHOR')
        myDB = database.DBConnection()

        data = myDB.match('SELECT * from authors WHERE AuthorID=?', (authorid,))
        if data:
            return serve_template(templatename="editauthor.html", title="Edit Author", config=data)
        else:
            logger.info('Missing author %s:' % authorid)

    # noinspection PyUnusedLocal
    # kwargs needed for passing utf8 hidden input
    @cherrypy.expose
    def authorUpdate(self, authorid='', authorname='', authorborn='', authordeath='', authorimg='',
                     manual='0', **kwargs):
        myDB = database.DBConnection()
        if authorid:
            authdata = myDB.match('SELECT * from authors WHERE AuthorID=?', (authorid,))
            if authdata:
                edited = ""
                if not authorborn or authorborn == 'None':
                    authorborn = None
                if not authordeath or authordeath == 'None':
                    authordeath = None
                if authorimg == 'None':
                    authorimg = ''
                manual = bool(check_int(manual, 0))

                if not (authdata["AuthorBorn"] == authorborn):
                    edited += "Born "
                if not (authdata["AuthorDeath"] == authordeath):
                    edited += "Died "
                if authorimg and (authdata["AuthorImg"] != authorimg):
                    edited += "Image "
                if not (bool(check_int(authdata["Manual"], 0)) == manual):
                    edited += "Manual "

                if not (authdata["AuthorName"] == authorname):
                    match = myDB.match('SELECT AuthorName from authors where AuthorName=?', (authorname,))
                    if match:
                        logger.debug("Unable to rename, new author name %s already exists" % authorname)
                        authorname = authdata["AuthorName"]
                    else:
                        edited += "Name "

                if edited:
                    # Check dates in format yyyy/mm/dd, or None to clear date
                    # Leave unchanged if fails datecheck
                    if authorborn is not None:
                        ab = authorborn
                        authorborn = authdata["AuthorBorn"]  # assume fail, leave unchanged
                        if ab:
                            rejected = True
                            if len(ab) == 10:
                                try:
                                    _ = datetime.date(int(ab[:4]), int(ab[5:7]), int(ab[8:]))
                                    authorborn = ab
                                    rejected = False
                                except ValueError:
                                    authorborn = authdata["AuthorBorn"]
                            if rejected:
                                logger.warn("Author Born date [%s] rejected" % ab)
                                edited = edited.replace('Born ', '')

                    if authordeath is not None:
                        ab = authordeath
                        authordeath = authdata["AuthorDeath"]  # assume fail, leave unchanged
                        if ab:
                            rejected = True
                            if len(ab) == 10:
                                try:
                                    _ = datetime.date(int(ab[:4]), int(ab[5:7]), int(ab[8:]))
                                    authordeath = ab
                                    rejected = False
                                except ValueError:
                                    authordeath = authdata["AuthorDeath"]
                            if rejected:
                                logger.warn("Author Died date [%s] rejected" % ab)
                                edited = edited.replace('Died ', '')

                    if not authorimg:
                        authorimg = authdata["AuthorImg"]
                    else:
                        if authorimg == 'none':
                            authorimg = os.path.join(bookbagofholding.PROG_DIR, 'data', 'images', 'nophoto.png')

                        rejected = True
                        # Cache file image
                        if os.path.isfile(authorimg):
                            extn = os.path.splitext(authorimg)[1].lower()
                            if extn and extn in ['.jpg', '.jpeg', '.png']:
                                destfile = os.path.join(bookbagofholding.CACHEDIR, 'author', authorid + '.jpg')
                                try:
                                    copyfile(authorimg, destfile)
                                    setperm(destfile)
                                    authorimg = 'cache/author/' + authorid + '.jpg'
                                    rejected = False
                                except Exception as why:
                                    logger.warn("Failed to copy file %s, %s %s" %
                                                (authorimg, type(why).__name__, str(why)))

                        if authorimg.startswith('http'):
                            # cache image from url
                            extn = os.path.splitext(authorimg)[1].lower()
                            if extn and extn in ['.jpg', '.jpeg', '.png']:
                                authorimg, success, _ = cache_img("author", authorid, authorimg)
                                if success:
                                    rejected = False

                        if rejected:
                            logger.warn("Author Image [%s] rejected" % authorimg)
                            authorimg = authdata["AuthorImg"]
                            edited = edited.replace('Image ', '')

                    controlValueDict = {'AuthorID': authorid}
                    newValueDict = {
                        'AuthorName': authorname,
                        'AuthorBorn': authorborn,
                        'AuthorDeath': authordeath,
                        'AuthorImg': authorimg,
                        'Manual': bool(manual)
                    }
                    myDB.upsert("authors", newValueDict, controlValueDict)
                    logger.info('Updated [ %s] for %s' % (edited, authorname))

                else:
                    logger.debug('Author [%s] has not been changed' % authorname)

            raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s" % authorid)
        else:
            raise cherrypy.HTTPRedirect("authors")

    @cherrypy.expose
    def editBook(self, bookid=None):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        self.label_thread('EDIT_BOOK')
        myDB = database.DBConnection()
        authors = myDB.select(
            "SELECT AuthorName from authors WHERE Status !='Ignored' ORDER by AuthorName COLLATE NOCASE")
        cmd = 'SELECT BookName,BookID,BookSub,BookGenre,BookLang,BookDesc,books.Manual,AuthorName,'
        cmd += 'books.AuthorID,BookDate from books,authors WHERE books.AuthorID = authors.AuthorID and BookID=?'
        bookdata = myDB.match(cmd, (bookid,))
        if bookdata:
            covers = []
            for source in ['current', 'cover', 'librarything', 'whatwork',
                           'openlibrary', 'googleisbn', 'googleimage']:
                cover, _ = getBookCover(bookid, source)
                if cover:
                    covers.append([source, cover])

            return serve_template(templatename="editbook.html", title="Edit Book",
                                  config=bookdata, seriesdict=[], authors=authors, covers=covers)
        else:
            logger.info('Missing book %s' % bookid)

    @cherrypy.expose
    def bookUpdate(self, bookname='', bookid='', booksub='', bookgenre='', booklang='', bookdate='',
                   manual='0', authorname='', cover='', newid='', editordata='', **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        myDB = database.DBConnection()

        if bookid:
            cmd = 'SELECT BookName,BookSub,BookGenre,BookLang,BookImg,BookDate,BookDesc,books.Manual,AuthorName,'
            cmd += 'books.AuthorID from books,authors WHERE books.AuthorID = authors.AuthorID and BookID=?'
            bookdata = myDB.match(cmd, (bookid,))
            if bookdata:
                edited = ''
                moved = False
                if bookgenre == 'None':
                    bookgenre = ''
                manual = bool(check_int(manual, 0))

                if newid and not (bookid == newid):
                    cmd = "SELECT BookName,Authorname from books,authors "
                    cmd += "WHERE books.AuthorID = authors.AuthorID and BookID=?"
                    match = myDB.match(cmd, (newid,))
                    if match:
                        logger.warn("Cannot change bookid to %s, in use by %s/%s" %
                                    (newid, match['BookName'], match['AuthorName']))
                    else:
                        logger.warn("Updating bookid is not supported yet")
                        # edited += "BookID "
                if not (bookdata["BookName"] == bookname):
                    edited += "Title "
                if not (bookdata["BookSub"] == booksub):
                    edited += "Subtitle "
                if not (bookdata["BookDesc"] == editordata):
                    edited += "Description "
                if not (bookdata["BookGenre"] == bookgenre):
                    edited += "Genre "
                if not (bookdata["BookLang"] == booklang):
                    edited += "Language "
                if not (bookdata["BookDate"] == bookdate):
                    if bookdate == '0000':
                        edited += "Date "
                    else:
                        # googlebooks sometimes gives yyyy, sometimes yyyy-mm, sometimes yyyy-mm-dd
                        if len(bookdate) == 4:
                            y = check_year(bookdate)
                        elif len(bookdate) in [7, 10]:
                            y = check_year(bookdate[:4])
                            if y and len(bookdate) == 7:
                                try:
                                    _ = datetime.date(int(bookdate[:4]), int(bookdate[5:7]), 1)
                                except ValueError:
                                    y = 0
                            elif y and len(bookdate) == 10:
                                try:
                                    _ = datetime.date(int(bookdate[:4]), int(bookdate[5:7]), int(bookdate[8:]))
                                except ValueError:
                                    y = 0
                        else:
                            y = 0
                        if y:
                            edited += "Date "
                        else:
                            bookdate = bookdata["BookDate"]
                if not (bool(check_int(bookdata["Manual"], 0)) == manual):
                    edited += "Manual "
                if not (bookdata["AuthorName"] == authorname):
                    moved = True

                covertype = ''
                if cover == 'librarything':
                    covertype = '_lt'
                elif cover == 'whatwork':
                    covertype = '_ww'
                elif cover == 'openlibrary':
                    covertype = '_ol'
                elif cover == 'googleisbn':
                    covertype = '_gi'
                elif cover == 'googleimage':
                    covertype = '_gb'

                if covertype:
                    cachedir = bookbagofholding.CACHEDIR
                    coverlink = 'cache/book/' + bookid + '.jpg'
                    coverfile = os.path.join(cachedir, "book", bookid + '.jpg')
                    newcoverfile = os.path.join(cachedir, "book", bookid + covertype + '.jpg')
                    if os.path.exists(newcoverfile):
                        copyfile(newcoverfile, coverfile)
                    edited += 'Cover '
                else:
                    coverlink = bookdata['BookImg']

                if edited:
                    controlValueDict = {'BookID': bookid}
                    newValueDict = {
                        'BookName': bookname,
                        'BookSub': booksub,
                        'BookGenre': bookgenre,
                        'BookLang': booklang,
                        'BookDate': bookdate,
                        'BookDesc': editordata,
                        'BookImg': coverlink,
                        'Manual': bool(manual)
                    }
                    myDB.upsert("books", newValueDict, controlValueDict)

                if edited:
                    logger.info('Updated [ %s] for %s' % (edited, bookname))
                else:
                    logger.debug('Book [%s] has not been changed' % bookname)

                if moved:
                    authordata = myDB.match('SELECT AuthorID from authors WHERE AuthorName=?', (authorname,))
                    if authordata:
                        controlValueDict = {'BookID': bookid}
                        newValueDict = {'AuthorID': authordata['AuthorID']}
                        myDB.upsert("books", newValueDict, controlValueDict)
                        update_totals(bookdata["AuthorID"])  # we moved from here
                        update_totals(authordata['AuthorID'])  # to here

                    logger.info('Book [%s] has been moved' % bookname)
                else:
                    logger.debug('Book [%s] has not been moved' % bookname)
                # if edited or moved:

                raise cherrypy.HTTPRedirect("editBook?bookid=%s" % bookid)

        raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def markBooks(self, AuthorID=None, action=None, redirect=None, **args):
        if 'library' in args:
            library = args['library']
        else:
            library = 'eBook'
            if redirect == 'audio':
                library = 'AudioBook'

        if 'marktype' in args:
            library = args['marktype']

        for arg in ['book_table_length', 'ignored', 'library', 'booklang']:
            args.pop(arg, None)

        myDB = database.DBConnection()
        if not redirect:
            redirect = "books"
        check_totals = []
        if redirect == 'author':
            check_totals = [AuthorID]
        if action:
            for bookid in args:
                if action in ["Unread", "Read", "ToRead"]:
                    cookie = cherrypy.request.cookie
                    if cookie and 'll_uid' in list(cookie.keys()):
                        res = myDB.match('SELECT ToRead,HaveRead from users where UserID=?',
                                         (cookie['ll_uid'].value,))
                        if res:
                            ToRead = getList(res['ToRead'])
                            HaveRead = getList(res['HaveRead'])
                            if action == "Unread":
                                if bookid in ToRead:
                                    ToRead.remove(bookid)
                                if bookid in HaveRead:
                                    HaveRead.remove(bookid)
                                logger.debug('Status set to "unread" for "%s"' % bookid)
                            elif action == "Read":
                                if bookid in ToRead:
                                    ToRead.remove(bookid)
                                if bookid not in HaveRead:
                                    HaveRead.append(bookid)
                                logger.debug('Status set to "read" for "%s"' % bookid)
                            elif action == "ToRead":
                                if bookid not in ToRead:
                                    ToRead.append(bookid)
                                if bookid in HaveRead:
                                    HaveRead.remove(bookid)
                                logger.debug('Status set to "to read" for "%s"' % bookid)

                            ToRead = list(set(ToRead))
                            HaveRead = list(set(HaveRead))
                            myDB.action('UPDATE users SET ToRead=?,HaveRead=? WHERE UserID=?',
                                        (', '.join(ToRead), ', '.join(HaveRead), cookie['ll_uid'].value))

                elif action in ["Wanted", "Have", "Ignored", "Skipped"]:
                    bookdata = myDB.match('SELECT AuthorID,BookName from books WHERE BookID=?', (bookid,))
                    if bookdata:
                        authorid = bookdata['AuthorID']
                        bookname = bookdata['BookName']
                        if authorid not in check_totals:
                            check_totals.append(authorid)
                        if 'eBook' in library:
                            myDB.upsert("books", {'Status': action}, {'BookID': bookid})
                            logger.debug('Status set to "%s" for "%s"' % (action, bookname))
                        if 'Audio' in library:
                            myDB.upsert("books", {'AudioStatus': action}, {'BookID': bookid})
                            logger.debug('AudioStatus set to "%s" for "%s"' % (action, bookname))
                elif action in ["NoDelay"]:
                    myDB.action("delete from failedsearch WHERE BookID=? AND Library=?", (bookid, library))
                    logger.debug('%s delay set to zero for %s' % (library, bookid))
                elif action in ["Remove", "Delete"]:
                    bookdata = myDB.match(
                        'SELECT AuthorID,Bookname,BookFile,AudioFile from books WHERE BookID=?', (bookid,))
                    if bookdata:
                        authorid = bookdata['AuthorID']
                        bookname = bookdata['BookName']
                        if authorid not in check_totals:
                            check_totals.append(authorid)
                        if action == "Delete":
                            if 'Audio' in library:
                                bookfile = bookdata['AudioFile']
                                if bookfile and os.path.isfile(bookfile):
                                    try:
                                        rmtree(os.path.dirname(bookfile), ignore_errors=True)
                                        logger.info('AudioBook %s deleted from disc' % bookname)
                                    except Exception as e:
                                        logger.warn('rmtree failed on %s, %s %s' %
                                                    (bookfile, type(e).__name__, str(e)))

                            if 'eBook' in library:
                                bookfile = bookdata['BookFile']
                                if bookfile and os.path.isfile(bookfile):
                                    try:
                                        rmtree(os.path.dirname(bookfile), ignore_errors=True)
                                        deleted = True
                                    except Exception as e:
                                        logger.warn('rmtree failed on %s, %s %s' %
                                                    (bookfile, type(e).__name__, str(e)))
                                        deleted = False

                                    if deleted:
                                        logger.info('eBook %s deleted from disc' % bookname)
                                        try:
                                            calibreid = os.path.dirname(bookfile)
                                            if calibreid.endswith(')'):
                                                # noinspection PyTypeChecker
                                                calibreid = calibreid.rsplit('(', 1)[1].split(')')[0]
                                                if not calibreid or not calibreid.isdigit():
                                                    calibreid = None
                                            else:
                                                calibreid = None
                                        except IndexError:
                                            calibreid = None

                                        if calibreid:
                                            res, err, rc = calibredb('remove', [calibreid], None)
                                            if res and not rc:
                                                logger.debug('%s reports: %s' %
                                                             (bookbagofholding.CONFIG['IMP_CALIBREDB'],
                                                              unaccented_str(res)))
                                            else:
                                                logger.debug('No response from %s' %
                                                             bookbagofholding.CONFIG['IMP_CALIBREDB'])

                        authorcheck = myDB.match('SELECT Status from authors WHERE AuthorID=?', (authorid,))
                        if authorcheck:
                            if authorcheck['Status'] not in ['Active', 'Wanted']:
                                myDB.action('delete from books where bookid=?', (bookid,))
                                myDB.action('delete from wanted where bookid=?', (bookid,))
                                logger.info('Removed "%s" from database' % bookname)
                            elif 'eBook' in library:
                                myDB.upsert("books", {"Status": "Ignored"}, {"BookID": bookid})
                                logger.debug('Status set to Ignored for "%s"' % bookname)
                            elif 'Audio' in library:
                                myDB.upsert("books", {"AudioStatus": "Ignored"}, {"BookID": bookid})
                                logger.debug('AudioStatus set to Ignored for "%s"' % bookname)
                        else:
                            myDB.action('delete from books where bookid=?', (bookid,))
                            myDB.action('delete from wanted where bookid=?', (bookid,))
                            logger.info('Removed "%s" from database' % bookname)

        if check_totals:
            for author in check_totals:
                update_totals(author)

        # start searchthreads (only if IMP_AUTOSEARCH is enabled)
        if action == 'Wanted' and bookbagofholding.CONFIG['IMP_AUTOSEARCH']:
            books = []
            for arg in ['booklang', 'library', 'ignored', 'book_table_length']:
                args.pop(arg, None)
            for arg in args:
                books.append({"bookid": arg})

            if bookbagofholding.USE_NZB() or bookbagofholding.USE_TOR() \
                    or bookbagofholding.USE_RSS() or bookbagofholding.USE_DIRECT():
                if 'eBook' in library:
                    threading.Thread(target=search_book, name='SEARCHBOOK', args=[books, 'eBook']).start()
                if 'Audio' in library:
                    threading.Thread(target=search_book, name='SEARCHBOOK', args=[books, 'AudioBook']).start()

        if redirect == "author":
                if 'eBook' in library:
                    raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s&library=%s" % (AuthorID, 'eBook'))
                if 'Audio' in library:
                    raise cherrypy.HTTPRedirect("authorPage?AuthorID=%s&library=%s" % (AuthorID, 'AudioBook'))
        elif redirect in ["books", "audio"]:
            raise cherrypy.HTTPRedirect(redirect)
        elif 'Audio' in library:
            raise cherrypy.HTTPRedirect("manage?library=%s" % 'AudioBook')
        raise cherrypy.HTTPRedirect("manage?library=%s" % 'eBook')

    # WALL #########################################################

    @cherrypy.expose
    def bookWall(self, have='0'):
        self.label_thread('BOOKWALL')
        myDB = database.DBConnection()
        if have == '1':
            cmd = 'SELECT BookLink,BookImg,BookID,BookName from books where Status="Open" order by BookLibrary DESC'
            title = 'Recently Downloaded Books'
        else:
            cmd = 'SELECT BookLink,BookImg,BookID,BookName from books where Status != "Ignored" order by BookAdded DESC'
            title = 'Recently Added Books'
        results = myDB.select(cmd)
        if not len(results):
            raise cherrypy.HTTPRedirect("books")
        maxcount = check_int(bookbagofholding.CONFIG['MAX_WALL'], 0)
        if maxcount and len(results) > maxcount:
            results = results[:maxcount]
            title = "%s (Top %i)" % (title, len(results))
        return serve_template(
            templatename="coverwall.html", title=title, results=results, redirect="books", have=have,
            columns=bookbagofholding.CONFIG['WALL_COLUMNS'])

    @cherrypy.expose
    def audioWall(self):
        self.label_thread('AUDIOWALL')
        myDB = database.DBConnection()
        results = myDB.select(
            'SELECT AudioFile,BookImg,BookID,BookName from books where AudioStatus="Open" order by AudioLibrary DESC')
        if not len(results):
            raise cherrypy.HTTPRedirect("audio")
        title = "Recent AudioBooks"
        maxcount = check_int(bookbagofholding.CONFIG['MAX_WALL'], 0)
        if maxcount and len(results) > maxcount:
            results = results[:maxcount]
            title = "%s (Top %i)" % (title, len(results))
        return serve_template(
            templatename="coverwall.html", title=title, results=results, redirect="audio",
            columns=bookbagofholding.CONFIG['WALL_COLUMNS'])

    @cherrypy.expose
    def wallColumns(self, redirect=None, count=None, have=0):
        columns = check_int(bookbagofholding.CONFIG['WALL_COLUMNS'], 6)
        if count == 'up' and columns <= 12:
            columns += 1
        elif count == 'down' and columns > 1:
            columns -= 1
        bookbagofholding.CONFIG['WALL_COLUMNS'] = columns
        if redirect == 'audio':
            raise cherrypy.HTTPRedirect('audioWall')
        elif redirect == 'books':
            raise cherrypy.HTTPRedirect('bookWall?have=%s' % have)
        else:
            raise cherrypy.HTTPRedirect('home')

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def forceUpdate(self, ajax=None, **kwargs):
        """Force update of author metadata (not application update)."""
        already_running = 'AAUPDATE' in [n.name for n in [t for t in threading.enumerate()]]

        if not already_running:
            threading.Thread(target=aaUpdate, name='AAUPDATE', args=[False]).start()
            message = 'Author refresh started'
        else:
            logger.debug('AAUPDATE already running')
            message = 'Author refresh already in progress'

        # If AJAX request, return JSON response
        if ajax or cherrypy.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return {
                'success': True,
                'message': message,
                'already_running': already_running
            }
        # Otherwise redirect back to authors page
        raise cherrypy.HTTPRedirect("authors")

    # IMPORT/EXPORT #####################################################

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def libraryScan(self, ajax=None, **kwargs):
        library = 'eBook'
        if 'library' in kwargs:
            library = kwargs['library']
        remove = bool(bookbagofholding.CONFIG['FULL_SCAN'])
        threadname = "%s_SCAN" % library.upper()
        is_ajax = ajax or cherrypy.request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if threadname not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=LibraryScan, name=threadname, args=[None, library, None, remove]).start()
                if is_ajax:
                    return {
                        'success': True,
                        'message': 'Started %s library scan' % library,
                        'library': library
                    }
            except Exception as e:
                logger.error('Unable to complete the scan: %s %s' % (type(e).__name__, str(e)))
                if is_ajax:
                    return {'success': False, 'error': str(e)}
        else:
            logger.debug('%s already running' % threadname)
            if is_ajax:
                return {
                    'success': True,
                    'message': '%s scan already running' % library,
                    'library': library,
                    'already_running': True
                }

        if library == 'AudioBook':
            raise cherrypy.HTTPRedirect("audio")
        raise cherrypy.HTTPRedirect("books")

    @cherrypy.expose
    def includeAlternate(self, library='eBook'):
        if 'ALT-LIBRARYSCAN' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=LibraryScan, name='ALT-LIBRARYSCAN',
                                 args=[bookbagofholding.CONFIG['ALTERNATE_DIR'], library, None, False]).start()
            except Exception as e:
                logger.error('Unable to complete the libraryscan: %s %s' % (type(e).__name__, str(e)))
        else:
            logger.debug('ALT-LIBRARYSCAN already running')
        raise cherrypy.HTTPRedirect("manage?library=%s" % library)

    @cherrypy.expose
    def importAlternate(self, library='eBook'):
        if 'IMPORTALT' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                threading.Thread(target=processAlternate, name='IMPORTALT',
                                 args=[bookbagofholding.CONFIG['ALTERNATE_DIR'], library]).start()
            except Exception as e:
                logger.error('Unable to complete the import: %s %s' % (type(e).__name__, str(e)))
        else:
            logger.debug('IMPORTALT already running')
        raise cherrypy.HTTPRedirect("manage?library=%s" % library)

    @cherrypy.expose
    def rssFeed(self, **kwargs):
        self.label_thread('RSSFEED')
        if 'type' in kwargs:
            ftype = kwargs['type']
        else:
            return

        if 'limit' in kwargs:
            limit = kwargs['limit']
        else:
            limit = '10'

        # url might end in .xml
        if not limit.isdigit():
            try:
                limit = int(limit.split('.')[0])
            except (IndexError, ValueError):
                limit = 10

        userid = 0
        if 'user' in kwargs:
            userid = kwargs['user']
        else:
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in list(cookie.keys()):
                userid = cookie['ll_uid'].value

        scheme, netloc, path, qs, anchor = urlsplit(cherrypy.url())
        netloc = cherrypy.request.headers.get('X-Forwarded-Host')
        if not netloc:
            netloc = cherrypy.request.headers.get('Host')

        remote_ip = cherrypy.request.headers.get('X-Forwarded-For')  # apache2
        if not remote_ip:
            remote_ip = cherrypy.request.headers.get('X-Host')  # lighthttpd
        if not remote_ip:
            remote_ip = cherrypy.request.headers.get('Remote-Addr')
        if not remote_ip:
            remote_ip = cherrypy.request.remote.ip

        filename = 'BookbagOfHolding_RSS_' + ftype + '.xml'
        path = path.replace('rssFeed', '').rstrip('/')
        baseurl = urlunsplit((scheme, netloc, path, qs, anchor))
        logger.debug("RSS Feed request %s %s%s: %s %s" % (limit, ftype, plural(limit), remote_ip, userid))
        cherrypy.response.headers["Content-Type"] = 'application/rss+xml'
        cherrypy.response.headers["Content-Disposition"] = 'attachment; filename="%s"' % filename
        res = genFeed(ftype, limit=limit, user=userid, baseurl=baseurl)
        return makeBytestr(res)

    @cherrypy.expose
    def importCSV(self, library='eBook'):
        if 'IMPORTCSV' not in [n.name for n in [t for t in threading.enumerate()]]:
            try:
                csvFile = csv_file(bookbagofholding.CONFIG['ALTERNATE_DIR'], library=library)
                if os.path.exists(csvFile):
                    message = "Importing books (background task) from %s" % csvFile
                    threading.Thread(target=import_CSV, name='IMPORTCSV',
                                     args=[bookbagofholding.CONFIG['ALTERNATE_DIR'], library]).start()
                else:
                    message = "No %s CSV file in [%s]" % (library, bookbagofholding.CONFIG['ALTERNATE_DIR'])
            except Exception as e:
                message = 'Unable to complete the import: %s %s' % (type(e).__name__, str(e))
                logger.error(message)
        else:
            message = 'IMPORTCSV already running'
            logger.debug(message)

        return message

    @cherrypy.expose
    def exportCSV(self, library='eBook'):
        self.label_thread('EXPORTCSV')
        message = export_CSV(bookbagofholding.CONFIG['ALTERNATE_DIR'], library=library)
        message = message.replace('\n', '<br>')
        return message

    # JOB CONTROL #######################################################

    @cherrypy.expose
    def shutdown(self):
        self.label_thread('SHUTDOWN')
        # bookbagofholding.config_write()
        bookbagofholding.SIGNAL = 'shutdown'
        message = 'closing ...'
        return serve_template(templatename="shutdown.html", prefix='Bookbag of Holding is ', title="Close library",
                              message=message, timer=15)

    @cherrypy.expose
    def restart(self):
        self.label_thread('RESTART')
        bookbagofholding.SIGNAL = 'restart'
        message = 'reopening ...'
        return serve_template(templatename="shutdown.html", prefix='Bookbag of Holding is ', title="Reopen library",
                              message=message, timer=30)

    @cherrypy.expose
    def show_Jobs(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # show the current status of LL cron jobs
        resultlist = showJobs()
        result = ''
        for line in resultlist:
            result = result + line + '\n'
        return result

    @cherrypy.expose
    def show_Stats(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # show some database status info
        resultlist = showStats()
        result = ''
        for line in resultlist:
            result = result + line + '\n'
        return result

    @cherrypy.expose
    def restart_Jobs(self):
        restartJobs(start='Restart')
        # return self.show_Jobs()

    @cherrypy.expose
    def stop_Jobs(self):
        restartJobs(start='Stop')
        # return self.show_Jobs()

    # LOGGING ###########################################################

    @cherrypy.expose
    def clearLog(self):
        # Clear the log
        result = clearLog()
        logger.info(result)
        raise cherrypy.HTTPRedirect("logs")

    @cherrypy.expose
    def logHeader(self):
        # Return the log header info
        result = logHeader()
        return result

    @cherrypy.expose
    def saveLog(self):
        # Save the debug log to a zipfile
        self.label_thread('SAVELOG')
        result = saveLog()
        logger.info(result)
        raise cherrypy.HTTPRedirect("logs")

    @cherrypy.expose
    def toggleLog(self):
        # Toggle the debug log
        # LOGLEVEL 0, quiet
        # 1 normal
        # 2 debug
        # >2 extra debugging
        self.label_thread()
        if bookbagofholding.LOGLEVEL > 1:
            bookbagofholding.LOGLEVEL = 1
        else:
            if bookbagofholding.LOGLEVEL < 2:
                bookbagofholding.LOGLEVEL = 2
        if bookbagofholding.LOGLEVEL < 2:
            logger.info('Debug log OFF, loglevel is %s' % bookbagofholding.LOGLEVEL)
        else:
            logger.info('Debug log ON, loglevel is %s' % bookbagofholding.LOGLEVEL)
        raise cherrypy.HTTPRedirect("logs")

    @cherrypy.expose
    def logs(self):
        return serve_template(templatename="logs.html", title="Log", lineList=[])  # bookbagofholding.LOGLIST)

    # noinspection PyUnusedLocal
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getLog(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        rows = []
        filtered = []
        # noinspection PyBroadException
        try:
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            bookbagofholding.CONFIG['DISPLAYLENGTH'] = iDisplayLength

            if sSearch:
                if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                    logger.debug("filter %s" % sSearch)
                filtered = [x for x in bookbagofholding.LOGLIST[::] if sSearch.lower() in str(x).lower()]
            else:
                filtered = bookbagofholding.LOGLIST[::]

            sortcolumn = int(iSortCol_0)
            if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                logger.debug("sortcolumn %d" % sortcolumn)

            filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")
            if iDisplayLength < 0:  # display = all
                rows = filtered
            else:
                rows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]
            if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                logger.debug("getLog returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getLog filtered %s from %s:%s" % (len(filtered), len(bookbagofholding.LOGLIST), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getLog: %s' % traceback.format_exc())
            rows = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(bookbagofholding.LOGLIST),
                      'aaData': rows,
                      }
            return mydict

    # HISTORY ###########################################################

    @cherrypy.expose
    def history(self):
        return serve_template(templatename="history.html", title="History", history=[])

    # noinspection PyUnusedLocal
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getHistory(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        # kwargs is used by datatables to pass params
        # for arg in kwargs:
        #     print arg, kwargs[arg]
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            myDB = database.DBConnection()
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            bookbagofholding.CONFIG['DISPLAYLENGTH'] = iDisplayLength
            myDB = database.DBConnection()
            cmd = "SELECT NZBTitle,AuxInfo,BookID,NZBProv,NZBDate,NZBSize,Status,Source,DownloadID,rowid from wanted"
            rowlist = myDB.select(cmd)
            # turn the sqlite rowlist into a list of dicts
            if len(rowlist):
                # the masterlist to be filled with the row data
                for row in rowlist:  # iterate through the sqlite3.Row objects
                    nrow = list(row)
                    # title needs spaces, not dots, for column resizing
                    title = nrow[0]  # type: str
                    if title:
                        title = title.replace('.', ' ')
                        title = title.replace('LL (', 'LL.(')
                        nrow[0] = title
                    # provider name needs to be shorter and with spaces for column resizing
                    if nrow[3]:
                        nrow[3] = dispName(nrow[3].strip('/'))
                        rows.append(nrow)  # add the rowlist to the masterlist

                if sSearch:
                    if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    filtered = [x for x in rows if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rows

                sortcolumn = int(iSortCol_0)
                if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                if sortcolumn == 6:
                    sortcolumn = 9

                filtered.sort(key=lambda y: y[sortcolumn], reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    nrows = filtered
                else:
                    nrows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

                bookbagofholding.HIST_REFRESH = 0
                rows = []
                for row in nrows:
                    rowid = row[9]
                    row = row[:9]
                    if row[6] == 'Snatched':
                        progress = getDownloadProgress(row[7], row[8])
                        row.append(progress)
                        if progress < 100:
                            bookbagofholding.HIST_REFRESH = bookbagofholding.CONFIG['HIST_REFRESH']
                    else:
                        row.append(-1)
                    row.append(rowid)
                    row.append(row[4])  # keep full datetime for tooltip
                    row[4] = dateFormat(row[4], bookbagofholding.CONFIG['DATE_FORMAT'])
                    rows.append(row)

            if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                logger.debug("getHistory returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getHistory filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getHistory: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @cherrypy.expose
    def bookdesc(self, bookid=None):
        global lastauthor
        myDB = database.DBConnection()
        if not bookid:
            return 'No BookID^No BookID'
        res = myDB.match("SELECT BookName,BookDesc,AuthorID from books WHERE bookid=?", (bookid,))
        if not res:
            return 'BookID not found^No Details'
        text = res['BookDesc']
        if not text:
            text = "No Description"
        lastauthor = res['AuthorID']
        return res['BookName'] + '^' + text

    @cherrypy.expose
    def dlinfo(self, target=None):
        myDB = database.DBConnection()
        if '^' not in target:
            return ''
        status, rowid = target.split('^')
        if status == 'Ignored':
            match = myDB.match('select ScanResult from books WHERE bookid=?', (rowid,))
            message = 'Reason: %s<br>' % match['ScanResult']
        else:
            cmd = 'select NZBurl,NZBtitle,NZBdate,NZBprov,Status,NZBsize,AuxInfo,NZBmode,DLResult,Source,DownloadID '
            cmd += 'from wanted where rowid=?'
            match = myDB.match(cmd, (rowid,))
            dltype = match['AuxInfo']
            if dltype not in ['eBook', 'AudioBook']:
                dltype = 'eBook'
            message = "Title: %s<br>" % match['NZBtitle']
            message += "Type: %s %s<br>" % (match['NZBmode'], dltype)
            message += "Date: %s<br>" % match['NZBdate']
            message += "Size: %s Mb<br>" % match['NZBsize']
            message += "Provider: %s<br>" % dispName(match['NZBprov'])
            message += "Downloader: %s<br>" % match['Source']
            message += "DownloadID: %s<br>" % match['DownloadID']
            message += "URL: %s<br>" % match['NZBurl']
            if status == 'Processed':
                message += "File: %s<br>" % match['DLResult']
            else:
                message += "Error: %s<br>" % match['DLResult']
        return message

    @cherrypy.expose
    def deletehistory(self, rowid=None):
        myDB = database.DBConnection()
        if not rowid:
            return
        match = myDB.match('SELECT NZBtitle,Status from wanted WHERE rowid=?', (rowid,))
        if match:
            logger.debug('Deleting %s history item %s' % (match['Status'], match['NZBtitle']))
            myDB.action('DELETE from wanted WHERE rowid=?', (rowid,))

    @cherrypy.expose
    def markhistory(self, rowid=None):
        myDB = database.DBConnection()
        if not rowid:
            return
        match = myDB.match('SELECT NZBurl,NZBtitle,NZBprov,Status,BookID,AuxInfo from wanted WHERE rowid=?', (rowid,))
        logger.debug('Marking %s history item %s as Failed' % (match['Status'], match['NZBtitle']))
        myDB.action('UPDATE wanted SET Status="Failed" WHERE rowid=?', (rowid,))
        # Add to blacklist if BLACKLIST_FAILED is enabled
        if bookbagofholding.CONFIG['BLACKLIST_FAILED']:
            add_to_blacklist(match['NZBurl'], match['NZBtitle'], match['NZBprov'],
                             match['BookID'], match['AuxInfo'], 'Failed')
        book_type = match['AuxInfo']
        if book_type not in ['AudioBook', 'eBook']:
            book_type = 'eBook'
        if book_type == 'AudioBook':
            myDB.action('UPDATE books SET audiostatus="Wanted" WHERE BookID=?', (match['BookID'],))
        else:
            myDB.action('UPDATE books SET status="Wanted" WHERE BookID=?', (match['BookID'],))

    @cherrypy.expose
    def clearhistory(self, status=None):
        myDB = database.DBConnection()
        if not status or status == 'all':
            logger.info("Clearing all history")
            # also reset the Snatched status in book table to Wanted and cancel any failed download task
            # ONLY reset if status is still Snatched, as maybe a later task succeeded
            status = "Snatched"
            cmd = 'SELECT BookID,AuxInfo,Source,DownloadID from wanted WHERE Status=?'
            rowlist = myDB.select(cmd, (status,))
            for book in rowlist:
                if book['BookID'] != 'unknown':
                    if book['AuxInfo'] == 'eBook':
                        myDB.action('UPDATE books SET Status="Wanted" WHERE Bookid=? AND Status=?',
                                    (book['BookID'], status))
                    elif book['AuxInfo'] == 'AudioBook':
                        myDB.action('UPDATE books SET AudioStatus="Wanted" WHERE Bookid=? AND AudioStatus=?',
                                    (book['BookID'], status))
                    delete_task(book['Source'], book['DownloadID'], True)
            myDB.action("DELETE from wanted")
        else:
            logger.info("Clearing history where status is %s" % status)
            if status == 'Snatched':
                # also reset the Snatched status in book table to Wanted and cancel any failed download task
                # ONLY reset if status is still Snatched, as maybe a later task succeeded
                cmd = 'SELECT BookID,AuxInfo,Source,DownloadID from wanted WHERE Status=?'
                rowlist = myDB.select(cmd, (status,))
                for book in rowlist:
                    if book['BookID'] != 'unknown':
                        if book['AuxInfo'] == 'eBook':
                            myDB.action('UPDATE books SET Status="Wanted" WHERE Bookid=? AND Status=?',
                                        (book['BookID'], status))
                        elif book['AuxInfo'] == 'AudioBook':
                            myDB.action('UPDATE books SET AudioStatus="Wanted" WHERE Bookid=? AND AudioStatus=?',
                                        (book['BookID'], status))
                    delete_task(book['Source'], book['DownloadID'], True)
            myDB.action('DELETE from wanted WHERE Status=?', (status,))
        raise cherrypy.HTTPRedirect("history")

    # ACTIVE DOWNLOADS PAGE
    @cherrypy.expose
    def activeDownloads(self):
        return serve_template(templatename="activedownloads.html", title="Active Downloads")

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getActiveDownloads(self, iDisplayStart=0, iDisplayLength=10, sSearch='', **kwargs):
        """
        AJAX endpoint for DataTables - returns active downloads with real-time progress.
        """
        self.label_thread('ACTIVEDL')
        myDB = database.DBConnection()

        # Get all snatched items
        cmd = 'SELECT rowid, * FROM wanted WHERE Status="Snatched"'
        rowlist = myDB.select(cmd)

        # Filter by search term if provided
        if sSearch:
            sSearch = sSearch.lower()
            rowlist = [r for r in rowlist if sSearch in r['NZBtitle'].lower() or
                       sSearch in (r['Source'] or '').lower() or
                       sSearch in (r['NZBprov'] or '').lower()]

        total_count = len(rowlist)

        # Apply pagination
        iDisplayStart = int(iDisplayStart)
        iDisplayLength = int(iDisplayLength)
        if iDisplayLength > 0:
            rowlist = rowlist[iDisplayStart:iDisplayStart + iDisplayLength]

        # Build response with real-time progress
        rows = []
        for item in rowlist:
            # Get progress from download client
            progress = -1
            if item['Source'] and item['DownloadID']:
                try:
                    progress = getDownloadProgress(item['Source'], item['DownloadID'])
                except Exception:
                    progress = -1

            # Format title for display
            title = item['NZBtitle'].replace('.', ' ') if item['NZBtitle'] else 'Unknown'

            # Format date
            date_str = item['NZBdate'] or ''
            if date_str:
                try:
                    from bookbagofholding.formatter import dateFormat
                    date_str = dateFormat(date_str)
                except Exception:
                    pass

            # Format size
            size_str = item['NZBsize'] or ''
            if size_str:
                try:
                    size_mb = float(size_str)
                    if size_mb > 1024:
                        size_str = '%.1f GB' % (size_mb / 1024)
                    else:
                        size_str = '%.1f MB' % size_mb
                except Exception:
                    pass

            rows.append([
                title,                          # 0: Title
                item['AuxInfo'] or 'eBook',     # 1: Type (eBook/AudioBook)
                item['Source'] or 'Unknown',    # 2: Client
                item['NZBprov'] or 'Unknown',   # 3: Provider
                progress,                       # 4: Progress (integer for sorting)
                date_str,                       # 5: Date
                item['rowid'],                  # 6: Row ID (for actions)
                item['BookID'] or ''            # 7: Book ID
            ])

        return {
            'aaData': rows,
            'iTotalRecords': total_count,
            'iTotalDisplayRecords': total_count
        }

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def cancelDownload(self, rowid=None, blacklist='0'):
        """
        Cancel a download, optionally adding it to the blacklist.
        """
        self.label_thread('CANCEL')
        if not rowid:
            return {'success': False, 'error': 'Missing rowid parameter'}

        myDB = database.DBConnection()

        # Get the wanted record
        item = myDB.match('SELECT * FROM wanted WHERE rowid=?', (rowid,))
        if not item:
            return {'success': False, 'error': 'Download not found'}

        # Cancel the download in the client
        if item['Source'] and item['DownloadID']:
            try:
                delete_task(item['Source'], item['DownloadID'], True)
                logger.info('Cancelled download %s from %s' % (item['NZBtitle'], item['Source']))
            except Exception as e:
                logger.warn('Failed to cancel download from client: %s' % str(e))

        # Add to blacklist if requested
        if blacklist == '1':
            add_to_blacklist(
                item['NZBurl'],
                item['NZBtitle'],
                item['NZBprov'],
                item['BookID'],
                item['AuxInfo'],
                'Cancelled'
            )
            logger.info('Added cancelled download to blacklist: %s' % item['NZBtitle'])

        # Reset book status to Wanted
        if item['BookID'] and item['BookID'] != 'unknown':
            if item['AuxInfo'] == 'AudioBook':
                myDB.action('UPDATE books SET AudioStatus="Wanted" WHERE BookID=? AND AudioStatus="Snatched"',
                            (item['BookID'],))
            else:
                myDB.action('UPDATE books SET Status="Wanted" WHERE BookID=? AND Status="Snatched"',
                            (item['BookID'],))

        # Remove from wanted table
        myDB.action('DELETE FROM wanted WHERE rowid=?', (rowid,))

        return {'success': True, 'message': 'Download cancelled'}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def cancelAllDownloads(self, blacklist='0'):
        """
        Cancel all active downloads, optionally adding them to the blacklist.
        """
        self.label_thread('CANCELALL')
        myDB = database.DBConnection()

        # Get all snatched items
        rowlist = myDB.select('SELECT * FROM wanted WHERE Status="Snatched"')

        cancelled = 0
        for item in rowlist:
            # Cancel in client
            if item['Source'] and item['DownloadID']:
                try:
                    delete_task(item['Source'], item['DownloadID'], True)
                except Exception as e:
                    logger.warn('Failed to cancel download from client: %s' % str(e))

            # Add to blacklist if requested
            if blacklist == '1':
                add_to_blacklist(
                    item['NZBurl'],
                    item['NZBtitle'],
                    item['NZBprov'],
                    item['BookID'],
                    item['AuxInfo'],
                    'Cancelled'
                )

            # Reset book status to Wanted
            if item['BookID'] and item['BookID'] != 'unknown':
                if item['AuxInfo'] == 'AudioBook':
                    myDB.action('UPDATE books SET AudioStatus="Wanted" WHERE BookID=? AND AudioStatus="Snatched"',
                                (item['BookID'],))
                else:
                    myDB.action('UPDATE books SET Status="Wanted" WHERE BookID=? AND Status="Snatched"',
                                (item['BookID'],))

            cancelled += 1

        # Remove all snatched items from wanted table
        myDB.action('DELETE FROM wanted WHERE Status="Snatched"')

        logger.info('Cancelled %d active downloads' % cancelled)
        return {'success': True, 'message': 'Cancelled %d downloads' % cancelled}

    # noinspection PyUnusedLocal
    @cherrypy.expose
    def blocklist(self):
        return serve_template(templatename="blocklist.html", title="Blocklist", blocklist=[])

    # noinspection PyUnusedLocal
    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getBlocklist(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0, sSortDir_0="desc", sSearch="", **kwargs):
        rows = []
        filtered = []
        rowlist = []
        # noinspection PyBroadException
        try:
            myDB = database.DBConnection()
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)
            bookbagofholding.CONFIG['DISPLAYLENGTH'] = iDisplayLength
            cmd = "SELECT NZBtitle,AuxInfo,BookID,NZBprov,DateAdded,Reason,NZBurl,rowid from blacklist"
            rowlist = myDB.select(cmd)
            if len(rowlist):
                for row in rowlist:
                    nrow = list(row)
                    # title needs spaces, not dots, for column resizing
                    title = nrow[0]
                    if title:
                        title = title.replace('.', ' ')
                        title = title.replace('LL (', 'LL.(')
                        nrow[0] = title
                    # provider name needs to be shorter and with spaces for column resizing
                    if nrow[3]:
                        nrow[3] = dispName(nrow[3].strip('/'))
                    rows.append(nrow)

                if sSearch:
                    if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                        logger.debug("filter %s" % sSearch)
                    filtered = [x for x in rows if sSearch.lower() in str(x).lower()]
                else:
                    filtered = rows

                sortcolumn = int(iSortCol_0)
                if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                    logger.debug("sortcolumn %d" % sortcolumn)

                filtered.sort(key=lambda y: y[sortcolumn] or '', reverse=sSortDir_0 == "desc")

                if iDisplayLength < 0:  # display = all
                    nrows = filtered
                else:
                    nrows = filtered[iDisplayStart:(iDisplayStart + iDisplayLength)]

                rows = []
                for row in nrows:
                    rowid = row[7]
                    row = row[:7]
                    row.append(rowid)
                    row.append(row[4])  # keep full datetime for tooltip
                    row[4] = dateFormat(row[4], bookbagofholding.CONFIG['DATE_FORMAT'])
                    rows.append(row)

            if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                logger.debug("getBlocklist returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getBlocklist filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))
        except Exception:
            logger.error('Unhandled exception in getBlocklist: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @cherrypy.expose
    def deleteBlocklistItem(self, rowid=None):
        myDB = database.DBConnection()
        if not rowid:
            return
        match = myDB.match('SELECT NZBtitle from blacklist WHERE rowid=?', (rowid,))
        if match:
            logger.debug('Deleting blocklist item %s' % match['NZBtitle'])
            myDB.action('DELETE from blacklist WHERE rowid=?', (rowid,))

    @cherrypy.expose
    def clearBlocklist(self, reason=None):
        myDB = database.DBConnection()
        if not reason or reason == 'all':
            logger.info("Clearing all blocklist entries")
            myDB.action("DELETE from blacklist")
        else:
            logger.info("Clearing blocklist entries where reason is %s" % reason)
            myDB.action('DELETE from blacklist WHERE Reason=?', (reason,))
        raise cherrypy.HTTPRedirect("blocklist")

    @cherrypy.expose
    def testprovider(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "TESTPROVIDER"
        if 'name' in kwargs and kwargs['name']:
            host = ''
            api = ''
            if 'host' in kwargs and kwargs['host']:
                host = kwargs['host']
            if 'api' in kwargs and kwargs['api']:
                api = kwargs['api']
            result, name = test_provider(kwargs['name'], host=host, api=api)
            if result:
                bookbagofholding.config_write(kwargs['name'])
                msg = "%s test PASSED" % name
            else:
                msg = "%s test FAILED, check debug log" % name
        else:
            msg = "Invalid or missing name in testprovider"
        return msg

    @cherrypy.expose
    def clearblocked(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # clear any currently blocked providers
        num = len(bookbagofholding.PROVIDER_BLOCKLIST)
        bookbagofholding.PROVIDER_BLOCKLIST = []
        result = 'Cleared %s blocked provider%s' % (num, plural(num))
        logger.debug(result)
        return result

    @cherrypy.expose
    def showblocked(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # show any currently blocked providers
        result = ''
        for line in bookbagofholding.PROVIDER_BLOCKLIST:
            resume = int(line['resume']) - int(time.time())
            if resume > 0:
                resume = int(resume / 60) + (resume % 60 > 0)
                if resume > 180:
                    resume = int(resume / 60) + (resume % 60 > 0)
                    new_entry = "%s blocked for %s hour%s, %s\n" % (line['name'], resume,
                                                                    plural(resume), line['reason'])
                else:
                    new_entry = "%s blocked for %s minute%s, %s\n" % (line['name'], resume,
                                                                      plural(resume), line['reason'])
                result = result + new_entry

        if result == '':
            result = 'No blocked providers'
        logger.debug(result)
        return result

    @cherrypy.expose
    def cleardownloads(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # clear download counters
        myDB = database.DBConnection()
        count = myDB.match('SELECT COUNT(*) as counter FROM downloads')
        if count:
            num = count['counter']
        else:
            num = 0
        result = 'Deleted download counter for %s provider%s' % (num, plural(num))
        myDB.action('DELETE from downloads')
        logger.debug(result)
        return result

    @cherrypy.expose
    def showdownloads(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        # show provider download totals
        myDB = database.DBConnection()
        result = ''
        downloads = myDB.select('SELECT Count,Provider FROM downloads ORDER BY Count DESC')
        for line in downloads:
            provname = dispName(line['Provider'].strip('/'))
            new_entry = "%4d - %s\n" % (line['Count'], provname)
            result = result + new_entry

        if result == '':
            result = 'No downloads'
        return result

    @cherrypy.expose
    def syncToCalibre(self):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        if 'CalSync' in [n.name for n in [t for t in threading.enumerate()]]:
            msg = 'Calibre Sync is already running'
        else:
            self.label_thread('CalSync')
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in list(cookie.keys()):
                userid = cookie['ll_uid'].value
                msg = syncCalibreList(userid=userid)
                self.label_thread('WEBSERVER')
            else:
                msg = "No userid found"
        return msg

    # API ###############################################################

    @cherrypy.expose
    def api(self, **kwargs):
        from bookbagofholding.api import Api
        a = Api()
        # noinspection PyArgumentList
        a.checkParams(**kwargs)
        return a.fetchData

    @cherrypy.expose
    def generateAPI(self):
        api_key = hashlib.sha224(str(random.getrandbits(256)).encode('utf-8')).hexdigest()[0:32]
        bookbagofholding.CONFIG['API_KEY'] = api_key
        bookbagofholding.CONFIG['API_ENABLED'] = 1
        bookbagofholding.config_write('General')
        logger.info("New API generated")
        raise cherrypy.HTTPRedirect("config")

    # ALL ELSE ##########################################################

    @cherrypy.expose
    def forceProcess(self, source=None):
        if 'POSTPROCESS' not in [n.name for n in [t for t in threading.enumerate()]]:
            bookbagofholding.POSTPROCESS_UPDATE = True
            threading.Thread(target=processDir, name='POSTPROCESS', args=[True]).start()
            scheduleJob(action='Restart', target='PostProcessor')
        else:
            logger.debug('POSTPROCESS already running')
        raise cherrypy.HTTPRedirect(source)

    @cherrypy.expose
    def forceWish(self, source=None):
        if bookbagofholding.USE_WISHLIST():
            search_wishlist()
        else:
            logger.warn('WishList search called but no wishlist providers set')
        if source:
            raise cherrypy.HTTPRedirect(source)
        raise cherrypy.HTTPRedirect('books')

    @cherrypy.expose
    def forceSearch(self, source=None, title=None):
        if source in ["books", "audio"]:
            if bookbagofholding.USE_NZB() or bookbagofholding.USE_TOR() \
                    or bookbagofholding.USE_RSS() or bookbagofholding.USE_DIRECT():
                if 'SEARCHALLBOOKS' not in [n.name for n in [t for t in threading.enumerate()]]:
                    threading.Thread(target=search_book, name='SEARCHALLBOOKS', args=[]).start()
                    scheduleJob(action='Restart', target='search_book')
                    if bookbagofholding.USE_RSS():
                        scheduleJob(action='Restart', target='search_rss_book')
            else:
                logger.warn('Search called but no download providers set')
        else:
            logger.debug("forceSearch called with bad source")
            raise cherrypy.HTTPRedirect('books')
        raise cherrypy.HTTPRedirect(source)

    @cherrypy.expose
    def manage(self, whichStatus=None, **kwargs):
        library = 'eBook'
        if 'library' in kwargs:
            library = kwargs['library']
        if not whichStatus or whichStatus == 'None':
            whichStatus = "Wanted"
        types = ['eBook']
        if bookbagofholding.SHOW_AUDIO:
            types.append('AudioBook')
        return serve_template(templatename="managebooks.html", title="%ss by Status" % library,
                              books=[], types=types, library=library, whichStatus=whichStatus)

    @cherrypy.expose
    def unmatchedFiles(self, whichStatus=None, library=None, **kwargs):
        """Display the unmatched files page."""
        threading.currentThread().name = "WEBSERVER"

        if not whichStatus:
            whichStatus = 'Unmatched'
        if not library:
            library = 'eBook'

        types = ['eBook']
        if bookbagofholding.SHOW_AUDIO:
            types.append('AudioBook')

        return serve_template(templatename="unmatchedfiles.html",
                              title="Unmatched Files",
                              library=library,
                              whichStatus=whichStatus,
                              types=types)

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def getUnmatchedFiles(self, iDisplayStart=0, iDisplayLength=100, iSortCol_0=0,
                          sSortDir_0="desc", sSearch="", **kwargs):
        """Server-side DataTables handler for unmatched files."""
        rows = []
        filtered = []
        rowlist = []

        try:
            iDisplayStart = int(iDisplayStart)
            iDisplayLength = int(iDisplayLength)

            myDB = database.DBConnection()

            library = kwargs.get('library', 'eBook')
            status = kwargs.get('whichStatus', 'Unmatched')

            # Check if table exists (handles case before migration)
            table_check = myDB.match("SELECT name FROM sqlite_master WHERE type='table' AND name='unmatchedfiles'")
            if not table_check:
                # Table doesn't exist yet - return empty result
                return {
                    'iTotalRecords': 0,
                    'iTotalDisplayRecords': 0,
                    'aaData': []
                }

            # Build query
            cmd = 'SELECT * FROM unmatchedfiles WHERE LibraryType=? AND Status=?'
            args = [library, status]

            db_rows = myDB.select(cmd, tuple(args))

            # Build rowlist with formatted data
            for row in db_rows:
                # Format file size
                size_str = ''
                if row['FileSize']:
                    size_mb = row['FileSize'] / (1024 * 1024)
                    if size_mb >= 1:
                        size_str = '%.1f MB' % size_mb
                    else:
                        size_str = '%.0f KB' % (row['FileSize'] / 1024)

                rowlist.append([
                    row['FileID'],                              # 0: checkbox/ID
                    row['ExtractedAuthor'] or 'Unknown',        # 1: Author
                    row['ExtractedTitle'] or 'Unknown',         # 2: Title
                    row['FileName'],                            # 3: Filename
                    size_str,                                   # 4: Size
                    row['DateAdded'],                           # 5: Date Added
                    row['ScanCount'],                           # 6: Scan Count
                    row['FileExtension'] or '',                 # 7: Extension
                    row['ExtractedISBN'] or '',                 # 8: ISBN
                    row['FilePath']                             # 9: Full path (hidden)
                ])

            # Filter by search
            if sSearch:
                sSearch_lower = sSearch.lower()
                for item in rowlist:
                    if (sSearch_lower in (item[1] or '').lower() or
                            sSearch_lower in (item[2] or '').lower() or
                            sSearch_lower in (item[3] or '').lower()):
                        filtered.append(item)
            else:
                filtered = rowlist[:]

            # Sort
            sort_col = int(iSortCol_0)
            if sort_col < 7:
                reverse = sSortDir_0 == 'desc'
                filtered = sorted(filtered, key=lambda x: x[sort_col] or '', reverse=reverse)

            # Paginate
            if iDisplayLength < 0:
                rows = filtered[:]
            else:
                rows = filtered[iDisplayStart:iDisplayStart + iDisplayLength]

            if bookbagofholding.LOGLEVEL & bookbagofholding.log_serverside:
                logger.debug("getUnmatchedFiles returning %s to %s" % (iDisplayStart, iDisplayStart + iDisplayLength))
                logger.debug("getUnmatchedFiles filtered %s from %s:%s" % (len(filtered), len(rowlist), len(rows)))

        except Exception:
            logger.error('Unhandled exception in getUnmatchedFiles: %s' % traceback.format_exc())
            rows = []
            rowlist = []
            filtered = []
        finally:
            mydict = {'iTotalDisplayRecords': len(filtered),
                      'iTotalRecords': len(rowlist),
                      'aaData': rows,
                      }
            return mydict

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def searchBooksForMatch(self, query=None, **kwargs):
        """Search books database for potential matches."""
        if not query or len(query) < 2:
            return {'success': False, 'error': 'Query too short'}

        try:
            myDB = database.DBConnection()

            # Search by title or author
            query_like = '%' + query + '%'
            cmd = '''SELECT books.BookID, books.BookName, books.BookSub,
                            authors.AuthorName, books.BookDate, books.Status, books.AudioStatus
                     FROM books, authors
                     WHERE books.AuthorID = authors.AuthorID
                     AND (BookName LIKE ? OR AuthorName LIKE ? OR BookIsbn LIKE ?)
                     ORDER BY AuthorName, BookName
                     LIMIT 50'''

            results = myDB.select(cmd, (query_like, query_like, query_like))

            books = []
            for row in results:
                books.append({
                    'bookid': row['BookID'],
                    'title': row['BookName'],
                    'subtitle': row['BookSub'] or '',
                    'author': row['AuthorName'],
                    'date': row['BookDate'] or '',
                    'status': row['Status'],
                    'audiostatus': row['AudioStatus']
                })

            return {'success': True, 'results': books}

        except Exception as e:
            logger.error('searchBooksForMatch error: %s' % str(e))
            return {'success': False, 'error': str(e)}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def searchGoogleBooksForAuthor(self, query=None, authorid=None, **kwargs):
        """Search Google Books for books to add to author."""
        if not query or len(query) < 2:
            return {'success': False, 'error': 'Query too short'}

        try:
            # Search Google Books
            results = search_for(query)

            if not results:
                return {'success': True, 'results': []}

            myDB = database.DBConnection()

            # Get existing book IDs for this author to check if already exists
            existing_books = myDB.select('SELECT BookID FROM books WHERE AuthorID=?', (authorid,))
            existing_ids = set(row['BookID'] for row in existing_books)

            # Also get all book IDs in the database to show if book exists elsewhere
            all_books = myDB.select('SELECT BookID FROM books')
            all_ids = set(row['BookID'] for row in all_books)

            books = []
            for item in results[:20]:  # Limit to first 20 results
                book_id = item.get('bookid', '')
                exists_for_author = book_id in existing_ids
                exists_in_db = book_id in all_ids

                books.append({
                    'bookid': book_id,
                    'title': item.get('bookname', ''),
                    'subtitle': item.get('booksub', ''),
                    'author': item.get('authorname', ''),
                    'img': item.get('bookimg', ''),
                    'isbn': item.get('bookisbn', ''),
                    'date': item.get('bookdate', ''),
                    'exists': exists_for_author,
                    'existsElsewhere': exists_in_db and not exists_for_author
                })

            return {'success': True, 'results': books}

        except Exception as e:
            logger.error('searchGoogleBooksForAuthor error: %s' % str(e))
            return {'success': False, 'error': str(e)}

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def matchUnmatchedFile(self, fileid=None, bookid=None, library=None, **kwargs):
        """Match an unmatched file to a book and update the book's file location."""
        if not fileid or not bookid:
            return {'success': False, 'error': 'Missing fileid or bookid'}

        try:
            myDB = database.DBConnection()

            # Get the unmatched file details
            file_row = myDB.match('SELECT * FROM unmatchedfiles WHERE FileID=?', (fileid,))
            if not file_row:
                return {'success': False, 'error': 'File not found'}

            # Verify the file still exists
            filepath = file_row['FilePath']
            if not os.path.isfile(filepath):
                # Remove the unmatched entry
                myDB.action('DELETE FROM unmatchedfiles WHERE FileID=?', (fileid,))
                return {'success': False, 'error': 'File no longer exists on disk'}

            # Get the book
            book_row = myDB.match('SELECT * FROM books WHERE BookID=?', (bookid,))
            if not book_row:
                return {'success': False, 'error': 'Book not found'}

            # Determine library type
            library_type = file_row['LibraryType'] or library or 'eBook'
            found_status = bookbagofholding.CONFIG.get('FOUND_STATUS', 'Open')

            logger.debug('matchUnmatchedFile: library_type=%s, found_status=%s, bookid=%s' %
                         (library_type, found_status, bookid))

            # Update the book's file location
            if library_type == 'eBook':
                myDB.action('UPDATE books SET BookFile=?, Status=?, BookLibrary=? WHERE BookID=?',
                            (filepath, found_status, now(), bookid))
                logger.info('Updated book %s: Status=%s, BookFile=%s' % (bookid, found_status, filepath))
            else:  # AudioBook
                myDB.action('UPDATE books SET AudioFile=?, AudioStatus=?, AudioLibrary=? WHERE BookID=?',
                            (filepath, found_status, now(), bookid))
                logger.info('Updated book %s: AudioStatus=%s, AudioFile=%s' % (bookid, found_status, filepath))

            # Mark the unmatched file as matched
            mark_unmatched_file_matched(fileid, bookid, 'Manually matched by user')

            # Update author totals
            update_totals(book_row['AuthorID'])

            # Import to Calibre if configured (eBooks only)
            calibre_msg = ''
            if library_type == 'eBook' and bookbagofholding.CONFIG.get('IMP_CALIBREDB'):
                # Get author name
                author_row = myDB.match('SELECT AuthorName FROM authors WHERE AuthorID=?',
                                        (book_row['AuthorID'],))
                authorname = author_row['AuthorName'] if author_row else 'Unknown'
                success, calibre_msg = calibreImportBook(filepath, bookid, authorname, book_row['BookName'])
                if not success:
                    logger.warn('Calibre import failed: %s' % calibre_msg)

            logger.info('Manually matched file [%s] to book [%s]' % (filepath, book_row['BookName']))

            message = 'File matched successfully'
            if calibre_msg:
                message += ' (%s)' % calibre_msg
            return {'success': True, 'message': message}

        except Exception as e:
            logger.error('matchUnmatchedFile error: %s' % str(e))
            return {'success': False, 'error': str(e)}

    @cherrypy.expose
    def markUnmatchedFiles(self, action=None, redirect=None, **args):
        """Handle bulk actions on unmatched files."""
        threading.currentThread().name = "WEBSERVER"

        library = args.get('library', 'eBook')
        whichStatus = args.get('whichStatus', 'Unmatched')

        # Remove non-file args
        for arg in ['library', 'whichStatus', 'book_table_length']:
            args.pop(arg, None)

        myDB = database.DBConnection()

        if action:
            for fileid in args:
                if action == 'Ignore':
                    mark_unmatched_file_ignored(fileid, 'Ignored by user')
                    logger.debug('Marked unmatched file %s as ignored' % fileid)

                elif action == 'Remove':
                    myDB.action('DELETE FROM unmatchedfiles WHERE FileID=?', (fileid,))
                    logger.debug('Removed unmatched file entry %s' % fileid)

                elif action == 'Retry':
                    # Reset status to trigger re-scan
                    myDB.action('UPDATE unmatchedfiles SET Status="Unmatched" WHERE FileID=?',
                                (fileid,))
                    logger.debug('Reset unmatched file %s for retry' % fileid)

        raise cherrypy.HTTPRedirect("unmatchedFiles?library=%s&whichStatus=%s" % (library, whichStatus))

    @cherrypy.expose
    @cherrypy.tools.json_out()
    def retryMatchUnmatchedFile(self, fileid=None, library=None, **kwargs):
        """Retry matching a single unmatched file against the current database."""
        if not fileid:
            return {'success': False, 'error': 'Missing fileid'}

        try:
            myDB = database.DBConnection()

            file_row = myDB.match('SELECT * FROM unmatchedfiles WHERE FileID=?', (fileid,))
            if not file_row:
                return {'success': False, 'error': 'File not found'}

            # Verify file exists
            if not os.path.isfile(file_row['FilePath']):
                myDB.action('DELETE FROM unmatchedfiles WHERE FileID=?', (fileid,))
                return {'success': False, 'error': 'File no longer exists'}

            # Try to find a match using the existing fuzzy matching
            from bookbagofholding.librarysync import find_book_in_db

            author = file_row['ExtractedAuthor']
            title = file_row['ExtractedTitle']
            library_type = file_row['LibraryType'] or 'eBook'

            if not author or not title:
                return {'success': False, 'error': 'Missing author or title metadata'}

            bookid, status = find_book_in_db(author, title, library=library_type)

            if bookid:
                # Match found - link the file
                filepath = file_row['FilePath']
                found_status = bookbagofholding.CONFIG.get('FOUND_STATUS', 'Open')

                if library_type == 'eBook':
                    myDB.action('UPDATE books SET BookFile=?, Status=?, BookLibrary=? WHERE BookID=?',
                                (filepath, found_status, now(), bookid))
                    logger.info('Retry match: Updated book %s: Status=%s' % (bookid, found_status))
                else:
                    myDB.action('UPDATE books SET AudioFile=?, AudioStatus=?, AudioLibrary=? WHERE BookID=?',
                                (filepath, found_status, now(), bookid))
                    logger.info('Retry match: Updated book %s: AudioStatus=%s' % (bookid, found_status))

                # Mark as matched
                mark_unmatched_file_matched(fileid, bookid, 'Auto-matched on retry')

                # Get book info for response
                book = myDB.match('SELECT BookName, AuthorID FROM books WHERE BookID=?', (bookid,))

                # Update totals
                update_totals(book['AuthorID'])

                return {
                    'success': True,
                    'matched': True,
                    'bookid': bookid,
                    'bookname': book['BookName'],
                    'message': 'File matched to: %s' % book['BookName']
                }
            else:
                # No match found - update scan count
                myDB.action('UPDATE unmatchedfiles SET ScanCount=ScanCount+1, DateScanned=? WHERE FileID=?',
                            (now(), fileid))
                return {
                    'success': True,
                    'matched': False,
                    'message': 'No match found in database'
                }

        except Exception as e:
            logger.error('retryMatchUnmatchedFile error: %s' % str(e))
            return {'success': False, 'error': str(e)}

    @cherrypy.expose
    def testDeluge(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            bookbagofholding.CONFIG['DELUGE_HOST'] = kwargs['host']
        if 'base' in kwargs:
            bookbagofholding.CONFIG['DELUGE_BASE'] = kwargs['base']
        if 'cert' in kwargs:
            bookbagofholding.CONFIG['DELUGE_CERT'] = kwargs['cert']
        if 'port' in kwargs:
            bookbagofholding.CONFIG['DELUGE_PORT'] = check_int(kwargs['port'], 0)
        if 'pwd' in kwargs:
            bookbagofholding.CONFIG['DELUGE_PASS'] = kwargs['pwd']
        if 'label' in kwargs:
            bookbagofholding.CONFIG['DELUGE_LABEL'] = kwargs['label']
        if 'user' in kwargs:
            bookbagofholding.CONFIG['DELUGE_USER'] = kwargs['user']
            # if daemon, no cert used
            bookbagofholding.CONFIG['DELUGE_CERT'] = ''
            # and host must not contain http:// or https://
            host = bookbagofholding.CONFIG['DELUGE_HOST']
            host = host.replace('https://', '').replace('http://', '')
            bookbagofholding.CONFIG['DELUGE_HOST'] = host

        try:
            if not bookbagofholding.CONFIG['DELUGE_USER']:
                # no username, talk to the webui
                msg = deluge.checkLink()
                if 'FAILED' in msg:
                    return msg
            else:
                # if there's a username, talk to the daemon directly
                client = DelugeRPCClient(bookbagofholding.CONFIG['DELUGE_HOST'],
                                         check_int(bookbagofholding.CONFIG['DELUGE_PORT'], 0),
                                         bookbagofholding.CONFIG['DELUGE_USER'],
                                         bookbagofholding.CONFIG['DELUGE_PASS'])
                client.connect()
                msg = "Deluge: Daemon connection Successful\n"
                if bookbagofholding.CONFIG['DELUGE_LABEL']:
                    labels = client.call('label.get_labels')
                    if labels:
                        if bookbagofholding.LOGLEVEL & bookbagofholding.log_dlcomms:
                            logger.debug("Valid labels: %s" % str(labels))
                    else:
                        msg += "Deluge daemon seems to have no labels set\n"

                    mylabel = bookbagofholding.CONFIG['DELUGE_LABEL'].lower()
                    if mylabel != bookbagofholding.CONFIG['DELUGE_LABEL']:
                        bookbagofholding.CONFIG['DELUGE_LABEL'] = mylabel

                    labels = [makeUnicode(s) for s in labels]
                    if mylabel not in labels:
                        res = client.call('label.add', mylabel)
                        if not res:
                            msg += "Label [%s] was added" % bookbagofholding.CONFIG['DELUGE_LABEL']
                        else:
                            msg = str(res)
                    else:
                        msg += 'Label [%s] is valid' % bookbagofholding.CONFIG['DELUGE_LABEL']
            # success, save settings
            bookbagofholding.config_write('DELUGE')
            return msg

        except Exception as e:
            msg = "Deluge: Daemon connection FAILED\n"
            if 'Connection refused' in str(e):
                msg += str(e)
                msg += "Check Deluge daemon HOST and PORT settings"
            elif 'need more than 1 value' in str(e):
                msg += "Invalid USERNAME or PASSWORD"
            else:
                msg += type(e).__name__ + ' ' + str(e)
            return msg

    @cherrypy.expose
    def testSABnzbd(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            bookbagofholding.CONFIG['SAB_HOST'] = kwargs['host']
        if 'port' in kwargs:
            bookbagofholding.CONFIG['SAB_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            bookbagofholding.CONFIG['SAB_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            bookbagofholding.CONFIG['SAB_PASS'] = kwargs['pwd']
        if 'api' in kwargs:
            bookbagofholding.CONFIG['SAB_API'] = kwargs['api']
        if 'cat' in kwargs:
            bookbagofholding.CONFIG['SAB_CAT'] = kwargs['cat']
        if 'subdir' in kwargs:
            bookbagofholding.CONFIG['SAB_SUBDIR'] = kwargs['subdir']
        msg = sabnzbd.checkLink()
        if 'success' in msg:
            bookbagofholding.config_write('SABnzbd')
        return msg

    @cherrypy.expose
    def testNZBget(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            bookbagofholding.CONFIG['NZBGET_HOST'] = kwargs['host']
        if 'port' in kwargs:
            bookbagofholding.CONFIG['NZBGET_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            bookbagofholding.CONFIG['NZBGET_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            bookbagofholding.CONFIG['NZBGET_PASS'] = kwargs['pwd']
        if 'cat' in kwargs:
            bookbagofholding.CONFIG['NZBGET_CATEGORY'] = kwargs['cat']
        if 'pri' in kwargs:
            bookbagofholding.CONFIG['NZBGET_PRIORITY'] = check_int(kwargs['pri'], 0)
        msg = nzbget.checkLink()
        if 'success' in msg:
            bookbagofholding.config_write('NZBGet')
        return msg

    @cherrypy.expose
    def testTransmission(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            bookbagofholding.CONFIG['TRANSMISSION_HOST'] = kwargs['host']
        if 'base' in kwargs:
            bookbagofholding.CONFIG['TRANSMISSION_BASE'] = kwargs['base']
        if 'port' in kwargs:
            bookbagofholding.CONFIG['TRANSMISSION_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            bookbagofholding.CONFIG['TRANSMISSION_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            bookbagofholding.CONFIG['TRANSMISSION_PASS'] = kwargs['pwd']
        msg = transmission.checkLink()
        if 'success' in msg:
            bookbagofholding.config_write('TRANSMISSION')
        return msg

    @cherrypy.expose
    def testqBittorrent(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            bookbagofholding.CONFIG['QBITTORRENT_HOST'] = kwargs['host']
        if 'port' in kwargs:
            bookbagofholding.CONFIG['QBITTORRENT_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            bookbagofholding.CONFIG['QBITTORRENT_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            bookbagofholding.CONFIG['QBITTORRENT_PASS'] = kwargs['pwd']
        if 'label' in kwargs:
            bookbagofholding.CONFIG['QBITTORRENT_LABEL'] = kwargs['label']
        msg = qbittorrent.checkLink()
        if 'success' in msg:
            bookbagofholding.config_write('QBITTORRENT')
        return msg

    @cherrypy.expose
    def testuTorrent(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            bookbagofholding.CONFIG['UTORRENT_HOST'] = kwargs['host']
        if 'port' in kwargs:
            bookbagofholding.CONFIG['UTORRENT_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            bookbagofholding.CONFIG['UTORRENT_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            bookbagofholding.CONFIG['UTORRENT_PASS'] = kwargs['pwd']
        if 'label' in kwargs:
            bookbagofholding.CONFIG['UTORRENT_LABEL'] = kwargs['label']
        msg = utorrent.checkLink()
        if 'success' in msg:
            bookbagofholding.config_write('UTORRENT')
        return msg

    @cherrypy.expose
    def testrTorrent(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            bookbagofholding.CONFIG['RTORRENT_HOST'] = kwargs['host']
        if 'dir' in kwargs:
            bookbagofholding.CONFIG['RTORRENT_DIR'] = kwargs['dir']
        if 'user' in kwargs:
            bookbagofholding.CONFIG['RTORRENT_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            bookbagofholding.CONFIG['RTORRENT_PASS'] = kwargs['pwd']
        if 'label' in kwargs:
            bookbagofholding.CONFIG['RTORRENT_LABEL'] = kwargs['label']
        msg = rtorrent.checkLink()
        if 'success' in msg:
            bookbagofholding.config_write('RTORRENT')
        return msg

    @cherrypy.expose
    def testSynology(self, **kwargs):
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        threading.currentThread().name = "WEBSERVER"
        if 'host' in kwargs:
            bookbagofholding.CONFIG['SYNOLOGY_HOST'] = kwargs['host']
        if 'port' in kwargs:
            bookbagofholding.CONFIG['SYNOLOGY_PORT'] = check_int(kwargs['port'], 0)
        if 'user' in kwargs:
            bookbagofholding.CONFIG['SYNOLOGY_USER'] = kwargs['user']
        if 'pwd' in kwargs:
            bookbagofholding.CONFIG['SYNOLOGY_PASS'] = kwargs['pwd']
        if 'dir' in kwargs:
            bookbagofholding.CONFIG['SYNOLOGY_DIR'] = kwargs['dir']
        msg = synology.checkLink()
        if 'success' in msg:
            bookbagofholding.config_write('SYNOLOGY')
        return msg

    @cherrypy.expose
    def testCalibredb(self, **kwargs):
        threading.currentThread().name = "WEBSERVER"
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        cherrypy.response.headers['Content-Type'] = "text/plain"
        if 'prg' in kwargs and kwargs['prg']:
            bookbagofholding.CONFIG['IMP_CALIBREDB'] = kwargs['prg']
        try:
            result = calibreTest()
            return result
        except Exception as e:
            import traceback
            logger.error('testCalibredb exception: %s' % traceback.format_exc())
            return 'Error testing calibredb: %s %s' % (type(e).__name__, str(e))

    @cherrypy.expose
    def testPreProcessor(self, **kwargs):
        threading.currentThread().name = "WEBSERVER"
        cherrypy.response.headers['Cache-Control'] = "max-age=0,no-cache,no-store"
        if 'prg' in kwargs and kwargs['prg']:
            bookbagofholding.CONFIG['IMP_PREPROCESS'] = kwargs['prg']

        params = [bookbagofholding.CONFIG['IMP_PREPROCESS'], 'test', '']
        rc, res, err = runScript(params)
        if rc:
            return "Preprocessor returned %s: res[%s] err[%s]" % (rc, res, err)
        return res

    @cherrypy.expose
    def opds(self, **kwargs):
        op = OPDS()
        op.checkParams(**kwargs)
        data = op.fetchData()
        return data

    @staticmethod
    def send_file(basefile, name=None):
        if bookbagofholding.CONFIG['USER_ACCOUNTS']:
            myDB = database.DBConnection()
            cookie = cherrypy.request.cookie
            if cookie and 'll_uid' in list(cookie.keys()):
                res = myDB.match('SELECT SendTo from users where UserID=?', (cookie['ll_uid'].value,))
                if res and res['SendTo']:
                    fsize = check_int(os.path.getsize(basefile), 0)
                    if fsize > 20000000:
                        msg = '%s is too large (%s) to email' % (os.path.split(basefile)[1], fsize)
                        logger.debug(msg)
                    else:
                        msg = "Email notifications are not configured"
                        logger.debug(msg)
                    return serve_template(templatename="choosetype.html", prefix="SendTo", title='Send file',
                                          pop_message=msg, pop_types='', bookid='', valid='')

        if name and name.endswith('zip'):
            return serve_file(basefile, mimeType(basefile), "attachment", name=name)
        return serve_file(basefile, mimeType(basefile), "attachment")
