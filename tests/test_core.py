import struct
from datetime import datetime, timezone, timedelta
from shared.simulator import Belt
from shared.model import Measurement
from vm.modbus_codec import encode, decode
from vm.journal import Journal
from vm.camera import TemporalClassifier
from server.logic import alarm_transition, period_metrics
from server.db import Store


def test_modbus_register_contract():
    b = Belt(produced=0x12345678, rejected=12, temperature_c=47.5, current_a=7.25, state=1)
    ir, hr = encode(b)
    assert ir[:2] == [0x1234, 0x5678]
    assert ir[2:4] == list(struct.unpack('>HH', struct.pack('>f', 47.5)))[::-1]
    assert ir[9] == 725 and ir[19] == 12 and hr == [1]
    assert decode(ir, hr) == dict(produced=b.produced, temperature_c=47.5,current_a=7.25,rejected=12,state=1)


def test_simulator_causality():
    b = Belt(state=0)
    b.step(); assert b.produced == 0 and b.current_a < 0.1
    b.state = 1
    for _ in range(12): b.step()
    assert b.produced == 36 and b.rejected == 1 and b.temperature_c > 22
    b.state = 2; old = b.temperature_c; b.step()
    assert b.produced == 36 and b.temperature_c > old


def test_journal_replay_and_db_dedupe(tmp_path):
    journal = Journal(str(tmp_path/'journal.db'))
    store = Store(tmp_path/'server.db')
    item = Measurement('belt-2','id-1',1,datetime.now(timezone.utc).isoformat(),10,45,7,1,1)
    journal.append(item)
    assert store.ingest(item) is True
    assert store.ingest(item) is False
    journal.acknowledge(1,'id-1')
    assert journal.pending() == [] and len(journal.after(0)) == 1


def test_alarm_hysteresis_and_staleness():
    now = datetime.now(timezone.utc)
    n = now.isoformat(); old = (now-timedelta(seconds=20)).isoformat()
    assert alarm_transition(False,81,n,n,80,5)
    assert alarm_transition(True,77,n,n,80,5)
    assert not alarm_transition(True,75,n,n,80,5)
    assert not alarm_transition(False,100,old,n,80,5)


def test_metrics_unknown_reset_zero():
    rows=[dict(epoch=0,state=1,produced=100,rejected=5),dict(epoch=5,state=1,produced=110,rejected=6),dict(epoch=30,state=0,produced=1,rejected=0)]
    m=period_metrics(rows,0,40)
    assert m['produced_delta']==10 and m['rejected_delta']==1
    assert m['unknown_seconds']>=25 and m['running_ratio']==1
    assert period_metrics([],0,10)['reject_ratio'] is None


def test_temporal_camera_without_frames():
    c=TemporalClassifier()
    for _ in range(20): result=c.update(True,True,0.4)
    assert result=='normal'
    # Intermittent missed face detections must not flicker to "absent".
    for seen in (False, True, False, True, True, False):
        result=c.update(seen,seen,0.4 if seen else None)
        assert result=='normal'
    for _ in range(12): result=c.update(True,False,0.4)
    assert result=='tired'
    for _ in range(12): result=c.update(False)
    assert result=='absent'


def test_unreliable_eye_detector_does_not_claim_fatigue():
    c=TemporalClassifier()
    for _ in range(30):
        assert c.update(True,False,0.4,0.3) in ('absent','normal')
    assert not c.eyes_calibrated
    for _ in range(12): result=c.update(True,False,0.60,0.3)
    assert result=='normal'  # Head movement without reliable eyes is insufficient.


def test_head_drop_supports_calibrated_eye_closure():
    c=TemporalClassifier()
    for _ in range(20): c.update(True,True,0.4,0.3)
    for _ in range(8): result=c.update(True,False,0.6,0.3)
    assert result=='tired'


def test_camera_movement_does_not_look_like_head_drop():
    c=TemporalClassifier()
    for _ in range(20): result=c.update(True,False,0.3,0.15)
    for _ in range(12): result=c.update(True,False,0.55,0.35)
    assert result=='normal'


def test_camera_state_hysteresis_avoids_rapid_flicker():
    c=TemporalClassifier()
    for _ in range(20): c.update(True,True,0.4,0.3)
    for _ in range(12): result=c.update(False)
    assert result=='absent'
    for seen in (True, False) * 8:
        assert c.update(seen, seen, 0.4, 0.3) == 'absent'
    for _ in range(12): result=c.update(True,True,0.4,0.3)
    assert result=='normal'
