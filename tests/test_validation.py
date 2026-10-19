"""登录/注册输入校验与用户信息清洗测试（离线）。"""

from __future__ import annotations

import unittest

from core.validation import (
    ValidationError,
    sanitize_user,
    validate_login_input,
    validate_new_password,
    validate_nickname,
    validate_password,
    validate_password_change,
    validate_register_input,
    validate_register_username,
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
            validate_register_input("alice1", "123", "123")
        with self.assertRaises(ValidationError):
            validate_register_input("alice1", "123456", "123457")
        self.assertEqual(
            validate_register_input("alice1", "123456", "123456"), ("alice1", "123456")
        )


class RegisterUsernameRuleTests(unittest.TestCase):
    """F-c1：注册账号 6–20 位、仅字母数字、至少含一个字母。"""

    def test_valid(self) -> None:
        for name in ("alice1", "ABCDEF", "user123", "a1234567890123456789"):
            with self.subTest(name=name):
                self.assertEqual(validate_register_username(name), name)

    def test_invalid(self) -> None:
        cases = [
            "abc12",             # 太短
            "a" * 21,            # 太长
            "abc-123",           # 非法字符
            "abc_123",           # 下划线不允许
            "123456",            # 无字母
            "中文abc123",         # 非字母数字
            "",
        ]
        for name in cases:
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    validate_register_username(name)

    def test_login_still_allows_old_short_accounts(self) -> None:
        self.assertEqual(validate_login_input("demo", "x")[0], "demo")


class NicknameTests(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertEqual(validate_nickname("  老王  "), "老王")
        self.assertEqual(validate_nickname("a" * 20), "a" * 20)

    def test_invalid(self) -> None:
        with self.assertRaises(ValidationError):
            validate_nickname("   ")
        with self.assertRaises(ValidationError):
            validate_nickname("x" * 21)
        with self.assertRaises(ValidationError):
            validate_nickname("bad\nname")


class PasswordChangeTests(unittest.TestCase):
    def test_new_password_length(self) -> None:
        self.assertEqual(validate_new_password("12345678"), "12345678")
        for password in ("1234567", "x" * 65):
            with self.subTest(password=password):
                with self.assertRaises(ValidationError):
                    validate_new_password(password)

    def test_match_and_old_password(self) -> None:
        self.assertEqual(
            validate_password_change("old-pass", "new-pass-1", "new-pass-1"),
            ("old-pass", "new-pass-1"),
        )
        with self.assertRaises(ValidationError):
            validate_password_change("old-pass", "new-pass-1", "new-pass-2")
        with self.assertRaises(ValidationError):
            validate_password_change("", "new-pass-1", "new-pass-1")
        with self.assertRaises(ValidationError):
            validate_password_change("same-pass", "same-pass", "same-pass")


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
