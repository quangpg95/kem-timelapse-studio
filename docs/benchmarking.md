# Benchmarking Kem Timelapse Studio

Benchmark này đo chất lượng quyết định cắt/giữ theo thời lượng giao nhau và hiệu năng của
toàn bộ Content Pack. Báo cáo JSON có schema version để máy đọc; báo cáo Markdown đi kèm
dùng cho việc duyệt thủ công. Cả hai chỉ chứa tên file, không chứa đường dẫn đầy đủ, username,
serial number hay mẫu media.

## Bộ media sinh tự động

Yêu cầu `ffmpeg`, `ffprobe` và môi trường phát triển đã được cài đặt. Từ thư mục gốc repository:

```bash
.venv/bin/python tools/generate_test_media.py --force
```

Lệnh tạo `tests/generated_media/painting-60s.mp4` ở 4K, SDR, 30 fps cùng một clip có metadata
xoay 90° và một clip không có audio. Script in SHA-256 cho từng fixture. Media sinh ra bị Git
ignore; chỉ `tests/fixtures/golden/labels.json` được commit.

## Kiểm thử chất lượng và media

```bash
.venv/bin/pytest tests/unit/quality -q
.venv/bin/pytest tests/integration -m media -q
```

Quality gate dùng mili-giây giao nhau, không dùng số segment:

- Xoá ít nhất 80% thời lượng được gắn nhãn `inactive`.
- Giữ ít nhất 90% thời lượng được gắn nhãn `important_detail`.
- Thiếu một trong hai loại nhãn là benchmark không hợp lệ, không được tự động coi là đạt.

`source_id` trong file nhãn là stem của tên file (ví dụ `painting-60s` cho
`painting-60s.mp4`), vì vậy nhãn có thể chia sẻ mà không lộ đường dẫn hoặc phụ thuộc fingerprint
cục bộ.

## Acceptance bằng bản quay riêng tư

Đặt bản quay và nhãn ở ngoài repository rồi chạy:

```bash
export KEM_TIMELAPSE_ACCEPTANCE_SOURCE="/absolute/path/to/private-recording.mov"
export KEM_TIMELAPSE_ACCEPTANCE_LABELS="/absolute/path/to/private-labels.json"
.venv/bin/pytest tests/e2e/test_acceptance_recording.py -m e2e -q
```

Nếu thiếu một trong hai biến, test báo `private acceptance recording not configured` và skip có
chủ đích. Acceptance đầy đủ yêu cầu macOS Apple Silicon; các ngưỡng 15 phút cho output đầu và
20 phút cho đủ pack được áp dụng trên M3 Pro có ít nhất 24 GB RAM. Test đưa vào một restart khi
analysis, một restart sau TikTok, thực hiện một edit, rồi xác minh source không đổi, manifest,
codec/kích thước/fps, black-gap và A/V drift dưới 100 ms.

Có thể tạo báo cáo JSON và Markdown trực tiếp khi composition root của ứng dụng đã được cấu
hình trong tiến trình benchmark:

```bash
.venv/bin/python tools/benchmark.py \
  --source "$KEM_TIMELAPSE_ACCEPTANCE_SOURCE" \
  --labels "$KEM_TIMELAPSE_ACCEPTANCE_LABELS" \
  --project-dir benchmark-results/acceptance-project \
  --report benchmark-results/acceptance.json
```

Báo cáo ghi phiên bản ứng dụng/FFmpeg, codec và duration source, dung lượng trống, loại volume,
power source, thermal state khi hệ điều hành cung cấp được, stage timings, output probes,
warning codes, time-to-first-output và full-pack time. `not_available` là trạng thái đo hợp lệ cho
thông tin hệ điều hành không cung cấp qua API không đặc quyền.

Tỷ lệ giữ chân người xem trên 65% là KPI sau khi đăng TikTok/Reels/YouTube Shorts. Nó phụ thuộc
vào nội dung, caption, phân phối và hành vi người xem, nên không phải điều kiện pass/fail kỹ thuật
của renderer hay benchmark cục bộ.
