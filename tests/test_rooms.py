"""房间号/房间名/可见性/密码校验测试（离线）。"""

from __future__ import annotations

import unittest

from core.rooms import (
    ValidationError,
    is_valid_room_code,
    normalize_room_code,
    room_has_password,
    validate_room_code,
    validate_room_name,
    validate_room_password,
    validate_visibility,
)


class RoomCodeTests(unittest.TestCase):
    def test_normalize(self) -> None:
        self.assertEqual(normalize_room_code(" ab12c "), "AB12C")
        self.assertEqual(normalize_room_code(None), "")

    def test_valid_codes(self) -> None:
        for code in ("AB12C", "00000", "ZZZZZ", "O0I1L"):
            with self.subTest(code=code):
                self.assertTrue(is_valid_room_code(code))
                self.assertEqual(validate_room_code(code), code)

    def test_invalid_codes(self) -> None:
        for code in ("AB12", "ABCDE1", "AB-12", "AB 12", "", "   ", "abc"):
            with self.subTest(code=code):
                self.assertFalse(is_valid_room_code(code))
                with self.assertRaises(ValidationError):
                    validate_room_code(code)

    def test_validate_normalizes_lowercase_and_whitespace(self) -> None:
        self.assertEqual(validate_room_code("ab12c"), "AB12C")
        self.assertEqual(validate_room_code(" AB12C\n"), "AB12C")
        self.assertTrue(is_valid_room_code(" ab12c "))

    def test_empty_message(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate_room_code("")
        self.assertIn("请输入房间号", str(ctx.exception))


class RoomNameTests(unittest.TestCase):
    def test_valid_name_is_trimmed(self) -> None:
        self.assertEqual(validate_room_name("  开黑房  "), "开黑房")

    def test_empty_name(self) -> None:
        with self.assertRaises(ValidationError):
            validate_room_name("   ")

    def test_too_long_name(self) -> None:
        with self.assertRaises(ValidationError):
            validate_room_name("x" * 33)

    def test_control_char_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            validate_room_name("bad\nname")


class VisibilityTests(unittest.TestCase):
    def test_public_private(self) -> None:
        self.assertEqual(validate_visibility("public"), "public")
        self.assertEqual(validate_visibility("Private"), "private")
        self.assertEqual(validate_visibility(True), "private")
        self.assertEqual(validate_visibility(False), "public")
        self.assertEqual(validate_visibility("私有"), "private")

    def test_invalid_visibility(self) -> None:
        with self.assertRaises(ValidationError):
            validate_visibility("secret")


class RoomPasswordTests(unittest.TestCase):
    def test_private_requires_password(self) -> None:
        self.assertEqual(validate_room_password("1234", "private"), "1234")
        with self.assertRaises(ValidationError):
            validate_room_password("", "private")
        with self.assertRaises(ValidationError):
            validate_room_password(None, "private")

    def test_public_ignores_password(self) -> None:
        self.assertIsNone(validate_room_password("1234", "public"))
        self.assertIsNone(validate_room_password(None, "public"))

    def test_password_not_stripped_and_length_limited(self) -> None:
        self.assertEqual(validate_room_password(" pass ", "private"), " pass ")
        with self.assertRaises(ValidationError):
            validate_room_password("x" * 65, "private")


class RoomLockedTests(unittest.TestCase):
    def test_target_fields(self) -> None:
        self.assertTrue(room_has_password({"has_password": True}))
        self.assertFalse(room_has_password({"has_password": False}))
        self.assertTrue(room_has_password({"is_private": True}))
        self.assertTrue(room_has_password({"locked": "true"}))
        self.assertFalse(room_has_password({}))

    def test_legacy_domain(self) -> None:
        self.assertTrue(room_has_password({"domain": 2}))
        self.assertTrue(room_has_password({"domain": "2"}))
        self.assertFalse(room_has_password({"domain": 1}))
        self.assertFalse(room_has_password({"domain": "bad"}))


if __name__ == "__main__":
    unittest.main()
