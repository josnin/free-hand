import pytest
from free_hand.protocol import ProtocolError, parse_response

def test_valid(): assert parse_response('{"version":1,"tool_calls":[],"final_message":"done"}')['version'] == 1
@pytest.mark.parametrize('raw', ['', '[]', '{}', '{"version":2,"tool_calls":[],"final_message":null}', '{"version":1,"tool_calls":{},"final_message":null}'])
def test_invalid(raw):
    with pytest.raises(ProtocolError): parse_response(raw)


def test_invalid_backslash_escape_has_actionable_message():
    raw = r'{"version":1,"tool_calls":[{"id":"call_001","type":"function","function":{"name":"list_files","arguments":{"pattern":"\*"}}}],"final_message":""}'
    with pytest.raises(ProtocolError, match="JSON strings do not support this backslash escape") as exc:
        parse_response(raw)
    assert 'rather than "\\*"' in str(exc.value)


def test_invalid_control_character_has_actionable_message():
    raw = '{"version":1,"tool_calls":[],"final_message":"First line\nSecond line"}'
    with pytest.raises(ProtocolError, match="JSON strings cannot contain literal newlines") as exc:
        parse_response(raw)
    assert "other control characters" in str(exc.value)
    assert "encode each newline as \\n" in str(exc.value)


def test_clean_response_extracts_markdown_fenced_json():
    from free_hand.protocol import clean_response

    raw = 'Here is the response:\n```json\n{"version":1,"tool_calls":[],"final_message":"done"}\n```\n'
    cleaned = clean_response(raw)
    assert parse_response(cleaned)["final_message"] == "done"


def test_clean_response_extracts_json_from_surrounding_prose():
    from free_hand.protocol import clean_response

    raw = 'Please run this:\n{"version":1,"tool_calls":[],"final_message":"done"}\nThat is all.'
    assert parse_response(clean_response(raw))["tool_calls"] == []


def test_clean_response_does_not_repair_invalid_escape():
    from free_hand.protocol import ProtocolError, clean_response

    raw = r'''AI assistant response:\n{"version":1,"tool_calls":[{"id":"call_001","type":"function","function":{"name":"list_files","arguments":{"pattern":"\*"}}}],"final_message":"done"}'''
    with pytest.raises(ProtocolError, match="JSON strings do not support this backslash escape"):
        clean_response(raw)


def test_clean_response_rejects_multiple_response_objects():
    from free_hand.protocol import ProtocolError, clean_response

    response = '{"version":1,"tool_calls":[],"final_message":"done"}'
    with pytest.raises(ProtocolError, match="multiple Free-hand JSON response objects"):
        clean_response(response + "\n" + response)
