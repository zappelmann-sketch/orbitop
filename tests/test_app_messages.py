# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright © 2026 zappelmann-sketch
"""parse_message: welche Nachrichten der Seite angenommen und welche verworfen werden."""
import json

import pytest

from orbitop import messages
from orbitop.layout import COLUMNS, DEFAULT_HIDDEN
from orbitop.messages import parse_message

L = {"order": list(COLUMNS), "hidden": list(DEFAULT_HIDDEN), "widths": {"cpu": 90}, "split": 0.6}


# ---- parse_message ----
@pytest.mark.parametrize("raw,msg", [
    ('{"type":"ready"}', {"type": "ready"}),
    ('{"type":"quit"}', {"type": "quit"}),
    ('{"type":"view","tab":"overview","pid":null,"start":null}',
     {"type": "view", "tab": "overview", "pid": None, "start": None}),
    ('{"type":"view","tab":"procs","pid":42,"start":0}', {"type": "view", "tab": "procs", "pid": 42, "start": 0}),
    ('{"type":"terminate","pid":42,"start":123456,"force":false}',
     {"type": "terminate", "pid": 42, "start": 123456, "force": False}),
    ('{"type":"terminate","pid":1,"start":2,"force":true}', {"type": "terminate", "pid": 1, "start": 2, "force": True}),
    ('{"type":"ready","extra":[1,2],"pid":"x"}', {"type": "ready"}),  # Zusatzschlüssel werden ignoriert
    ('{"type":"terminate","pid":3,"start":4,"force":true,"sig":"HUP"}',
     {"type": "terminate", "pid": 3, "start": 4, "force": True}),
    ('{"type":"terminate","pid":4194304,"start":9223372036854775807,"force":false}',  # Obergrenzen genau
     {"type": "terminate", "pid": 4194304, "start": 2**63 - 1, "force": False}),
    ('{"type":"view","tab":"procs","pid":4194304,"start":9223372036854775807}',
     {"type": "view", "tab": "procs", "pid": 4194304, "start": 2**63 - 1}),
    (json.dumps({"type": "layout", **L, "path": "/etc/passwd"}), {"type": "layout", **L}),
    ('{"type":"autostart","on":true}', {"type": "autostart", "on": True}),
    ('{"type":"autostart","on":false,"path":"/etc/xdg"}', {"type": "autostart", "on": False}),
    # B2.7, M-9: Zusatzfelder fallen weg, nur normalisierte Felder verlassen parse_message
    ('{"type":"counters","on":true,"x":1}', {"type": "counters", "on": True}),
    ('{"type":"counters","on":false}', {"type": "counters", "on": False}),
    ('{"type":"install_tool","package":"evil-package"}', {"type": "install_tool"}),
    ('{"type":"hide_hint","key":"hint.rapl_noperm","path":"/x"}', {"type": "hide_hint", "key": "hint.rapl_noperm"}),
    ('{"type":"show_hints","keys":["hint.igt_missing"]}', {"type": "show_hints"}),
])
def test_parse_message_accepts_contract_shapes(raw, msg):
    assert parse_message(raw) == msg


def test_parse_message_accepts_every_footer_hint():
    from orbitop.hints import KEYS
    assert [parse_message(json.dumps({"type": "hide_hint", "key": k})) for k in KEYS] == [
        {"type": "hide_hint", "key": k} for k in KEYS]


def test_parse_message_layout_rejects_bad_and_oversize():
    assert parse_message(json.dumps({"type": "layout", **L, "hidden": ["process"]})) is None
    assert parse_message(json.dumps({"type": "layout", **L, "pad": "x" * 4096})) is None
    assert parse_message(json.dumps({"type": "layout", **L}).replace("0.6", "1" + "0" * 400)) is None
    assert parse_message('{"type":"layout","order":[],"hidden":[],"widths":{},"split":NaN}') is None


@pytest.mark.parametrize("raw", [
    '{"type":"terminate","pid":true,"start":1,"force":false}',   # bool als pid
    '{"type":"terminate","pid":1,"start":false,"force":false}',
    '{"type":"view","tab":"procs","pid":true,"start":1}',
    '{"type":"terminate","pid":-1,"start":1,"force":false}',     # negativ
    '{"type":"view","tab":"procs","pid":1,"start":-5}',
    '{"type":"terminate","pid":"1","start":1,"force":false}',    # str
    '{"type":"terminate","pid":1.0,"start":1,"force":false}',    # float
    '{"type":"terminate","pid":1e400,"start":1,"force":false}',  # inf
    '{"type":"terminate","pid":NaN,"start":1,"force":false}',
    '{"type":"terminate","pid":4194305,"start":1,"force":false}',  # über PID_MAX_LIMIT
    '{"type":"terminate","pid":1,"start":9223372036854775808,"force":false}',  # start ≥ 2**63
    pytest.param('{"type":"terminate","pid":1%s,"start":1,"force":false}' % ("0" * 4000), id="pid-4001-digits"),
    '{"type":"view","tab":"procs","pid":4194305,"start":1}',
    '{"type":"view","tab":"procs","pid":1,"start":9223372036854775808}',
    '{"type":"terminate","start":1,"force":false}',              # pid fehlt
    '{"type":"terminate","pid":1,"start":1}',                    # force fehlt
    '{"type":"terminate","pid":1,"start":1,"force":"yes"}',
    '{"type":"terminate","pid":1,"start":1,"force":1}',
    '{"type":"terminate","pid":1,"start":null,"force":true}',
    '{"type":"view","tab":"x","pid":null,"start":null}',
    '{"type":"view","tab":["procs"],"pid":null,"start":null}',
    '{"type":"view","pid":null,"start":null}',
    '{"type":"autostart","on":1}', '{"type":"autostart","on":"true"}', '{"type":"autostart"}',
    '{"type":"autostart","on":null}',
    '{"type":"counters","on":1}', '{"type":"counters","on":"true"}', '{"type":"counters","on":null}',
    '{"type":"counters"}', '{"type":"counters","on":[true]}',
    '{"type":"hide_hint","key":"hint.evil"}', '{"type":"hide_hint","key":"footer.missing"}',  # nur Fußzeilen-Hinweise
    '{"type":"hide_hint","key":["hint.igt_missing"]}', '{"type":"hide_hint","key":null}', '{"type":"hide_hint"}',
    '{"type":"reload"}', '{"type":["ready"]}', '{"type":null}', '{}',
    '[{"type":"ready"}]', "null", "1", '"ready"', "", "{kaputt", '{"type":"ready"',
    '{"type":"ready","pad":"' + "x" * 4096 + '"}',               # zu lang
])
def test_parse_message_rejects(raw):
    assert parse_message(raw) is None


def test_parse_message_rejects_non_str_and_length_limit():
    assert parse_message(None) is None
    pad = '{"type":"ready","p":"%s"}'
    assert parse_message(pad % ("x" * (4096 - len(pad % "")))) == {"type": "ready"}  # genau 4096 Zeichen
    assert parse_message(pad % ("x" * (4097 - len(pad % "")))) is None


def test_parse_message_survives_deep_nesting(monkeypatch):
    deep = '{"type":"ready","x":' + "[" * 2030 + "]" * 2030 + "}"
    assert len(deep) <= 4096
    assert parse_message(deep) in (None, {"type": "ready"})  # je nach Python-Version geparst oder RecursionError

    def boom(_):
        raise RecursionError
    monkeypatch.setattr(messages.json, "loads", boom)
    assert parse_message('{"type":"ready"}') is None
