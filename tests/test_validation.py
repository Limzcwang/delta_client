"""登录/注册输入校验与用户信息清洗测试（离线）。"""

from __future__ import annotations

import unittest

from core.validation import (
    ValidationError,
    sanitize_user,
    validate_login_input,
    validate_password,
    validate_register_input,
    validate_username,
)


class UsernameTests(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertEqual(validate_username("  alice  "), "alice")

    def test_empty(self) -> None:
        with self.assertRaises(ValidationError):
            validate_username("   ")

    def test_too_long(self) -> None:
        with self.assertRaises(ValidationError):
            validate_username("x" * 33)

    def test_control_chars(self) -> None:
        with self.assertRaises(ValidationError):
            validate_username("bad\nname")


class PasswordTests(unittest.TestCase):
    def test_password_not_stripped(self) -> None:
        self.assertEqual(validate_password(" pass "), " pass ")
        self.assertEqual(validate_password("a b"), "a b")

    def test_empty_password(self) -> None:
        with self.assertRaises(ValidationError):
            validate_password("")
        with self.assertRaises(ValidationError):
            validate_password(None)

    def test_login_does_not_enforce_register_min_length(self) -> None:
        # 老账号可能是短密码，登录不能拦截
        self.assertEqual(validate_login_input("alice", "123"), ("alice", "123"))

    def test_register_min_length_and_confirm(self) -> None:
        with self.assertRaises(ValidationError):
            validate_register_input("alice", "123", "123")
        with self.assertRaises(ValidationError):
            validate_register_input("alice", "123456", "123457")
        self.assertEqual(validate_register_input("alice", "123456", "123456"), ("alice", "123456"))


class SanitizeUserTests(unittest.TestCase):
    def test_removes_sensitive_keys(self) -> None:
        cleaned = sanitize_user(
            {
                "id": 1,
                "username": "alice",
                "password": "secret",
                "password_hash": "scrypt$...",
                "access_token": "jwt",
                "api_secret": "s",
                "nickname": "A",
            }
        )
        self.assertEqual(cleaned, {"id": 1, "username": "alice", "nickname": "A"})
        self.assertNotIn("secret", str(cleaned))

    def test_nested_cleaned(self) -> None:
        cleaned = sanitize_user({"user": {"username": "bob", "password": "x"}})
        self.assertEqual(cleaned, {"user": {"username": "bob"}})

    def test_non_mapping(self) -> None:
        self.assertEqual(sanitize_user(None), {})
        self.assertEqual(sanitize_user("nope"), {})


if __name__ == "__main__":
    unittest.main()
