"""Component outage checks; VM end-to-end outage demo remains separate."""
from datetime import datetime, timezone
from dataclasses import replace
import socket
import time
import pytest
import paho.mqtt.client as mqtt
from shared.model import Measurement
from server.db import Store
from vm.journal import Journal


def record(sequence):
    return Measurement("belt-2",f"event-{sequence}",sequence,datetime.now(timezone.utc).isoformat(),sequence*3,40,7,1,sequence//12)


def test_broker_outage_keeps_outbox(tmp_path):
    journal=Journal(str(tmp_path/'outbox.db'))
    journal.append(record(1))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); closed_port=sock.getsockname()[1]
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    with pytest.raises(Exception):
        client.connect('127.0.0.1',closed_port,1)
    assert [r['sequence'] for r in journal.pending()]==[1]


def test_publisher_stop_and_restart_preserves_sequence(tmp_path):
    path=str(tmp_path/'outbox.db')
    first=Journal(path)
    first.append(record(first.next_sequence()))
    # No process means no new generated row; restart reads the same durable row.
    second=Journal(path)
    assert second.next_sequence()==2
    assert [r['sequence'] for r in second.pending()]==[1]
    second.append(record(second.next_sequence()))
    assert [r['sequence'] for r in second.pending()]==[1,2]


def test_platform_outage_replay_has_no_gap_or_duplicate(tmp_path):
    journal=Journal(str(tmp_path/'outbox.db'))
    platform=Store(tmp_path/'platform.db')
    journal.append(record(1))
    assert platform.ingest(record(1))
    journal.acknowledge(1,'event-1')
    # During outage there is no DB acknowledgement even if broker got PUBACK.
    journal.append(record(2));journal.append(record(3))
    assert [r['sequence'] for r in journal.pending()]==[2,3]
    for payload in journal.pending():
        item=Measurement(**payload)
        assert platform.ingest(item)
        assert not platform.ingest(item)
        journal.acknowledge(item.sequence,item.event_id)
    with platform.connect() as db:
        rows=db.execute("SELECT sequence FROM measurements ORDER BY sequence").fetchall()
    assert [r[0] for r in rows]==[1,2,3]
    assert journal.pending()==[]


def test_modbus_cursor_replay_after_platform_restart(tmp_path):
    journal=Journal(str(tmp_path/'modbus.db'))
    platform=Store(tmp_path/'platform.db')
    for seq in range(1,4): journal.append(record(seq))
    for payload in journal.after(0): platform.ingest(Measurement(**payload))
    journal.acknowledge_through(3)
    # Platform process loses in-memory cursor; persistent IDs deduplicate replay.
    for payload in Journal(str(tmp_path/'modbus.db')).after(0):
        assert not platform.ingest(Measurement(**payload))
    with platform.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]==3


def test_journal_capacity_stops_new_measurements(tmp_path):
    journal = Journal(str(tmp_path/'bounded.db'), max_rows=2)
    journal.append(record(1))
    journal.append(record(2))
    assert not journal.has_capacity()
    with pytest.raises(RuntimeError, match='journal full'):
        journal.append(record(3))
    assert [r['sequence'] for r in journal.after(0)] == [1, 2]
    journal.acknowledge(1, 'event-1')
    assert journal.has_capacity()
    journal.append(record(3))
    assert [r['sequence'] for r in journal.after(0)] == [1, 2, 3]


def test_sqlite_disk_full_does_not_commit_partial_measurement(tmp_path):
    journal = Journal(str(tmp_path/'disk-limit.db'))
    db = journal.db()
    try:
        pages = db.execute('PRAGMA page_count').fetchone()[0]
        db.execute(f'PRAGMA max_page_count={pages}')
        journal.db = lambda: db  # SQLite page limit belongs to this connection.
        large = replace(record(1), event_id='x' * 100_000)
        with pytest.raises(RuntimeError, match='journal disk failure'):
            journal.append(large)
        assert journal.after(0) == []
        assert journal.next_sequence() == 1
    finally:
        db.close()


def test_retention_purges_only_old_acknowledged_records(tmp_path):
    journal = Journal(str(tmp_path/'retention.db'))
    journal.append(record(1))
    journal.append(record(2))
    journal.acknowledge(1, 'event-1')
    with journal.db() as db:
        db.execute('UPDATE records SET created_at=? WHERE seq IN (1,2)',
                   (time.time() - 8 * 86400,))
    journal.append(record(3))
    assert [r['sequence'] for r in journal.after(0)] == [2,3]
    assert [r['sequence'] for r in journal.pending()] == [2,3]
