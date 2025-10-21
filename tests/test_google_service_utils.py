import json
import base64
import pytest

from google_service_utils import normalize_service_account_json

sample = {
    "type": "service_account",
    "project_id": "proj",
    "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
    "client_email": "a@b.com"
}


def test_dict_input():
    assert normalize_service_account_json(sample) == sample


def test_raw_json():
    s = json.dumps(sample)
    assert normalize_service_account_json(s) == sample


def test_escaped_newlines():
    s = json.dumps(sample).replace('\n', '\\n')
    assert normalize_service_account_json(s) == sample


def test_base64_valid():
    s = base64.b64encode(json.dumps(sample).encode('utf-8')).decode('utf-8')
    assert normalize_service_account_json(s) == sample


def test_base64_invalid():
    with pytest.raises(ValueError):
        normalize_service_account_json('not-a-valid-base64-or-json')


def test_base64_missing_padding():
    raw = json.dumps(sample)
    s = base64.b64encode(raw.encode('utf-8')).decode('utf-8')
    # remove padding '='
    s_short = s.rstrip('=')
    assert normalize_service_account_json(s_short) == sample
