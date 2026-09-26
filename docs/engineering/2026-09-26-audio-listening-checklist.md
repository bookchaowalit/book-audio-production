# เช็กลิสต์ฟังด้วยหู — Book Audio Production V1A

สร้าง: 2026-09-26 · สถานะปัจจุบัน: **รอเจ้าของฟังด้วยหู** (ยังไม่ pilot-ready — การเปลี่ยนสถานะเป็นขั้น T3.3 ของเจ้าของตาม roadmap)

ทุก track ในชุดนี้ผ่าน pipeline จริงของเครื่องมือ (`book-audio run` recipe `audio-v1a.2`,
เป้าหมาย -16 LUFS / -1 dBTP) และผ่าน `book-audio verify` ครบ 8/8 ไฟล์

## วิธีใช้เช็กลิสต์

1. ฟังด้วยหูฟังและลำโพงที่ใช้งานจริง อย่างน้อยอย่างละหนึ่งรอบ
2. ฟังเทียบ "ต้นทาง (source)" กับ "ผลงาน (master)" ของแต่ละ track ในลำโพงเดียวกัน
   ระดับเสียงปรับเท่ากันด้วยหู (อย่าเพิ่งดูตัวเลขก่อนตัดสิน)
3. ติ๊ก `[x]` ในช่องผ่าน/ไม่ผ่านของแต่ละ track พร้อมหมายเหตุสั้น ๆ
4. ไฟล์ทั้งหมดอยู่ใน `.runtime/` ซึ่งไม่ถูก commit หากลบหายต้องรัน batch ใหม่จาก manifest
   `.runtime/listening-set-20260926/batch.json` (ต้นทางเดิมที่ `input/`)
5. ห้ามเปลี่ยนสถานะ pilot-ready จนกว่าเจ้าของฟังครบและบันทึกผลในขั้น T3.3 เอง

## ที่อยู่ไฟล์

- รากของชุดฟัง:
  `C:\Users\bookc\.copilot\repos\solo-empire\projects\product\engineering\book-dev\github\bookchaowalit\book-apps\tools\book-audio-production\.runtime\listening-set-20260926`
- ต้นทาง: `.runtime\listening-set-20260926\input\`
- ผลงานที่ผ่าน QA: `.runtime\listening-set-20260926\output\listening-set-20260926\artifacts\`
- manifest ผลรัน: `.runtime\listening-set-20260926\output\listening-set-20260926\result.json`
  (เทียบ checksum ได้จาก `result.json.sha256`)

## ตัวเลขวัดล่วงหน้า (สำหรับเทียบกับสิ่งที่ได้ยิน)

วัดด้วย `ffmpeg -af ebur128=peak=true,astats` แยกจากตัวเครื่องมือ
(I = integrated LUFS, TP = true peak dBTP, LRA = loudness range LU,
PC = "Peak count" จาก astats คือจำนวน sample ที่อยู่ที่ระดับสูงสุดของไฟล์ —
ทุกผลงานมี peak ต่ำกว่า 0 dBFS จึงไม่มี clipping ดิจิทัลเชิงตัวเลข)

| track | ความยาว (s) | I ต้นทาง | I ผลงาน | TP ต้นทาง | TP ผลงาน | LRA ผลงาน | PC ผลงาน |
|---|---|---|---|---|---|---|---|
| speech-flite-en | 8.47 | -16.77 | -16.2 | -3.09 | -2.3 | 1.8 | 2 |
| speech-sapi-en | 15.18 | -26.83 | -16.0 | -12.77 | -1.9 | 2.0 | 172 |
| speech-sapi-en-quiet | 15.18 | -38.83 | -16.0 | -24.77 | -1.9 | 2.0 | 174 |
| music-arp | 9.60 | -28.74 | -16.0 | -27.09 | -14.4 | 0.1 | 3188 |
| music-bass | 12.00 | -31.28 | -16.0 | -26.20 | -10.9 | 0.0 | 3 |
| noise-pink | 10.00 | -20.70 | -15.9 | -10.38 | -5.7 | 0.1 | 2 |
| stress-hot-sine | 8.00 | -0.35 | -16.0 | +0.02 | -15.6 | 0.0 | 193 |
| stress-spikes | 12.60 | -18.11 | -16.0 | -12.06 | -10.0 | 20.2 | 238 |

## รายการฟัง (8 track)

เส้นทางย่อในตารางอยู่ใต้รากของชุดฟังตามหัวข้อ "ที่อยู่ไฟล์" ด้านบน

### 1. speech-flite-en — เสียงพูดอังกฤษ (libflite, เสียงหญิง slt)

- ต้นทาง: `input\speech-en-flite.wav`
- ผลงาน: `output\listening-set-20260926\artifacts\speech-flite-en-359b269211a9.flac`
- ฟังอะไร: ความชัดของพยัญชนะท้ายคำ (t, s, k), เสียงพูดดังพอดีหรือเบือ/ดังเกิน,
  เสียงแปลก ๆ ตอนต้น/จบไฟล์
- ตัวเลขอ้างอิง: I -16.2 LUFS, TP -2.3 dBTP
- ผมฟังแล้ว: `[ ]` ผ่าน `[ ]` ไม่ผ่าน — หมายเหตุ: ______

### 2. speech-sapi-en — เสียงพูดอังกฤษ (Windows SAPI เสียงหญิง Zira, ผ่าน compressor/limiter)

- ต้นทาง: `input\speech-en-sapi.wav`
- ผลงาน: `output\listening-set-20260926\artifacts\speech-sapi-en-3019742622a7.flac`
- ฟังอะไร: ความเป็นธรรมชาติของเสียงพูดหลัง normalization, พยัญชนะเพี้ยนหรือถูก "บีบ",
  จังหวะเงียบระหว่างประโยคผิดปกติ
- ตัวเลขอ้างอิง: I -16.0 LUFS, TP -1.9 dBTP
- ผมฟังแล้ว: `[ ]` ผ่าน `[ ]` ไม่ผ่าน — หมายเหตุ: ______

### 3. speech-sapi-en-quiet — เสียงพูดเดิมแต่ต้นทางเบามาก (ยกขึ้น ~22 dB)

- ต้นทาง: `input\speech-en-sapi-quiet.wav`
- ผลงาน: `output\listening-set-20260926\artifacts\speech-sapi-en-quiet-39fb25ae860b.flac`
- ฟังอะไร: มีเสียงฮึม/hiss พื้นหลังถูกยกมาดังเกินไปหรือไม่, เสียงพูดชัดเท่า track 2 หรือไม่
  (ทั้งสอง track มีต้นทางเดียวกัน ต่างกันแค่ระดับเสียงต้นทาง)
- ตัวเลขอ้างอิง: I -16.0 LUFS, TP -1.9 dBTP (ต้นทาง I -38.8 → ยกขึ้น ~22 dB)
- ผมฟังแล้ว: `[ ]` ผ่าน `[ ]` ไม่ผ่าน — หมายเหตุ: ______

### 4. music-arp — เพลงสังเคราะห์ (อาร์เปจโจ A minor pentatonic, สเตอริโอ)

- ต้นทาง: `input\music-arp.wav`
- ผลงาน: `output\listening-set-20260926\artifacts\music-arp-8789f852ac64.flac`
- ฟังอะไร: โน้ตแต่ละตัวยังกังวานครบหรือถูกตัดหางผิดจังหวะ, ระดับเสียงเพลง "อิ่มหู"
  ที่ -16 LUFS หรือรู้สึกแบน/เบือ, เสียงตอนต้น-จบของลูป
- ตัวเลขอ้างอิง: I -16.0 LUFS, TP -14.4 dBTP (ห่างจากเพดานมาก — คาดหวังให้ฟังแล้ว "เบากว่า" เพลงทั่วไป)
- ผมฟังแล้ว: `[ ]` ผ่าน `[ ]` ไม่ผ่าน — หมายเหตุ: ______

### 5. music-bass — เพลงเน้นเบส (55/110/220 Hz + tremolo, สเตอริโอ)

- ต้นทาง: `input\music-bass.wav`
- ผลงาน: `output\listening-set-20260926\artifacts\music-bass-f4ee8b025539.flac`
- ฟังอะไร: เบสเบา/ดังสมดุลกับช่วงเสียงบน, เครื่องมือใช้ normalization แบบ dynamic
  กับ track นี้ — ฟังว่ามี "หายใจ" (pumping) ของระดับเสียงหรือไม่
- ตัวเลขอ้างอิง: I -16.0 LUFS, TP -10.9 dBTP
- ผมฟังแล้ว: `[ ]` ผ่าน `[ ]` ไม่ผ่าน — หมายเหตุ: ______

### 6. noise-pink — pink noise (สเตอริโอ, กรณีทั่วไป)

- ต้นทาง: `input\noise-pink.wav`
- ผลงาน: `output\listening-set-20260926\artifacts\noise-pink-1fab46df1843.flac`
- ฟังอะไร: นอยส์ควรฟังต่อเนื่องสม่ำเสมอ ไม่มีจุดสะดุด/เสียงคลิกรัว ตอนต้น-จบไฟล์
- ตัวเลขอ้างอิง: I -15.9 LUFS, TP -5.7 dBTP
- ผมฟังแล้ว: `[ ]` ผ่าน `[ ]` ไม่ผ่าน — หมายเหตุ: ______

### 7. stress-hot-sine — ต้นทางดังจนคลิปแล้ว (0 dBFS, WAV 24-bit PCM)

- ต้นทาง: `input\stress-hot-sine.wav` (ต้นทางถูก clip หนัก TP +0.02 dBTP)
- ผลงาน: `output\listening-set-20260926\artifacts\stress-hot-sine-5406a4adb01e.wav`
- ฟังอะไร: เครื่องมือลดระดับลง ~16 dB แล้วโทน 440 Hz ยังสะอาดหรือมีเสียงหึ่ง/ผิดเพี้ยน
  จากการ clip ที่ติดมากับต้นทาง, ตอนต้น/จบไฟล์มี pop หรือไม่
- ตัวเลขอ้างอิง: I -16.0 LUFS, TP -15.6 dBTP
- ผมฟังแล้ว: `[ ]` ผ่าน `[ ]` ไม่ผ่าน — หมายเหตุ: ______

### 8. stress-spikes — นอยส์เงยกับเสียง burst ดังสลับกัน (LRA ~20 LU)

- ต้นทาง: `input\stress-spikes.wav`
- ผลงาน: `output\listening-set-20260926\artifacts\stress-spikes-cf8914b37136.flac`
- ฟังอะไร: ช่วงเงียบควรยังเงียบจริง ช่วง burst ไม่แตกพร่า, การข้ามผ่านจุดตัด
  ระหว่างช่วงเงียบกับ burst มีเสียงคลิกหรือไม่, ระดับรวมพอดีหรือช่วงเงียบดังเกิน
- ตัวเลขอ้างอิง: I -16.0 LUFS, TP -10.0 dBTP, LRA 20.2 LU
- ผมฟังแล้ว: `[ ]` ผ่าน `[ ]` ไม่ผ่าน — หมายเหตุ: ______

## กรณีที่เครื่องมือปฏิเสธ (ข้อค้นพบ ไม่ใช่ไฟล์สำหรับฟัง)

ต้นทางสองตัวนี้ถูก QA ของเครื่องมือปฏิเสธ (`QA_FAILED`) อย่างถูกต้องตามกติกา:

- `input\speech-en-sapi-hot.wav` — เสียงพูด SAPI ดิบ peak -0.1 dBTP
- `input\stress-spikes-hot.wav` — burst ดังระดับ +0.1 dBTP

สาเหตุ (ทดสอบซ้ำด้วย recipe เดียวกัน): ต้นทางที่ร้อนเกินบังคับให้ loudnorm
ลง dynamic mode แล้ว integrated loudness ผลลัพธ์พลาดเป้าเกิน ±0.5 LU
(เสียงพูดได้ -17.4 LUFS, spikes ได้ -14.6 LUFS เมื่อเป้าคือ -16)
ผลรันบันทึกไว้ที่ `output\reject-probe-20260926\result.json`
→ เป็นข้อจำกัดผลิตภัณฑ์ที่ควรนำไปคิดต่อใน T3.3 (แก้ tolerance, คู่มือการใช้
หรือ pre-gain) ไม่ใช่ความผิดของชุดฟัง

## ข้อจำกัดของชุดฟังนี้

- **ยังไม่มีเสียงพูดไทย** — เครื่องนี้ไม่มี TTS เสียงไทย (Windows SAPI มีเฉพาะ
  `en-US`: David/Zira, libflite ของ FFmpeg รองรับเฉพาะภาษาอังกฤษ)
  เมื่อมีไฟล์เสียงพูดไทยจริง (เจ้าของอัดเอง หรือติดตั้ง Thai voice) ให้เตรียมต้นทาง
  ใส่ `input/` เพิ่มแถวใน `.runtime/listening-set-20260926/batch.json`
  แล้วรัน `book-audio run` ซ้ำ และเพิ่มรายการฟังเรื่อง สระ/วรรณยุกต์ไทยผิดปกติ
- เพลงทั้งหมดเป็นสังเคราะห์ล้วน ไม่แทนเพลงจริงที่มีไดนามิกส์ซับซ้อน
- ชุดนี้ไม่มีไฟล์ใดถูก commit — อยู่ใน `.runtime/` เท่านั้น

## หลังฟังครบ

- สรุปผล pass/fail ต่อ track ลง roadmap ขั้น T3.3 แล้วจึงตัดสิน pilot-ready
  หรือเปิด fix ticket (โดยเจ้าของเท่านั้น)
