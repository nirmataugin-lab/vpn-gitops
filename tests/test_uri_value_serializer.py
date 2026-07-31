import pytest

from app.services.uri_value_serializer import UriValueSerializer


class TestUriValueSerializer:
    def setup_method(self):
        self.serializer = UriValueSerializer()

    def test_str(self):
        assert self.serializer.serialize("hello") == "hello"

    def test_int(self):
        assert self.serializer.serialize(42) == "42"

    def test_bool_true(self):
        assert self.serializer.serialize(True) == "true"

    def test_bool_false(self):
        assert self.serializer.serialize(False) == "false"

    def test_none(self):
        assert self.serializer.serialize(None) == ""

    def test_dict(self):
        assert self.serializer.serialize({"a": 1, "b": 2}) == '{"a":1,"b":2}'

    def test_list(self):
        assert self.serializer.serialize([1, 2, 3]) == "[1,2,3]"

    def test_nested_dict(self):
        assert self.serializer.serialize({"outer": {"inner": "value"}}) == '{"outer":{"inner":"value"}}'

    def test_dict_with_list(self):
        assert self.serializer.serialize({"tags": ["a", "b"]}) == '{"tags":["a","b"]}'

    def test_empty_dict(self):
        assert self.serializer.serialize({}) == "{}"

    def test_empty_list(self):
        assert self.serializer.serialize([]) == "[]"

    def test_special_chars_in_string(self):
        result = self.serializer.serialize({"key": "value with spaces & symbols"})
        assert "value with spaces & symbols" in result

    def test_deeply_nested(self):
        data = {"level1": {"level2": {"level3": ["a", "b"]}}}
        assert self.serializer.serialize(data) == '{"level1":{"level2":{"level3":["a","b"]}}}'