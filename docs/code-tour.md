# Kod turu

1. `shared/model.py`: protokolden bağımsız ölçüm ve doğrulama.
2. `shared/simulator.py`: çalışma/duruş/arıza durumlarının sinyallere etkisi.
3. `vm/modbus_codec.py` ve `vm/modbus_sim.py`: register kodlaması, canlı Modbus ve ayrı recovery API.
4. `vm/mqtt_publisher.py` ve `vm/journal.py`: kalıcı outbox, sıra, platform commit onayı, kapasite sınırı.
5. `server/collectors.py`: iki transport adaptörü, kopma/toparlanma, recovery replay.
6. `server/db.py`: SQLite tabloları, tekilleştirme, olay ve alarm geçişleri.
7. `server/app.py` ve `server/auth.py`: rol denetimi, CRUD, canlı/geçmiş/olay/alarm API'leri.
8. `server/logic.py`: hysteresis ve bant başına dönem hesapları.
9. `vm/camera.py` ve `vm/run_camera.sh`: kareleri VM içinde işleyen zamansal sınıflandırıcı; API'ye sınıf/zaman gönderimi.
10. `web/src.jsx`: tek React ekranı ve rol bazlı kontroller.
11. `tests/`: çekirdek, API yetki/tekilleştirme, gerçek Modbus TCP/MQTT broker, saklama/kapasite ve dört kesinti bileşen kontrolü; Chrome üç rol smoke. `manual-camera-ui.mjs` gerçek telefonla üç React sınıfını, `manual_camera_reconnect_ui.mjs` Kopuk → Bağlı durumunu; `manual_real_disk_full.py` ayrı 2 MB Linux tmpfs üzerinde `ENOSPC` davranışını ve `manual_full_capacity.py` 86.400 kayıt sınırını denetler.
12. `host/generate_runtime.py` ve `host/run_api.py`: özel çalışma sırlarının üretilmesi ve host platformunun başlatılması.
13. `host/check_integrity.py`: gerçek VM kaynak günlükleriyle host DB'nin sıra/olay kimliği karşılaştırması (yerel doğrulama aracı).

Veri yolu: simülatör → protokol → collector → DB → API → React. Kamera yolu yalnız sınıf/zaman gönderir. Modbus/MQTT ve kesinti testleri gerçek Ubuntu WSL2 VM'de yapıldı; testlerin gerçek telefon gösterimi yerine geçmediğini belirtin.
