"""Security-focused tests — secret detection, input validation, sanitization."""

from __future__ import annotations

import pytest

from friday.domain.permissions import contains_secret, sanitize_for_prompt
from friday.domain.validation import (
    validate_command,
    validate_content,
    validate_line_range,
    validate_path,
    validate_pattern,
)


class TestContainsSecret:
    def test_keyword_api_key(self) -> None:
        assert contains_secret('my api_key is ABC123')

    def test_keyword_token(self) -> None:
        assert contains_secret('set the token to xyz')

    def test_keyword_password(self) -> None:
        assert contains_secret('password: hunter2')

    def test_keyword_senha(self) -> None:
        assert contains_secret('minha senha e 12345')

    def test_aws_key(self) -> None:
        assert contains_secret('AKIAIOSFODNN7EXAMPLE')

    def test_bearer_token(self) -> None:
        assert contains_secret('Authorization: Bearer eyJhbGciOiJIUzI1NiJ9')

    def test_url_with_credentials(self) -> None:
        assert contains_secret('postgres://admin:s3cret@localhost/db')

    def test_long_hex_token(self) -> None:
        assert contains_secret('key=' + 'a1b2c3d4' * 5)

    def test_ssh_key_header(self) -> None:
        assert contains_secret('-----BEGIN RSA PRIVATE KEY-----')

    def test_github_token(self) -> None:
        assert contains_secret('ghp_1234567890abcdef1234567890abcdef12345')

    def test_safe_text(self) -> None:
        assert not contains_secret('how do I use the find command?')

    def test_safe_code(self) -> None:
        assert not contains_secret('def main():\n    print("hello")')

    def test_empty(self) -> None:
        assert not contains_secret('')


class TestSanitizeForPrompt:
    def test_clean_text_passes_through(self) -> None:
        assert sanitize_for_prompt('hello world') == 'hello world'

    def test_secret_is_redacted(self) -> None:
        result = sanitize_for_prompt('curl -H "Bearer eyJtoken"')
        assert 'redacted' in result
        assert 'Bearer' not in result

    def test_long_text_clipped(self) -> None:
        result = sanitize_for_prompt('hello world ' * 50, limit=100)
        assert 'truncated' in result

    def test_secret_in_long_text_redacted(self) -> None:
        result = sanitize_for_prompt('api_key=secret123 ' + 'x' * 500, limit=100)
        assert 'redacted' in result


class TestValidatePath:
    def test_normal_path(self) -> None:
        assert validate_path('src/main.py') == 'src/main.py'

    def test_too_long(self) -> None:
        with pytest.raises(ValueError, match='path too long'):
            validate_path('a/' * 300)


class TestValidatePattern:
    def test_normal_pattern(self) -> None:
        assert validate_pattern('*.py') == '*.py'

    def test_too_long(self) -> None:
        with pytest.raises(ValueError, match='pattern too long'):
            validate_pattern('a' * 300)

    def test_traversal_rejected(self) -> None:
        with pytest.raises(ValueError, match='must not contain'):
            validate_pattern('../**/*.py')


class TestValidateCommand:
    def test_normal_command(self) -> None:
        assert validate_command('ls -la') == 'ls -la'

    def test_too_long(self) -> None:
        with pytest.raises(ValueError, match='command too long'):
            validate_command('echo ' + 'x' * 3000)


class TestValidateContent:
    def test_normal_content(self) -> None:
        assert validate_content('hello') == 'hello'

    def test_too_large(self) -> None:
        with pytest.raises(ValueError, match='content too large'):
            validate_content('x' * 200_000)


class TestValidateLineRange:
    def test_normal_range(self) -> None:
        assert validate_line_range(1, 100) == (1, 100)

    def test_negative_start_clamped(self) -> None:
        start, _ = validate_line_range(-5, 100)
        assert start == 1

    def test_huge_end_clamped(self) -> None:
        _, end = validate_line_range(1, 999_999)
        assert end == 10_000

    def test_inverted_range_corrected(self) -> None:
        start, end = validate_line_range(100, 50)
        assert start <= end
