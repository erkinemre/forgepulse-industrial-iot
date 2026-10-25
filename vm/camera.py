"""Phone RTSP/MJPEG capture on VM. No frame is persisted or transmitted."""
import argparse
import json
import os
import time
import urllib.request
from collections import deque
from shared.model import utcnow


class TemporalClassifier:
    def __init__(self, window=12):
        self.window = deque(maxlen=window)
        self.head_window = deque(maxlen=window)
        self.eye_baseline = deque(maxlen=20)
        self.eyes_calibrated = False
        self.last_face_y = None
        self.last_face_size = None
        self.last_label = "absent"

    def update(self, face_present, eyes_visible=False, face_y=None, face_size=None):
        if not face_present:
            self.window.append("absent")
            self.head_window.append(False)
        else:
            stable_scale = (self.last_face_size is not None and face_size is not None
                            and 0.85 <= face_size / self.last_face_size <= 1.15)
            head_drop = (stable_scale and self.last_face_y is not None and face_y is not None
                         and face_y - self.last_face_y > 0.15)
            self.eye_baseline.append(bool(eyes_visible))
            if len(self.eye_baseline) == 20 and sum(self.eye_baseline) >= 15:
                self.eyes_calibrated = True
            eyes_closed = self.eyes_calibrated and not eyes_visible
            self.window.append("fatigue" if eyes_closed else "normal")
            self.head_window.append(bool(head_drop))
            if face_y is not None and face_size is not None and not head_drop:
                if not stable_scale or self.last_face_y is None:
                    self.last_face_y, self.last_face_size = face_y, face_size
                else:
                    self.last_face_y = 0.95*self.last_face_y + 0.05*face_y
                    self.last_face_size = 0.95*self.last_face_size + 0.05*face_size
        absent = sum(x == "absent" for x in self.window)
        fatigue = sum(x == "fatigue" for x in self.window)
        normal = sum(x == "normal" for x in self.window)
        fatigue_threshold = 8 if sum(self.head_window) >= 7 else 10
        if self.last_label == "absent":
            if normal >= 10:
                self.last_label = "normal"
        elif self.last_label == "tired":
            if absent >= 10:
                self.last_label = "absent"
            elif normal >= 10:
                self.last_label = "normal"
        else:
            if absent >= 10:
                self.last_label = "absent"
            elif fatigue >= fatigue_threshold:
                self.last_label = "tired"
        return self.last_label


def main():
    import cv2
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="Phone RTSP or MJPEG URL")
    p.add_argument("--platform", required=True)
    p.add_argument("--key", default=os.getenv("INGEST_KEY"))
    p.add_argument("--preview", action="store_true", help="Show local VM window only; never stream or save frames")
    args = p.parse_args()
    if not args.key:
        p.error("INGEST_KEY is required")
    face_model = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    eye_model = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    classifier = TemporalClassifier()
    last_sent = None
    last_sent_at = 0
    while True:
        cap = cv2.VideoCapture(args.url)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        if not cap.isOpened():
            print("Camera disconnected; retrying", flush=True)
            time.sleep(3)
            continue
        print("Camera connected", flush=True)
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera disconnected; reconnecting", flush=True)
                break
            if args.preview:
                cv2.imshow("VM local camera preview (not recorded)", frame)
                cv2.waitKey(1)
            gray = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            faces = face_model.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=3, minSize=(45,45))
            if len(faces):
                x,y,w,h = max(faces, key=lambda f: f[2]*f[3])
                upper = gray[y:y+int(h*0.6), x:x+w]
                eyes = eye_model.detectMultiScale(upper, minNeighbors=5, minSize=(12,12))
                label = classifier.update(True, len(eyes)>=1, (y+h/2)/frame.shape[0], h/frame.shape[0])
            else:
                label = classifier.update(False)
            if label != last_sent or time.monotonic()-last_sent_at >= 5:
                payload = json.dumps({"class":label,"at_utc":utcnow()}).encode()
                req = urllib.request.Request(args.platform.rstrip('/')+"/api/camera", data=payload,
                    headers={"Content-Type":"application/json","X-Ingest-Key":args.key})
                try:
                    with urllib.request.urlopen(req, timeout=3): pass
                    last_sent = label
                    last_sent_at = time.monotonic()
                    print("Class:", label, flush=True)
                except Exception as exc:
                    print("Platform unavailable:", type(exc).__name__, flush=True)
            # The frame is discarded on the next iteration. No recording or preview endpoint.
        cap.release()
        if args.preview:
            cv2.destroyAllWindows()
        time.sleep(2)


if __name__ == "__main__":
    main()
