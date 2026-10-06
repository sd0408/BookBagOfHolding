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
Unit tests for bookbagofholding.gb module.

Google Books stopped answering field qualified queries (inauthor:, intitle:) in
late September 2026, so these cover the plain text replacements:
- normalise_author / author_matches
- GoogleBooks._get_items paging
- GoogleBooks.get_author_items
- GoogleBooks.find_results query building
- GoogleBooks.get_author_books using get_author_items
"""

import queue
from urllib.parse import unquote_plus, urlparse, parse_qs

import pytest
from unittest.mock import patch, MagicMock

import bookbagofholding
from bookbagofholding import gb


def volume(volid, authors, title='A Book', lang='en'):
    return {'id': volid, 'volumeInfo': {'authors': authors, 'title': title, 'language': lang}}


@pytest.fixture
def gb_config():
    saved = dict(bookbagofholding.CONFIG)
    bookbagofholding.CONFIG['GB_API'] = 'testkey'
    bookbagofholding.CONFIG['IMP_PREFLANG'] = 'All'
    yield
    bookbagofholding.CONFIG.clear()
    bookbagofholding.CONFIG.update(saved)


def query_of(url):
    """ The q= value of a GoogleBooks url, unquoted """
    return unquote_plus(url.split('?q=', 1)[1].split('&', 1)[0])


def start_of(url):
    return int(parse_qs(urlparse(url).query)['startIndex'][0])


class TestAuthorMatching:
    def test_normalise_author_punctuation_and_accents(self):
        assert gb.normalise_author('J.K. Rowling') == gb.normalise_author('J. K. Rowling') == 'j k rowling'
        assert gb.normalise_author('Gabriel García Márquez') == 'gabriel garcia marquez'

    def test_author_matches_any_author(self):
        item = volume('x', ['Someone Else', 'Brandon Sanderson'])
        assert gb.author_matches(item, 'Brandon Sanderson')

    def test_author_matches_rejects_other_authors(self):
        # a plain text search for the name also finds books about the author
        item = volume('x', ['Some Critic'], title='The Worlds of Brandon Sanderson')
        assert not gb.author_matches(item, 'Brandon Sanderson')

    def test_author_matches_no_authors(self):
        assert not gb.author_matches({'id': 'x', 'volumeInfo': {}}, 'Brandon Sanderson')
        assert not gb.author_matches({'id': 'x'}, 'Brandon Sanderson')


class TestGetItems:
    def test_steps_by_items_returned_until_empty_page(self, gb_config):
        # google returns 20 items a page even though we ask for 40
        pages = {0: [volume('a%s' % i, ['X']) for i in range(20)],
                 20: [volume('b%s' % i, ['X']) for i in range(20)],
                 40: [volume('c%s' % i, ['X']) for i in range(5)],
                 45: []}
        calls = []

        def fake(url, useCache=True):
            calls.append(url)
            return {'totalItems': 300, 'items': pages[start_of(url)]}, False

        with patch.object(gb, 'gb_json_request', side_effect=fake):
            items, hits = gb.GoogleBooks()._get_items('foo')

        assert len(items) == 45
        assert [start_of(u) for u in calls] == [0, 20, 40, 45]
        assert hits == 4

    def test_respects_max_pages(self, gb_config):
        page = [volume('a', ['X'])] * 20
        with patch.object(gb, 'gb_json_request', return_value=({'items': page}, True)) as req:
            items, hits = gb.GoogleBooks()._get_items('foo', max_pages=3)
        assert req.call_count == 3
        assert len(items) == 60
        assert hits == 0  # all from cache

    def test_no_items_key(self, gb_config):
        with patch.object(gb, 'gb_json_request', return_value=({'kind': 'books#volumes', 'totalItems': 0}, False)):
            assert gb.GoogleBooks()._get_items('foo') == ([], 1)

    def test_request_failure(self, gb_config):
        with patch.object(gb, 'gb_json_request', return_value=(None, False)):
            assert gb.GoogleBooks()._get_items('foo') == ([], 0)

    def test_request_exception(self, gb_config):
        with patch.object(gb, 'gb_json_request', side_effect=OSError('boom')):
            assert gb.GoogleBooks()._get_items('foo') == ([], 0)

    def test_passes_use_cache(self, gb_config):
        with patch.object(gb, 'gb_json_request', return_value=(None, False)) as req:
            gb.GoogleBooks()._get_items('foo', useCache=False)
        assert req.call_args[1]['useCache'] is False


class TestGetAuthorItems:
    def test_quoted_and_unquoted_merged_filtered_and_deduped(self, gb_config):
        results = {
            '"Garth Nix"': [volume('1', ['Garth Nix']), volume('2', ['A Critic'])],
            'Garth Nix': [volume('1', ['Garth Nix']), volume('3', ['Garth Nix', 'Sean Williams'])],
        }
        queries = []

        def fake(self, query, useCache=True, max_pages=gb.GB_PAGE_LIMIT):
            queries.append(unquote_plus(query))
            return results[unquote_plus(query)], 2

        with patch.object(gb.GoogleBooks, '_get_items', fake):
            items, hits = gb.GoogleBooks().get_author_items('Garth Nix')

        assert queries == ['"Garth Nix"', 'Garth Nix']
        assert [i['id'] for i in items] == ['1', '3']
        assert hits == 4

    def test_never_uses_inauthor(self, gb_config):
        with patch.object(gb, 'gb_json_request', return_value=(None, False)) as req:
            gb.GoogleBooks().get_author_items('Garth Nix')
        assert req.call_count == 2
        for call in req.call_args_list:
            assert 'inauthor' not in unquote_plus(call[0][0])

    def test_accents_removed_from_query(self, gb_config):
        with patch.object(gb.GoogleBooks, '_get_items', return_value=([], 0)) as get:
            gb.GoogleBooks().get_author_items('Gabriel García Márquez')
        assert unquote_plus(get.call_args_list[1][0][0]) == 'Gabriel Garcia Marquez'


class TestFindResults:
    def run(self, searchterm, items):
        q = queue.Queue()
        with patch.object(gb.GoogleBooks, '_get_items', return_value=(items, 1)) as get, \
                patch.object(gb.database, 'DBConnection', return_value=MagicMock(match=MagicMock(return_value=None))):
            gb.GoogleBooks().find_results(searchterm, q)
        return get, q.get_nowait()

    def test_plain_search_term(self, gb_config):
        get, results = self.run('Ariel Lawhon', [volume('1', ['Ariel Lawhon'], 'I Was Anastasia')])
        assert unquote_plus(get.call_args[0][0]) == 'Ariel Lawhon'
        assert get.call_args[1]['max_pages'] == gb.GB_SEARCH_PAGE_LIMIT
        assert results[0]['authorname'] == 'Ariel Lawhon'
        assert results[0]['bookname'] == 'I Was Anastasia'

    def test_title_and_author_searched_together_without_series(self, gb_config):
        get, results = self.run('Lirael (Old Kingdom 3) <ll> Garth Nix', [volume('1', ['Garth Nix'], 'Lirael')])
        assert unquote_plus(get.call_args[0][0]) == 'Lirael Garth Nix'
        assert results[0]['highest_fuzz'] == 100

    def test_ranks_by_fuzz(self, gb_config):
        items = [volume('1', ['Brian Herbert'], 'Dune: House Atreides'), volume('2', ['Frank Herbert'], 'Dune')]
        get, results = self.run('Dune <ll> Frank Herbert', items)
        best = max(results, key=lambda r: r['highest_fuzz'])
        assert best['bookid'] == '2'

    def test_double_quotes_removed(self, gb_config):
        get, _ = self.run('The "Best" Book', [])
        assert unquote_plus(get.call_args[0][0]) == 'The Best Book'

    def test_isbn_still_uses_isbn_qualifier(self, gb_config):
        get, _ = self.run('9780765356147', [])
        assert unquote_plus(get.call_args[0][0]) == 'isbn:9780765356147'

    def test_no_results(self, gb_config):
        _, results = self.run('nothing', [])
        assert results == []


class TestGetAuthorBooks:
    def test_uses_get_author_items_and_processes_each(self, gb_config):
        db = MagicMock()
        db.match.return_value = None
        items = [volume('1', ['Garth Nix']), volume('2', ['Garth Nix'])]
        with patch.object(gb.GoogleBooks, 'get_author_items', return_value=(items, 2)) as get, \
                patch.object(gb.database, 'DBConnection', return_value=db), \
                patch.object(gb, 'bookdict', return_value={'author': ''}) as bookdict:
            gb.GoogleBooks().get_author_books('auth1', 'Garth Nix', refresh=True)

        get.assert_called_once_with('Garth Nix', useCache=False)
        assert bookdict.call_count == 2
        db.upsert.assert_any_call('authors', {'Status': 'Loading'}, {'AuthorID': 'auth1'})

    def test_no_items_still_finishes_author(self, gb_config):
        db = MagicMock()
        db.match.return_value = None
        with patch.object(gb.GoogleBooks, 'get_author_items', return_value=([], 2)) as get, \
                patch.object(gb.database, 'DBConnection', return_value=db):
            gb.GoogleBooks().get_author_books('auth1', 'Garth Nix', entrystatus='Active')

        get.assert_called_once_with('Garth Nix', useCache=True)
        final = db.upsert.call_args_list[-1][0]
        assert final[0] == 'authors' and final[1]['Status'] == 'Active'
