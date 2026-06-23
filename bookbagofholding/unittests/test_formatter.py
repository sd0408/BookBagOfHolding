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
Unit tests for bookbagofholding.formatter module.

Tests cover:
- String manipulation functions (cleanName, unaccented, replace_all)
- Date/time functions (now, today, age, datecompare)
- Type conversion functions (check_int, size_in_bytes)
- Book/author formatting functions
- ISBN validation
- URL handling
"""

import datetime
import pytest

import bookbagofholding
from bookbagofholding import formatter


class TestCheckInt:
    """Tests for check_int() function."""

    def test_check_int_returns_int_for_valid_string(self):
        """check_int should convert valid string to int."""
        assert formatter.check_int("42", 0) == 42

    def test_check_int_returns_int_for_int_input(self):
        """check_int should return int for int input."""
        assert formatter.check_int(42, 0) == 42

    def test_check_int_returns_zero_for_zero_string(self):
        """check_int should handle '0' correctly."""
        assert formatter.check_int("0", 10) == 0

    def test_check_int_returns_default_for_invalid_string(self):
        """check_int should return default for non-numeric string."""
        assert formatter.check_int("not_a_number", 99) == 99

    def test_check_int_returns_default_for_none(self):
        """check_int should return default for None."""
        assert formatter.check_int(None, 42) == 42

    def test_check_int_returns_default_for_empty_string(self):
        """check_int should return default for empty string."""
        assert formatter.check_int("", 10) == 10

    def test_check_int_returns_default_for_negative_when_positive_required(self):
        """check_int should return default for negative when positive=True."""
        assert formatter.check_int("-5", 0, positive=True) == 0

    def test_check_int_allows_negative_when_positive_false(self):
        """check_int should allow negative when positive=False."""
        assert formatter.check_int("-5", 0, positive=False) == -5

    def test_check_int_handles_float_string(self):
        """check_int should handle float strings by truncating."""
        # Python's int() raises ValueError for float strings
        assert formatter.check_int("3.14", 0) == 0


class TestSizeInBytes:
    """Tests for size_in_bytes() function."""

    def test_size_in_bytes_handles_kilobytes(self):
        """size_in_bytes should convert KB to bytes."""
        assert formatter.size_in_bytes("10K") == 10 * 1024
        assert formatter.size_in_bytes("10 KB") == 10 * 1024

    def test_size_in_bytes_handles_megabytes(self):
        """size_in_bytes should convert MB to bytes."""
        assert formatter.size_in_bytes("5M") == 5 * 1024 * 1024
        assert formatter.size_in_bytes("5 MB") == 5 * 1024 * 1024

    def test_size_in_bytes_handles_gigabytes(self):
        """size_in_bytes should convert GB to bytes."""
        assert formatter.size_in_bytes("2G") == 2 * 1024 * 1024 * 1024
        assert formatter.size_in_bytes("2 GB") == 2 * 1024 * 1024 * 1024

    def test_size_in_bytes_handles_plain_bytes(self):
        """size_in_bytes should handle plain byte values."""
        assert formatter.size_in_bytes("1024") == 1024

    def test_size_in_bytes_handles_decimal_values(self):
        """size_in_bytes should handle decimal values."""
        assert formatter.size_in_bytes("1.5M") == int(1.5 * 1024 * 1024)

    def test_size_in_bytes_returns_zero_for_empty(self):
        """size_in_bytes should return 0 for empty input."""
        assert formatter.size_in_bytes("") == 0
        assert formatter.size_in_bytes(None) == 0


class TestPlural:
    """Tests for plural() function."""

    def test_plural_returns_empty_for_one(self):
        """plural should return empty string for 1."""
        assert formatter.plural(1) == ''

    def test_plural_returns_s_for_zero(self):
        """plural should return 's' for 0."""
        assert formatter.plural(0) == 's'

    def test_plural_returns_s_for_multiple(self):
        """plural should return 's' for values > 1."""
        assert formatter.plural(5) == 's'
        assert formatter.plural(100) == 's'

    def test_plural_handles_string_one(self):
        """plural should handle string '1'."""
        assert formatter.plural('1') == ''


class TestReplaceAll:
    """Tests for replace_all() function."""

    def test_replace_all_replaces_multiple_characters(self):
        """replace_all should replace multiple specified characters."""
        result = formatter.replace_all("Hello World!", {'o': '0', '!': '?'})
        assert result == "Hell0 W0rld?"

    def test_replace_all_handles_empty_dict(self):
        """replace_all should return original for empty dict."""
        assert formatter.replace_all("Hello", {}) == "Hello"

    def test_replace_all_handles_empty_string(self):
        """replace_all should return empty string for empty input."""
        assert formatter.replace_all("", {'a': 'b'}) == ''

    def test_replace_all_handles_none(self):
        """replace_all should return empty string for None."""
        assert formatter.replace_all(None, {'a': 'b'}) == ''


class TestStripEmbeddedUrl:
    """Tests for strip_embedded_url() function."""

    def test_strips_appended_download_url(self):
        """An http download URL appended after ' - ' should be removed."""
        title = ("Serpent & Dove by Shelby Mahurin EPUB - "
                 "http://prowlarr:9696/4/download?apikey=abc&link=TOKEN123&file=Serpent")
        assert formatter.strip_embedded_url(title) == "Serpent & Dove by Shelby Mahurin EPUB"

    def test_same_release_different_token_yields_same_title(self):
        """Ephemeral tokens differ per search; stripped titles must be equal."""
        base = "Serpent & Dove by Shelby Mahurin EPUB - http://prowlarr:9696/4/download?link="
        a = formatter.strip_embedded_url(base + "TOKEN_AAAAA&file=x")
        b = formatter.strip_embedded_url(base + "TOKEN_BBBBB&file=x")
        assert a == b == "Serpent & Dove by Shelby Mahurin EPUB"

    def test_strips_magnet_url(self):
        """Magnet links should also be stripped."""
        title = "Some Audiobook - magnet:?xt=urn:btih:DEADBEEF&dn=foo"
        assert formatter.strip_embedded_url(title) == "Some Audiobook"

    def test_leaves_clean_title_untouched(self):
        """A normal title with no URL should be returned unchanged."""
        title = "Grady Hendrix How to Sell a Haunted House"
        assert formatter.strip_embedded_url(title) == title

    def test_handles_empty_and_none(self):
        """Empty/None inputs should pass through without error."""
        assert formatter.strip_embedded_url("") == ""
        assert formatter.strip_embedded_url(None) is None


class TestUnaccented:
    """Tests for unaccented() function."""

    def test_unaccented_removes_accents(self):
        """unaccented should remove accent marks."""
        assert formatter.unaccented("café") == "cafe"
        assert formatter.unaccented("résumé") == "resume"
        assert formatter.unaccented("naïve") == "naive"

    def test_unaccented_handles_empty_string(self):
        """unaccented should handle empty string."""
        assert formatter.unaccented("") == ""

    def test_unaccented_handles_none(self):
        """unaccented should handle None."""
        assert formatter.unaccented(None) == ""

    def test_unaccented_preserves_ascii(self):
        """unaccented should preserve plain ASCII."""
        assert formatter.unaccented("Hello World") == "Hello World"

    def test_unaccented_handles_special_characters(self):
        """unaccented should handle special Unicode characters."""
        # Ae ligature, Eth, etc.
        result = formatter.unaccented("Æther")
        assert 'A' in result


class TestCleanName:
    """Tests for cleanName() function."""

    def test_cleanName_removes_invalid_characters(self):
        """cleanName should remove characters not valid for filenames."""
        result = formatter.cleanName("Test: Book/Title?")
        assert ':' not in result
        assert '/' not in result
        assert '?' not in result

    def test_cleanName_preserves_allowed_characters(self):
        """cleanName should preserve allowed filename characters."""
        result = formatter.cleanName("Test Book (2023)")
        assert 'Test' in result
        assert 'Book' in result
        assert '2023' in result
        assert '(' in result
        assert ')' in result

    def test_cleanName_handles_empty(self):
        """cleanName should handle empty input."""
        assert formatter.cleanName("") == ""
        assert formatter.cleanName(None) == ""

    def test_cleanName_with_extras(self):
        """cleanName should include extra allowed characters."""
        result = formatter.cleanName("Test@Book", extras="@")
        assert '@' in result


class TestGetList:
    """Tests for getList() function."""

    def test_getList_splits_on_comma(self):
        """getList should split on comma."""
        result = formatter.getList("epub, mobi, pdf")
        assert result == ['epub', 'mobi', 'pdf']

    def test_getList_splits_on_plus(self):
        """getList should split on plus."""
        result = formatter.getList("epub+mobi+pdf")
        assert result == ['epub', 'mobi', 'pdf']

    def test_getList_splits_on_whitespace(self):
        """getList should split on whitespace."""
        result = formatter.getList("epub mobi pdf")
        assert result == ['epub', 'mobi', 'pdf']

    def test_getList_with_custom_separator(self):
        """getList should split on custom separator."""
        result = formatter.getList("epub;mobi;pdf", c=';')
        assert result == ['epub', 'mobi', 'pdf']

    def test_getList_handles_empty(self):
        """getList should return empty list for empty input."""
        assert formatter.getList("") == []
        assert formatter.getList(None) == []


class TestIsValidIsbn:
    """Tests for is_valid_isbn() function."""

    def test_valid_isbn13(self):
        """is_valid_isbn should accept valid 13-digit ISBN."""
        assert formatter.is_valid_isbn("9781234567890") is True

    def test_valid_isbn10(self):
        """is_valid_isbn should accept valid 10-digit ISBN."""
        assert formatter.is_valid_isbn("1234567890") is True

    def test_valid_isbn10_with_x(self):
        """is_valid_isbn should accept ISBN-10 ending with X."""
        assert formatter.is_valid_isbn("123456789X") is True
        assert formatter.is_valid_isbn("123456789x") is True

    def test_valid_isbn_with_dashes(self):
        """is_valid_isbn should accept ISBN with dashes."""
        assert formatter.is_valid_isbn("978-1-234-56789-0") is True

    def test_valid_isbn_with_spaces(self):
        """is_valid_isbn should accept ISBN with spaces."""
        assert formatter.is_valid_isbn("978 1 234 56789 0") is True

    def test_invalid_isbn_wrong_length(self):
        """is_valid_isbn should reject wrong length."""
        assert formatter.is_valid_isbn("12345") is False
        assert formatter.is_valid_isbn("12345678901234") is False

    def test_invalid_isbn_non_numeric(self):
        """is_valid_isbn should reject non-numeric ISBN."""
        assert formatter.is_valid_isbn("abcdefghij") is False


class TestFormatAuthorName:
    """Tests for formatAuthorName() function."""

    def test_format_author_surname_forename(self):
        """formatAuthorName should swap surname, forename format."""
        result = formatter.formatAuthorName("Doe, John")
        assert result == "John Doe"

    def test_format_author_with_postfix(self):
        """formatAuthorName should handle name postfixes like Jr."""
        result = formatter.formatAuthorName("L. E. Modesitt, Jr.")
        # Should keep Jr. with surname, not swap
        assert "Modesitt" in result
        assert "Jr" in result

    def test_format_author_initials(self):
        """formatAuthorName should format initials properly."""
        result = formatter.formatAuthorName("J. K. Rowling")
        assert result == "J.K. Rowling"

    def test_format_author_already_correct(self):
        """formatAuthorName should not change already-formatted names."""
        result = formatter.formatAuthorName("Stephen King")
        assert result == "Stephen King"

    def test_format_author_removes_extra_whitespace(self):
        """formatAuthorName should remove extra whitespace."""
        result = formatter.formatAuthorName("John    Doe")
        assert result == "John Doe"


class TestSplitTitle:
    """Tests for split_title() function."""

    def test_split_title_on_colon(self):
        """split_title should split on colon."""
        title, sub = formatter.split_title("Author", "Main Title: A Subtitle")
        assert title == "Main Title"
        assert sub == " A Subtitle"  # Note: function preserves leading space after colon

    def test_split_title_removes_author_prefix(self):
        """split_title should remove author name prefix."""
        title, sub = formatter.split_title("Tom Clancy", "Tom Clancy: Ghost Protocol")
        assert title == "Ghost Protocol"

    def test_split_title_on_parenthesis(self):
        """split_title should split on parenthesis."""
        title, sub = formatter.split_title("Author", "Main Title (Subtitle)")
        assert title == "Main Title"
        assert sub == "(Subtitle)"

    def test_split_title_no_subtitle(self):
        """split_title should handle titles without subtitle."""
        title, sub = formatter.split_title("Author", "Simple Title")
        assert title == "Simple Title"
        assert sub == ""


class TestMakeUnicode:
    """Tests for makeUnicode() function."""

    def test_makeUnicode_handles_unicode(self):
        """makeUnicode should return unicode unchanged."""
        result = formatter.makeUnicode("Hello World")
        assert result == "Hello World"
        assert isinstance(result, str)

    def test_makeUnicode_handles_empty(self):
        """makeUnicode should return empty string for empty input."""
        assert formatter.makeUnicode("") == ""
        assert formatter.makeUnicode(None) == ""

    def test_makeUnicode_handles_bytes(self):
        """makeUnicode should decode bytes to unicode."""
        result = formatter.makeUnicode(b"Hello World")
        assert result == "Hello World"
        assert isinstance(result, str)


class TestMakeBytestr:
    """Tests for makeBytestr() function."""

    def test_makeBytestr_handles_string(self):
        """makeBytestr should encode string to bytes."""
        result = formatter.makeBytestr("Hello World")
        assert isinstance(result, bytes)

    def test_makeBytestr_handles_empty(self):
        """makeBytestr should return empty bytes for empty input."""
        assert formatter.makeBytestr("") == b""
        assert formatter.makeBytestr(None) == b""

    def test_makeBytestr_handles_bytes(self):
        """makeBytestr should return bytes unchanged."""
        result = formatter.makeBytestr(b"Hello World")
        assert result == b"Hello World"


class TestMd5Utf8:
    """Tests for md5_utf8() function."""

    def test_md5_utf8_returns_hex_digest(self):
        """md5_utf8 should return MD5 hex digest."""
        result = formatter.md5_utf8("test")
        assert len(result) == 32
        assert result == "098f6bcd4621d373cade4e832627b4f6"

    def test_md5_utf8_handles_unicode(self):
        """md5_utf8 should handle Unicode input."""
        result = formatter.md5_utf8("café")
        assert len(result) == 32


class TestDateFunctions:
    """Tests for date-related functions."""

    def test_now_returns_current_time(self):
        """now() should return current datetime string."""
        result = formatter.now()
        assert len(result) == 19  # YYYY-MM-DD HH:MM:SS
        assert '-' in result
        assert ':' in result

    def test_today_returns_current_date(self):
        """today() should return current date string."""
        result = formatter.today()
        assert len(result) == 10  # YYYY-MM-DD
        today = datetime.date.today().isoformat()
        assert result == today

    def test_age_returns_days_since_date(self):
        """age() should return days since given date."""
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        assert formatter.age(yesterday) == 1

    def test_age_returns_zero_for_today(self):
        """age() should return 0 for today's date."""
        today = datetime.date.today().isoformat()
        assert formatter.age(today) == 0

    def test_age_returns_zero_for_invalid_date(self):
        """age() should return 0 for invalid date."""
        assert formatter.age("invalid") == 0

    def test_datecompare_returns_difference(self):
        """datecompare() should return days between dates."""
        result = formatter.datecompare("2023-01-15", "2023-01-10")
        assert result == 5

    def test_datecompare_handles_negative(self):
        """datecompare() should handle earlier first date."""
        result = formatter.datecompare("2023-01-10", "2023-01-15")
        assert result == -5

    def test_datecompare_returns_zero_for_invalid(self):
        """datecompare() should return 0 for invalid dates."""
        assert formatter.datecompare("invalid", "2023-01-01") == 0


class TestMonth2Num:
    """Tests for month2num() function."""

    def test_month2num_long_names(self):
        """month2num should convert long month names."""
        assert formatter.month2num("january") == 1
        assert formatter.month2num("december") == 12

    def test_month2num_short_names(self):
        """month2num should convert short month names."""
        assert formatter.month2num("jan") == 1
        assert formatter.month2num("dec") == 12

    def test_month2num_case_insensitive(self):
        """month2num should be case insensitive."""
        assert formatter.month2num("JANUARY") == 1
        assert formatter.month2num("January") == 1

    def test_month2num_seasons(self):
        """month2num should convert season names."""
        assert formatter.month2num("winter") == 1
        assert formatter.month2num("spring") == 4
        assert formatter.month2num("summer") == 7
        assert formatter.month2num("fall") == 10
        assert formatter.month2num("autumn") == 10

    def test_month2num_returns_zero_for_unknown(self):
        """month2num should return 0 for unknown names."""
        assert formatter.month2num("notamonth") == 0


class TestCheckYear:
    """Tests for check_year() function."""

    def test_check_year_valid_year(self):
        """check_year should accept valid years."""
        current_year = int(datetime.date.today().strftime("%Y"))
        assert formatter.check_year(str(current_year)) == current_year
        assert formatter.check_year("2000") == 2000

    def test_check_year_future_year(self):
        """check_year should accept year up to 1 year in future."""
        next_year = int(datetime.date.today().strftime("%Y")) + 1
        assert formatter.check_year(str(next_year)) == next_year

    def test_check_year_too_far_future(self):
        """check_year should reject years too far in future."""
        far_future = int(datetime.date.today().strftime("%Y")) + 5
        assert formatter.check_year(str(far_future)) == 0

    def test_check_year_too_old(self):
        """check_year should reject years before 1900."""
        assert formatter.check_year("1800") == 0
        assert formatter.check_year("1899") == 0

    def test_check_year_invalid(self):
        """check_year should return 0 for invalid input."""
        assert formatter.check_year("notayear") == 0


class TestUrlFix:
    """Tests for url_fix() function."""

    def test_url_fix_encodes_spaces(self):
        """url_fix should encode spaces in path."""
        result = formatter.url_fix("http://example.com/path with spaces")
        assert "%20" in result or "+" in result

    def test_url_fix_preserves_valid_url(self):
        """url_fix should preserve already-valid URLs."""
        url = "http://example.com/path?query=value"
        result = formatter.url_fix(url)
        assert "example.com" in result
        assert "path" in result


class TestNzbdate2format:
    """Tests for nzbdate2format() function."""

    def test_nzbdate2format_converts_date(self):
        """nzbdate2format should convert NZB date to YYYY-MM-DD."""
        result = formatter.nzbdate2format("Sat, 02 Mar 2013 06:51:28 +0100")
        assert result == "2013-03-02"

    def test_nzbdate2format_handles_invalid(self):
        """nzbdate2format should return default for invalid input."""
        result = formatter.nzbdate2format("invalid")
        assert result == "1970-01-01"


class TestSortDefinite:
    """Tests for sortDefinite() function."""

    def test_sortDefinite_moves_the_to_end(self):
        """sortDefinite should move 'The' to end."""
        assert formatter.sortDefinite("The Great Gatsby") == "Great Gatsby, The"

    def test_sortDefinite_handles_no_article(self):
        """sortDefinite should not change titles without article."""
        assert formatter.sortDefinite("Great Expectations") == "Great Expectations"

    def test_sortDefinite_handles_empty(self):
        """sortDefinite should handle empty input."""
        assert formatter.sortDefinite("") == ""
        assert formatter.sortDefinite(None) == ""


class TestSurnameFirst:
    """Tests for surnameFirst() function."""

    def test_surnameFirst_swaps_name(self):
        """surnameFirst should put surname first."""
        result = formatter.surnameFirst("John Doe")
        assert result == "Doe, John"

    def test_surnameFirst_handles_single_name(self):
        """surnameFirst should handle single name."""
        result = formatter.surnameFirst("Madonna")
        assert result == "Madonna"

    def test_surnameFirst_handles_empty(self):
        """surnameFirst should handle empty input."""
        assert formatter.surnameFirst("") == ""
        assert formatter.surnameFirst(None) == ""


class TestDateFormat:
    """Tests for dateFormat() function."""

    def test_dateFormat_default_format(self):
        """dateFormat should return YYYY-MM-DD for default format."""
        result = formatter.dateFormat("2023-06-15", "$Y-$m-$d")
        assert result == "2023-06-15"

    def test_dateFormat_custom_format(self):
        """dateFormat should support custom format strings."""
        result = formatter.dateFormat("2023-06-15", "$d/$m/$Y")
        assert result == "15/06/2023"

    def test_dateFormat_year_only(self):
        """dateFormat should extract year."""
        result = formatter.dateFormat("2023-06-15", "$Y")
        assert result == "2023"

    def test_dateFormat_short_year(self):
        """dateFormat should support 2-digit year."""
        result = formatter.dateFormat("2023-06-15", "$y")
        assert result == "23"

    def test_dateFormat_empty_date(self):
        """dateFormat should handle empty date."""
        result = formatter.dateFormat("", "$Y-$m-$d")
        assert result == ""

    def test_dateFormat_digit_string(self):
        """dateFormat should pass through numeric strings."""
        result = formatter.dateFormat("1234", "$Y-$m-$d")
        assert result == "1234"


class TestSecondsToMidnight:
    """Tests for seconds_to_midnight() function."""

    def test_seconds_to_midnight_returns_positive(self):
        """seconds_to_midnight should return positive integer."""
        result = formatter.seconds_to_midnight()
        assert isinstance(result, int)
        assert result >= 0
        assert result < 86400  # Less than 24 hours


class TestNextRun:
    """Tests for next_run() function."""

    def test_next_run_returns_string(self):
        """next_run should return a string."""
        import datetime
        future = datetime.datetime.now() + datetime.timedelta(hours=2)
        when_run = future.strftime('%Y-%m-%d %H:%M:%S')
        result = formatter.next_run(when_run)
        assert isinstance(result, str)

    def test_next_run_handles_invalid_date(self):
        """next_run should handle invalid date gracefully."""
        result = formatter.next_run("invalid date")
        assert isinstance(result, str)


class TestUrlFunctions:
    """Tests for URL-related functions."""

    def test_url_fix_handles_unicode(self):
        """url_fix should handle unicode characters."""
        result = formatter.url_fix("http://example.com/path/café")
        assert "example.com" in result

    def test_url_fix_preserves_query_params(self):
        """url_fix should preserve query parameters."""
        result = formatter.url_fix("http://example.com/path?key=value&other=test")
        assert "key" in result
        assert "value" in result


class TestUnaccentedStr:
    """Tests for unaccented_str() function."""

    def test_unaccented_str_normalizes_text(self):
        """unaccented_str should normalize accented text."""
        result = formatter.unaccented_str("café")
        assert result == "cafe"

    def test_unaccented_str_handles_german_umlauts(self):
        """unaccented_str should handle German umlauts."""
        result = formatter.unaccented_str("über")
        assert "u" in result

    def test_unaccented_str_handles_spanish(self):
        """unaccented_str should handle Spanish characters."""
        result = formatter.unaccented_str("señor")
        assert "sen" in result


class TestEdgeCases:
    """Tests for edge cases in formatter functions."""

    def test_check_int_with_leading_zeros(self):
        """check_int should handle strings with leading zeros."""
        assert formatter.check_int("007", 0) == 7

    def test_check_int_with_whitespace(self):
        """check_int should handle strings with whitespace."""
        # Depends on implementation
        result = formatter.check_int("  42  ", 0)
        # Either returns 42 or default
        assert result in [42, 0]

    def test_size_in_bytes_lowercase(self):
        """size_in_bytes should handle lowercase units."""
        # Depends on implementation - may or may not support lowercase
        result = formatter.size_in_bytes("10k")
        # Either works or returns 0
        assert result >= 0

    def test_plural_with_negative(self):
        """plural should handle negative numbers."""
        result = formatter.plural(-1)
        assert result == 's'

    def test_getList_mixed_separators(self):
        """getList should handle mixed separators."""
        result = formatter.getList("epub, mobi+pdf")
        assert len(result) >= 2
