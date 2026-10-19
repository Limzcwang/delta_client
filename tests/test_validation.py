"""登录/注册输入校验与用户信息清洗测试（离线）。"""

from __future__ import annotations

import unittest

from core.validation import (
    MAX_USERNAME_LENGTH,
    MIN_REGISTER_PASSWORD_LENGTH,
    NEW_PASSWORD_MAX,
    NEW_PASSWORD_MIN,
    ValidationError,
    sanitize_user,
    sanitize_username_input,
    sanitized_cursor_position,
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
            validate_username("x" * 21)
        self.assertEqual("x" * 20, validate_username("x" * 20))

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
            validate_register_input("alice1", "1234567", "1234567")  # 7 位被拦截
        with self.assertRaises(ValidationError):
            validate_register_input("alice1", "12345678", "12345679")
        self.assertEqual(
            validate_register_input("alice1", "12345678", "12345678"),
            ("alice1", "12345678"),
        )


class RegisterPasswordRuleTests(unittest.TestCase):
    """G/B：注册密码与后端对齐为 8–32；登录仍只校验非空。"""

    def test_constants_share_same_rule(self) -> None:
        self.assertEqual(8, NEW_PASSWORD_MIN)
        self.assertEqual(32, NEW_PASSWORD_MAX)
        self.assertEqual(NEW_PASSWORD_MIN, MIN_REGISTER_PASSWORD_LENGTH)

    def test_six_and_seven_rejected_before_submit(self) -> None:
        for password in ("123456", "1234567"):
            with self.subTest(password=password):
                with self.assertRaises(ValidationError) as ctx:
                    validate_register_input("alice1", password, password)
                self.assertIn("8", str(ctx.exception))

    def test_eight_and_bounds_accepted(self) -> None:
        self.assertEqual(
            ("alice1", "12345678"),
            validate_register_input("alice1", "12345678", "12345678"),
        )
        self.assertEqual(
            ("alice1", "x" * 32),
            validate_register_input("alice1", "x" * 32, "x" * 32),
        )
        with self.assertRaises(ValidationError) as too_long:
            validate_register_input("alice1", "x" * 33, "x" * 33)
        self.assertIn("32", str(too_long.exception))

    def test_login_password_stays_lenient(self) -> None:
        # 历史 6 位密码仍可登录，绝不能因为注册/改密规则把老用户挡在门外
        self.assertEqual(validate_login_input("alice1", "123456")[1], "123456")
        self.assertEqual(validate_login_input("alice1", "123"), ("alice1", "123"))


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


class UsernameInputSanitizeTests(unittest.TestCase):
    """G：账号输入框即时过滤（纯函数，覆盖输入/粘贴/截断/光标/模式差异）。"""

    def test_register_filters_everything_but_ascii_alnum(self) -> None:
        cases = {
            "abc中文123": "abc123",
            "abc 123": "abc123",
            "a_b-c.d": "abcd",
            "😀abc": "abc",
            "abc１２３": "abc",          # 全角数字删除
            "ＡＢＣ": "",                # 全角字母删除，不转半角
            "\tabc\n": "abc",
            "ABC123": "ABC123",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(expected, sanitize_username_input(raw, "register"))

    def test_login_same_as_register(self) -> None:
        """G 变更：登录页也只允许字母/数字，不再兼容 dsh_test 下划线账号。"""
        self.assertEqual("dshtest2", sanitize_username_input("dsh_test2", "login"))
        self.assertEqual("dshtest", sanitize_username_input("dsh_test", "login"))
        self.assertEqual("abc", sanitize_username_input("a-b_c", "login"))
        cases = {
            "abc中文": "abc",
            "a b": "ab",
            "a.b": "ab",
            "ＡＢＣ": "",
            "a/b": "ab",
            "abc😀": "abc",
            "abc１２３": "abc",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(expected, sanitize_username_input(raw, "login"))

    def test_mode_behaviour_identical(self) -> None:
        for text in ("dsh_test-2", "abc中文", "ＡＢＣ", "a" * 30, "DeltaQA01"):
            with self.subTest(text=text):
                self.assertEqual(
                    sanitize_username_input(text, "register"),
                    sanitize_username_input(text, "login"),
                )

    def test_login_alnum_submits(self) -> None:
        self.assertEqual(
            ("DeltaQA01", "DeltaTest2026"),
            validate_login_input("DeltaQA01", "DeltaTest2026"),
        )
        self.assertEqual("DeltaQA01", sanitize_username_input("DeltaQA01", "login"))

    def test_paste_keeps_legal_part(self) -> None:
        pasted = "abc中文123😀"
        self.assertEqual("abc123", sanitize_username_input(pasted, "register"))
        self.assertEqual("abc123", sanitize_username_input(pasted, "login"))

    def test_truncation_limits(self) -> None:
        self.assertEqual(20, len(sanitize_username_input("a" * 25, "register")))
        self.assertEqual(20, len(sanitize_username_input("a" * 40, "login")))
        self.assertEqual(MAX_USERNAME_LENGTH, 20)
        # 中文不占长度：过滤后再截断
        self.assertEqual("a" * 20, sanitize_username_input("a" * 19 + "中" + "a", "register"))

    def test_none_and_unknown_mode(self) -> None:
        self.assertEqual("", sanitize_username_input(None, "register"))
        with self.assertRaises(ValueError):
            sanitize_username_input("abc", "unknown")

    def test_cursor_position_rolls_back_removed_chars(self) -> None:
        # "ab中文cd"，光标在 4（中文之后）：删除 2 个中文，光标回到 2
        self.assertEqual(2, sanitized_cursor_position("ab中文cd", 4, "register"))
        # 光标在合法字符之后：位置不变
        self.assertEqual(2, sanitized_cursor_position("abcd", 2, "register"))
        # 末尾：等于清洗后长度
        self.assertEqual(4, sanitized_cursor_position("ab中文cd", 6, "register"))
        # 超长光标按末尾处理
        self.assertEqual(4, sanitized_cursor_position("abcd", 99, "register"))
        # 0 不变
        self.assertEqual(0, sanitized_cursor_position("中文abc", 0, "register"))
        # 截断时光标不超过上限
        self.assertEqual(20, sanitized_cursor_position("a" * 25, 25, "register"))

    def test_nickname_still_allows_chinese(self) -> None:
        self.assertEqual("中文昵称", validate_nickname("中文昵称"))


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
        self.assertEqual(validate_new_password("x" * 32), "x" * 32)
        for password in ("1234567", "x" * 33):
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
