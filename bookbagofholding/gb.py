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


# example
# https://www.googleapis.com/books/v1/volumes?q=+inauthor:george+martin+intitle:song+ice+fire

import re
import traceback

import requests

import bookbagofholding
from bookbagofholding import logger, database
from bookbagofholding.bookwork import getWorkPage, setStatus, thingLang
from bookbagofholding.images import getBookCover
from bookbagofholding.cache import gb_json_request, cache_img
from bookbagofholding.formatter import plural, today, replace_all, unaccented, unaccented_str, is_valid_isbn, \
    getList, cleanName, makeUnicode, md5_utf8
from fuzzywuzzy import fuzz
from urllib.parse import quote, quote_plus, urlencode

# Google returns at most 20 items per page whatever maxResults says, so these cap
# the number of api hits per query rather than the number of results
GB_PAGE_LIMIT = 15  # pages per query when fetching all books by an author
GB_SEARCH_PAGE_LIMIT = 5  # pages per query for a search


def normalise_author(name):
    """ Lowercase unaccented name with punctuation as spaces, so "J.K. Rowling" matches "J. K. Rowling" """
    name = re.sub(r'[^\w\s]', ' ', unaccented_str(name).lower())
    return ' '.join(name.split())


def author_matches(item, authorname):
    """ True if any of the authors of a GoogleBooks volume is a close match for authorname """
    wanted = normalise_author(authorname)
    for author in item.get('volumeInfo', {}).get('authors', []):
        if fuzz.ratio(normalise_author(author), wanted) >= 90:
            return True
    return False


class GoogleBooks:
    def __init__(self, name=None):
        self.name = makeUnicode(name)
        if not bookbagofholding.CONFIG['GB_API']:
            logger.warn('No GoogleBooks API key, check config')
        self.url = 'https://www.googleapis.com/books/v1/volumes?q='
        self.params = {
            'maxResults': 40,
            'printType': 'books',
        }

        if bookbagofholding.CONFIG['GB_API']:
            self.params['key'] = bookbagofholding.CONFIG['GB_API']

    def _get_items(self, query, useCache=True, max_pages=GB_PAGE_LIMIT):
        """ Return (items, api_hits) for up to max_pages of results for an already quoted query.
            startIndex steps by the number of items actually returned, as google may return
            fewer than maxResults per page
        """
        items = []
        api_hits = 0
        startindex = 0
        for _ in range(max_pages):
            self.params['startIndex'] = startindex
            URL = self.url + query + '&' + urlencode(self.params)
            try:
                jsonresults, in_cache = gb_json_request(URL, useCache=useCache)
            except Exception as err:
                if hasattr(err, 'reason'):
                    errmsg = err.reason
                else:
                    errmsg = str(err)
                logger.warn('Google Books API Error [%s]: Check your API key or wait a while' % errmsg)
                break
            if not jsonresults:
                break
            if not in_cache:
                api_hits += 1
            logger.debug('Searching url: ' + URL)
            page = jsonresults.get('items', [])
            if not page:
                break
            items.extend(page)
            startindex += len(page)
        return items, api_hits

    def get_author_items(self, authorname, useCache=True):
        """ Return (items, api_hits) for all GoogleBooks volumes by authorname.
            Google Books stopped answering inauthor: queries in late September 2026, so search
            for the name as plain text, both as a phrase and unquoted as neither finds everything,
            and keep only volumes with a matching author as plain text also finds books about them
        """
        name = unaccented_str(authorname)  # google doesnt like accents in author names
        results = []
        seen = set()
        api_hits = 0
        for query in (quote_plus('"%s"' % name), quote_plus(name)):
            items, hits = self._get_items(query, useCache=useCache)
            api_hits += hits
            for item in items:
                if item.get('id') not in seen and author_matches(item, authorname):
                    seen.add(item.get('id'))
                    results.append(item)
        return results, api_hits

    # noinspection PyBroadException
    def find_results(self, searchterm=None, queue=None):
        """ Search GoogleBooks for an isbn, or as plain text for anything else.
            Bookbag of Holding searches use <ll> to separate title from author in searchterm
            If this token isn't present, it's an isbn or searchterm as supplied by user
        """
        try:
            myDB = database.DBConnection()
            resultlist = []

            api_hits = 0

            ignored = 0
            total_count = 0
            no_author_count = 0
            title = ''
            authorname = ''

            if ' <ll> ' in searchterm:  # special token separates title from author
                title, authorname = searchterm.split(' <ll> ')

            fullterm = searchterm.replace(' <ll> ', ' ')
            logger.debug('Now searching Google Books API with searchterm: %s' % fullterm)

            # Google Books stopped answering inauthor: and intitle: queries in late September 2026
            # (they return no results), so search with plain text and let the fuzzy matching rank
            # the results. isbn: is broken too, but plain text isbn searches find nothing either,
            # so keep using it in case Google restores it.
            if is_valid_isbn(searchterm):
                api_value = 'isbn:'
                query = quote(api_value + searchterm)
            else:
                api_value = 'text'
                searchterm = fullterm
                if title and authorname:
                    title = title.split(' (')[0]  # without any series info
                    searchterm = '%s %s' % (title, authorname)
                searchterm = searchterm.replace('"', '').strip()  # no quotes
                query = quote_plus(searchterm)

            resultcount = 0
            items, api_hits = self._get_items(query, max_pages=GB_SEARCH_PAGE_LIMIT)
            if not items:
                logger.warn('Found no results for %s with value: %s' % (api_value, searchterm))
            try:
                for item in items:
                    total_count += 1

                    book = bookdict(item)
                    if not book['author']:
                        logger.debug('Skipped a result without authorfield.')
                        no_author_count += 1
                        continue

                    if not book['name']:
                        logger.debug('Skipped a result without title.')
                        continue

                    valid_langs = getList(bookbagofholding.CONFIG['IMP_PREFLANG'])
                    if "All" not in valid_langs:  # don't care about languages, accept all
                        try:
                            # skip if language is not in valid list -
                            booklang = book['lang']
                            if booklang not in valid_langs:
                                logger.debug(
                                    'Skipped %s with language %s' % (book['name'], booklang))
                                ignored += 1
                                continue
                        except KeyError:
                            ignored += 1
                            logger.debug('Skipped %s where no language is found' % book['name'])
                            continue

                    if authorname:
                        author_fuzz = fuzz.ratio(book['author'], authorname)
                    else:
                        author_fuzz = fuzz.ratio(book['author'], fullterm)

                    if title:
                        if title.endswith(')'):
                            title = title.rsplit('(', 1)[0]
                        book_fuzz = fuzz.token_set_ratio(book['name'], title)
                        # lose a point for each extra word in the fuzzy matches so we get the closest match
                        words = len(getList(book['name']))
                        words -= len(getList(title))
                        book_fuzz -= abs(words)
                    else:
                        book_fuzz = fuzz.token_set_ratio(book['name'], fullterm)

                    isbn_fuzz = 0
                    if is_valid_isbn(fullterm):
                        isbn_fuzz = 100

                    highest_fuzz = max((author_fuzz + book_fuzz) / 2, isbn_fuzz)

                    dic = {':': '.', '"': '', '\'': ''}
                    bookname = replace_all(book['name'], dic)

                    bookname = unaccented(bookname)
                    bookname = bookname.strip()  # strip whitespace

                    AuthorID = ''
                    if book['author']:
                        match = myDB.match(
                            'SELECT AuthorID FROM authors WHERE AuthorName=?', (book['author'],))
                        if match:
                            AuthorID = match['AuthorID']

                    resultlist.append({
                        'authorname': book['author'],
                        'authorid': AuthorID,
                        'bookid': item['id'],
                        'bookname': bookname,
                        'booksub': book['sub'],
                        'bookisbn': book['isbn'],
                        'bookpub': book['pub'],
                        'bookdate': book['date'],
                        'booklang': book['lang'],
                        'booklink': book['link'],
                        'bookrate': float(book['rate']),
                        'bookrate_count': book['rate_count'],
                        'bookimg': book['img'],
                        'bookpages': book['pages'],
                        'bookgenre': book['genre'],
                        'bookdesc': book['desc'],
                        'author_fuzz': author_fuzz,
                        'book_fuzz': book_fuzz,
                        'isbn_fuzz': isbn_fuzz,
                        'highest_fuzz': highest_fuzz,
                        'num_reviews': book['ratings']
                    })

                    resultcount += 1

            except KeyError:
                pass

            logger.debug("Returning %s result%s for (%s) with keyword: %s" %
                         (resultcount, plural(resultcount), api_value, searchterm))

            logger.debug("Found %s result%s" % (total_count, plural(total_count)))
            logger.debug("Removed %s unwanted language result%s" % (ignored, plural(ignored)))
            logger.debug("Removed %s book%s with no author" % (no_author_count, plural(no_author_count)))
            logger.debug('The Google Books API was hit %s time%s for searchterm: %s' %
                         (api_hits, plural(api_hits), fullterm))
            queue.put(resultlist)

        except Exception:
            logger.error('Unhandled exception in GB.find_results: %s' % traceback.format_exc())

    def get_author_books(self, authorid=None, authorname=None, bookstatus="Skipped",
                         audiostatus="Skipped", entrystatus='Active', refresh=False):
        # noinspection PyBroadException
        try:
            logger.debug('[%s] Now processing books with Google Books API' % authorname)
            api_hits = 0
            gr_lang_hits = 0
            lt_lang_hits = 0
            gb_lang_change = 0
            cache_hits = 0
            not_cached = 0
            removedResults = 0
            duplicates = 0
            ignored = 0
            added_count = 0
            updated_count = 0
            locked_count = 0
            book_ignore_count = 0
            total_count = 0

            valid_langs = getList(bookbagofholding.CONFIG['IMP_PREFLANG'])
            # Artist is loading
            myDB = database.DBConnection()
            controlValueDict = {"AuthorID": authorid}
            newValueDict = {"Status": "Loading"}
            myDB.upsert("authors", newValueDict, controlValueDict)

            try:
                items, api_hits = self.get_author_items(authorname, useCache=not refresh)
                if not items:
                    logger.warn('Found no results for %s' % authorname)
                else:
                    logger.debug('Found %s result%s for %s' % (len(items), plural(len(items)), authorname))

                for item in items:

                    total_count += 1
                    book = bookdict(item)
                    # skip if no author, no author is no book.
                    if not book['author']:
                        logger.debug('Skipped a result without authorfield.')
                        continue

                    isbnhead = ""
                    if len(book['isbn']) == 10:
                        isbnhead = book['isbn'][0:3]
                    elif len(book['isbn']) == 13:
                        isbnhead = book['isbn'][3:6]

                    booklang = book['lang']
                    # do we care about language?
                    if "All" not in valid_langs:
                        if book['isbn']:
                            # seems google lies to us, sometimes tells us books are in english when they are not
                            if booklang == "Unknown" or booklang == "en":
                                googlelang = booklang
                                match = False
                                lang = myDB.match('SELECT lang FROM languages where isbn=?', (isbnhead,))
                                if lang:
                                    booklang = lang['lang']
                                    cache_hits += 1
                                    logger.debug("Found cached language [%s] for [%s]" % (booklang, isbnhead))
                                    match = True
                                if not match:  # no match in cache, try lookup dict
                                    if isbnhead:
                                        if len(book['isbn']) == 13 and book['isbn'].startswith('979'):
                                            for lang in bookbagofholding.isbn_979_dict:
                                                if isbnhead.startswith(lang):
                                                    booklang = bookbagofholding.isbn_979_dict[lang]
                                                    logger.debug("ISBN979 returned %s for %s" %
                                                                 (booklang, isbnhead))
                                                    match = True
                                                    break
                                        elif (len(book['isbn']) == 10) or \
                                                (len(book['isbn']) == 13 and book['isbn'].startswith('978')):
                                            for lang in bookbagofholding.isbn_978_dict:
                                                if isbnhead.startswith(lang):
                                                    booklang = bookbagofholding.isbn_978_dict[lang]
                                                    logger.debug("ISBN979 returned %s for %s" %
                                                                 (booklang, isbnhead))
                                                    match = True
                                                    break
                                        if match:
                                            controlValueDict = {"isbn": isbnhead}
                                            newValueDict = {"lang": booklang}
                                            myDB.upsert("languages", newValueDict, controlValueDict)

                                if not match:
                                    booklang = thingLang(book['isbn'])
                                    lt_lang_hits += 1
                                    if booklang:
                                        match = True
                                        myDB.action('insert into languages values (?, ?)', (isbnhead, booklang))

                                if match:
                                    # We found a better language match
                                    if googlelang == "en" and booklang not in ["en-US", "en-GB", "eng"]:
                                        # these are all english, may need to expand this list
                                        logger.debug("%s Google thinks [%s], we think [%s]" %
                                                     (book['name'], googlelang, booklang))
                                        gb_lang_change += 1
                                else:  # No match anywhere, accept google language
                                    booklang = googlelang

                        # skip if language is in ignore list
                        if booklang not in valid_langs:
                            logger.debug('Skipped [%s] with language %s' % (book['name'], booklang))
                            ignored += 1
                            continue

                    ignorable = ['future', 'date', 'isbn']
                    if bookbagofholding.CONFIG['NO_LANG']:
                        ignorable.append('lang')
                    rejected = None
                    check_status = False
                    existing_book = None
                    bookname = book['name']
                    bookid = item['id']
                    if not bookname:
                        logger.debug('Rejecting bookid %s for %s, no bookname' % (bookid, authorname))
                        rejected = 'name', 'No bookname'
                    else:
                        bookname = replace_all(unaccented(bookname), {':': '.', '"': '', '\'': ''}).strip()
                        if re.match(r'[^\w-]', bookname):  # remove books with bad characters in title
                            logger.debug("[%s] removed book for bad characters" % bookname)
                            rejected = 'chars', 'Bad characters in bookname'

                    if not rejected and bookbagofholding.CONFIG['NO_FUTURE']:
                        # googlebooks sometimes gives yyyy, sometimes yyyy-mm, sometimes yyyy-mm-dd
                        if book['date'] > today()[:len(book['date'])]:
                            logger.debug('Rejecting %s, future publication date %s' % (bookname, book['date']))
                            rejected = 'future', 'Future publication date [%s]' % book['date']

                    if not rejected and bookbagofholding.CONFIG['NO_PUBDATE']:
                        if not book['date']:
                            logger.debug('Rejecting %s, no publication date' % bookname)
                            rejected = 'date', 'No publication date'

                    if not rejected and bookbagofholding.CONFIG['NO_ISBN']:
                        if not isbnhead:
                            logger.debug('Rejecting %s, no isbn' % bookname)
                            rejected = 'isbn', 'No ISBN'

                    if not rejected:
                        cmd = 'SELECT BookID FROM books,authors WHERE books.AuthorID = authors.AuthorID'
                        cmd += ' and BookName=? COLLATE NOCASE and AuthorName=? COLLATE NOCASE'
                        match = myDB.match(cmd, (bookname, authorname))
                        if match:
                            if match['BookID'] != bookid:  # we have a different book with this author/title already
                                logger.debug('Rejecting bookid %s for [%s][%s] already got %s' %
                                             (match['BookID'], authorname, bookname, bookid))
                                rejected = 'bookid', 'Got under different bookid %s' % bookid
                                duplicates += 1

                    cmd = 'SELECT AuthorName,BookName,AudioStatus,books.Status FROM books,authors'
                    cmd += ' WHERE authors.AuthorID = books.AuthorID AND BookID=?'
                    match = myDB.match(cmd, (bookid,))
                    if match:  # we have a book with this bookid already
                        if bookname != match['BookName'] or authorname != match['AuthorName']:
                            logger.debug('Rejecting bookid %s for [%s][%s] already got bookid for [%s][%s]' %
                                         (bookid, authorname, bookname, match['AuthorName'], match['BookName']))
                        else:
                            logger.debug('Rejecting bookid %s for [%s][%s] already got this book in database' %
                                         (bookid, authorname, bookname))
                            check_status = True
                        duplicates += 1
                        rejected = 'got', 'Already got this book in database'

                        # Make sure we don't reject books we have got
                        if match['Status'] in ['Open', 'Have'] or match['AudioStatus'] in ['Open', 'Have']:
                            rejected = None

                    if rejected and rejected[0] not in ignorable:
                        removedResults += 1
                    if check_status or rejected is None or (
                            bookbagofholding.CONFIG['IMP_IGNORE'] and rejected[0] in ignorable):  # dates, isbn

                        cmd = 'SELECT Status,AudioStatus,BookFile,AudioFile,Manual,BookAdded,BookName '
                        cmd += 'FROM books WHERE BookID=?'
                        existing = myDB.match(cmd, (bookid,))
                        if existing:
                            existing_book = True
                            book_status = existing['Status']
                            audio_status = existing['AudioStatus']
                            if bookbagofholding.CONFIG['FOUND_STATUS'] == 'Open':
                                if book_status == 'Have' and existing['BookFile']:
                                    book_status = 'Open'
                                if audio_status == 'Have' and existing['AudioFile']:
                                    audio_status = 'Open'
                            locked = existing['Manual']
                            added = existing['BookAdded']
                            if locked is None:
                                locked = False
                            elif locked.isdigit():
                                locked = bool(int(locked))
                        else:
                            book_status = bookstatus  # new_book status, or new_author status
                            audio_status = audiostatus
                            added = today()
                            locked = False

                        if rejected:
                            reason = rejected[1]
                            if rejected[0] in ignorable:
                                book_status = 'Ignored'
                                audio_status = 'Ignored'
                                book_ignore_count += 1
                        else:
                            reason = ''

                        if locked:
                            locked_count += 1
                        else:
                            controlValueDict = {"BookID": bookid}
                            newValueDict = {
                                "AuthorID": authorid,
                                "BookName": bookname,
                                "BookSub": book['sub'],
                                "BookDesc": book['desc'],
                                "BookIsbn": book['isbn'],
                                "BookPub": book['pub'],
                                "BookGenre": book['genre'],
                                "BookImg": book['img'],
                                "BookLink": book['link'],
                                "BookRate": float(book['rate']),
                                "BookPages": book['pages'],
                                "BookDate": book['date'],
                                "BookLang": booklang,
                                "Status": book_status,
                                "AudioStatus": audio_status,
                                "BookAdded": added,
                                "WorkID": '',
                                "ScanResult": reason
                            }

                            myDB.upsert("books", newValueDict, controlValueDict)
                            logger.debug("Book found: " + bookname + " " + book['date'])
                            if 'nocover' in book['img'] or 'nophoto' in book['img']:
                                # try to get a cover from another source
                                workcover, source = getBookCover(bookid)
                                if workcover:
                                    logger.debug('Updated cover for %s using %s' % (bookname, source))
                                    controlValueDict = {"BookID": bookid}
                                    newValueDict = {"BookImg": workcover}
                                    myDB.upsert("books", newValueDict, controlValueDict)

                            elif book['img'] and book['img'].startswith('http'):
                                link, success, _ = cache_img("book", bookid, book['img'], refresh=refresh)
                                if success:
                                    controlValueDict = {"BookID": bookid}
                                    newValueDict = {"BookImg": link}
                                    myDB.upsert("books", newValueDict, controlValueDict)
                                else:
                                    logger.debug('Failed to cache image for %s' % book['img'])

                            new_status = setStatus(bookid, bookstatus)

                            if not new_status == book_status:
                                book_status = new_status

                            worklink = getWorkPage(bookid)
                            if worklink:
                                controlValueDict = {"BookID": bookid}
                                newValueDict = {"WorkPage": worklink}
                                myDB.upsert("books", newValueDict, controlValueDict)

                            if not existing_book:
                                logger.debug("[%s] Added book: %s [%s] status %s" %
                                             (authorname, bookname, booklang, book_status))
                                added_count += 1
                            else:
                                logger.debug("[%s] Updated book: %s [%s] status %s" %
                                             (authorname, bookname, booklang, book_status))
                                updated_count += 1
            except KeyError:
                pass

            logger.debug('[%s] The Google Books API was hit %s time%s to populate book list' %
                         (authorname, api_hits, plural(api_hits)))
            cmd = 'SELECT BookName, BookLink, BookDate, BookImg, BookID from books WHERE AuthorID=?'
            cmd += ' AND Status != "Ignored" order by BookDate DESC'
            lastbook = myDB.match(cmd, (authorid,))

            if lastbook:  # maybe there are no books [remaining] for this author
                lastbookname = lastbook['BookName']
                lastbooklink = lastbook['BookLink']
                lastbookdate = lastbook['BookDate']
                lastbookid = lastbook['BookID']
                lastbookimg = lastbook['BookImg']
            else:
                lastbookname = ""
                lastbooklink = ""
                lastbookdate = ""
                lastbookid = ""
                lastbookimg = ""

            controlValueDict = {"AuthorID": authorid}
            newValueDict = {
                "Status": entrystatus,
                "LastBook": lastbookname,
                "LastLink": lastbooklink,
                "LastDate": lastbookdate,
                "LastBookID": lastbookid,
                "LastBookImg": lastbookimg
            }

            myDB.upsert("authors", newValueDict, controlValueDict)
            resultcount = added_count + updated_count
            logger.debug("Found %s total book%s for author" % (total_count, plural(total_count)))
            logger.debug("Found %s locked book%s" % (locked_count, plural(locked_count)))
            logger.debug("Removed %s unwanted language result%s" % (ignored, plural(ignored)))
            logger.debug("Removed %s incorrect/incomplete result%s" % (removedResults, plural(removedResults)))
            logger.debug("Removed %s duplicate result%s" % (duplicates, plural(duplicates)))
            logger.debug("Ignored %s book%s" % (book_ignore_count, plural(book_ignore_count)))
            logger.debug("Imported/Updated %s book%s for author" % (resultcount, plural(resultcount)))

            myDB.action('insert into stats values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        (authorname, api_hits, gr_lang_hits, lt_lang_hits, gb_lang_change,
                         cache_hits, ignored, removedResults, not_cached, duplicates))

            if refresh:
                logger.info("[%s] Book processing complete: Added %s book%s / Updated %s book%s" %
                            (authorname, added_count, plural(added_count), updated_count, plural(updated_count)))
            else:
                logger.info("[%s] Book processing complete: Added %s book%s to the database" %
                            (authorname, added_count, plural(added_count)))

        except Exception:
            logger.error('Unhandled exception in GB.get_author_books: %s' % traceback.format_exc())

    def find_book(self, bookid=None, bookstatus=None, audiostatus=None):
        myDB = database.DBConnection()
        if not bookbagofholding.CONFIG['GB_API']:
            logger.warn('No GoogleBooks API key, check config')
        URL = 'https://www.googleapis.com/books/v1/volumes/' + \
              str(bookid) + "?key=" + bookbagofholding.CONFIG['GB_API']
        jsonresults, in_cache = gb_json_request(URL)

        if not jsonresults:
            logger.debug('No results found for %s' % bookid)
            return

        if not bookstatus:
            bookstatus = bookbagofholding.CONFIG['NEWBOOK_STATUS']
        if not audiostatus:
            audiostatus = bookbagofholding.CONFIG['NEWAUDIO_STATUS']

        book = bookdict(jsonresults)
        dic = {':': '.', '"': '', '\'': ''}
        bookname = replace_all(book['name'], dic)

        bookname = unaccented(bookname)
        bookname = bookname.strip()  # strip whitespace

        if not book['author']:
            logger.debug('Book %s does not contain author field, skipping' % bookname)
            return
        # warn if language is in ignore list, but user said they wanted this book
        valid_langs = getList(bookbagofholding.CONFIG['IMP_PREFLANG'])
        if book['lang'] not in valid_langs and 'All' not in valid_langs:
            logger.debug('Book %s googlebooks language does not match preference, %s' % (bookname, book['lang']))

        if bookbagofholding.CONFIG['NO_PUBDATE']:
            if not book['date'] or book['date'] == '0000':
                logger.warn('Book %s Publication date does not match preference, %s' % (bookname, book['date']))

        if bookbagofholding.CONFIG['NO_FUTURE']:
            if book['date'] > today()[:4]:
                logger.warn('Book %s Future publication date does not match preference, %s' % (bookname, book['date']))

        authorname = book['author']
        # Check if author exists in database by name
        match = myDB.match('SELECT AuthorID from authors WHERE AuthorName=?', (authorname,))
        if match:
            AuthorID = match['AuthorID']
        else:
            # No author found, create one
            AuthorID = "GB:" + md5_utf8(authorname)
            match = myDB.match('SELECT AuthorID from authors WHERE AuthorID=?', (AuthorID,))
            if not match:
                # User hit "add book" button from a search or a wishlist import
                newauthor_status = 'Active'
                if bookbagofholding.CONFIG['NEWAUTHOR_STATUS'] in ['Skipped', 'Ignored']:
                    newauthor_status = 'Paused'
                controlValueDict = {"AuthorID": AuthorID}
                newValueDict = {
                    "AuthorName": authorname,
                    "AuthorImg": "images/nophoto.png",
                    "DateAdded": today(),
                    "Status": newauthor_status
                }
                myDB.upsert("authors", newValueDict, controlValueDict)
                if bookbagofholding.CONFIG['NEWAUTHOR_BOOKS']:
                    self.get_author_books(AuthorID, authorname, entrystatus=bookbagofholding.CONFIG['NEWAUTHOR_STATUS'])

        controlValueDict = {"BookID": bookid}
        newValueDict = {
            "AuthorID": AuthorID,
            "BookName": bookname,
            "BookSub": book['sub'],
            "BookDesc": book['desc'],
            "BookIsbn": book['isbn'],
            "BookPub": book['pub'],
            "BookGenre": book['genre'],
            "BookImg": book['img'],
            "BookLink": book['link'],
            "BookRate": float(book['rate']),
            "BookPages": book['pages'],
            "BookDate": book['date'],
            "BookLang": book['lang'],
            "Status": bookstatus,
            "AudioStatus": audiostatus,
            "BookAdded": today()
        }

        myDB.upsert("books", newValueDict, controlValueDict)
        logger.info("%s by %s added to the books database, %s/%s" % (bookname, authorname, bookstatus, audiostatus))

        if 'nocover' in book['img'] or 'nophoto' in book['img']:
            # try to get a cover from another source
            workcover, source = getBookCover(bookid)
            if workcover:
                logger.debug('Updated cover for %s using %s' % (bookname, source))
                controlValueDict = {"BookID": bookid}
                newValueDict = {"BookImg": workcover}
                myDB.upsert("books", newValueDict, controlValueDict)

            elif book['img'] and book['img'].startswith('http'):
                link, success, _ = cache_img("book", bookid, book['img'])
                if success:
                    controlValueDict = {"BookID": bookid}
                    newValueDict = {"BookImg": link}
                    myDB.upsert("books", newValueDict, controlValueDict)
                else:
                    logger.debug('Failed to cache image for %s' % book['img'])

        worklink = getWorkPage(bookid)
        if worklink:
            controlValueDict = {"BookID": bookid}
            newValueDict = {"WorkPage": worklink}
            myDB.upsert("books", newValueDict, controlValueDict)


def bookdict(item):
    """ Return all the book info we need as a dictionary or default value if no key """
    mydict = {}
    for val, idx1, idx2, default in [
        ('author', 'authors', 0, ''),
        ('name', 'title', None, ''),
        ('lang', 'language', None, ''),
        ('pub', 'publisher', None, ''),
        ('sub', 'subtitle', None, ''),
        ('date', 'publishedDate', None, '0000'),
        ('rate', 'averageRating', None, 0),
        ('rate_count', 'ratingsCount', None, 0),
        ('pages', 'pageCount', None, 0),
        ('desc', 'description', None, 'Not available'),
        ('link', 'canonicalVolumeLink', None, ''),
        ('img', 'imageLinks', 'thumbnail', 'images/nocover.png'),
        ('genre', 'categories', 0, ''),
        ('ratings', 'ratingsCount', None, 0)
    ]:
        try:
            if idx2 is None:
                mydict[val] = item['volumeInfo'][idx1]
            else:
                mydict[val] = item['volumeInfo'][idx1][idx2]
        except KeyError:
            mydict[val] = default

    try:
        if item['volumeInfo']['industryIdentifiers'][0]['type'] in ['ISBN_10', 'ISBN_13']:
            mydict['isbn'] = item['volumeInfo']['industryIdentifiers'][0]['identifier']
        else:
            mydict['isbn'] = ""
    except KeyError:
        mydict['isbn'] = ""

    # googlebooks has a few series naming systems in the authors books page...
    # title or subtitle (seriesname num) eg (Discworld 24)
    # title or subtitle (seriesname #num) eg (Discworld #24)
    # title or subtitle (seriesname Series num)  eg (discworld Series 24)
    # subtitle Book num of seriesname  eg Book 24 of Discworld
    # There may be others...
    #
    try:

        seriesNum, series = mydict['sub'].split('Book ')[1].split(' of ')
    except (IndexError, ValueError):
        series = ""
        seriesNum = ""

    if not series:
        for item in [mydict['name'], mydict['sub']]:
            if ' Series ' in item:
                try:
                    series, seriesNum = item.split('(')[1].split(' Series ')
                    seriesNum = seriesNum.rstrip(')').lstrip('#')
                except (IndexError, ValueError):
                    series = ""
                    seriesNum = ""
            if not series and '#' in item:
                try:
                    series, seriesNum = item.rsplit('#', 1)
                    series = series.split('(')[1].strip()
                    seriesNum = seriesNum.rstrip(')')
                except (IndexError, ValueError):
                    series = ""
                    seriesNum = ""
            if not series and ' ' in item:
                try:
                    series, seriesNum = item.rsplit(' ', 1)
                    series = series.split('(')[1].strip()
                    seriesNum = seriesNum.rstrip(')')
                    # has to be unicode for isnumeric()
                    if not (u"%s" % seriesNum).isnumeric():
                        series = ""
                        seriesNum = ""
                except (IndexError, ValueError):
                    series = ""
                    seriesNum = ""
            if series and seriesNum:
                break

    mydict['series'] = series
    mydict['seriesNum'] = seriesNum

    return mydict
