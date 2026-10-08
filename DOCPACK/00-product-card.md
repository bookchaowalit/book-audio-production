---
title: Book Audio Production — Product Card
doc_id: CARD-book-audio-production
doc_type: product-card
verdict: showcase
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Product owner (Book Dev)
---

# Book Audio Production — Product Card

## 1. สรุปคุณค่าในหนึ่งประโยค

ช่วยผู้ผลิตคอนเทนต์เสียงตัดและปรับ loudness ไฟล์เป็น batch ด้วย FFmpeg แบบทำซ้ำได้ ตรวจ QA และได้ manifest ที่พิสูจน์ผลได้ โดยไม่ส่งเสียงออกนอกเครื่องและไม่ใช้ AI

## 2. ปัญหาและผู้ใช้เป้าหมาย

- ปัญหา: การทำ master เสียงหลายแทร็กให้ได้ LUFS/true peak ตามเป้าแบบ manual ช้าและพิสูจน์ผลซ้ำไม่ได้
- ผู้ใช้: ผู้ทำ podcast/คอนเทนต์เสียง — ผู้ใช้จริงตอนนี้ **[ต้องยืนยัน]**

## 3. สิ่งที่ทำได้จริงตอนนี้

- CLI `book-audio run|verify|benchmark` ตาม contract `audio-batch.v1` (`schemas/`)
- ตัดตาม sample, normalize loudness, ตรวจ QA, เขียน FLAC/WAV 24-bit, `result.json` + sha256 sidecar
- replay เมื่อ input/setting เหมือนเดิม, `REPLAY_CONFLICT` เมื่อเปลี่ยน, lock + staging แบบ atomic, resource limits
- FFmpeg/FFprobe pin ใน `toolchain.lock.json`; benchmark 2026-09-25: 21 output, 0 QA failure, `model_calls=0`

## 4. หลักฐานสถานะ

| รายการ | ค่า (ตรวจจาก repository) |
|---|---|
| Stack | Python |
| Commits | 24 (แรก 2026-09-24 → ล่าสุด 2026-10-01) |
| Source | 44 ไฟล์ / 4,880 บรรทัด |
| Tests | 25 ไฟล์ |
| CI | 1 workflow |
| Deploy config | ไม่มี |
| Live URL | ไม่มี |
| README | 160 บรรทัด (`Book Audio Production`) |
| โครงสร้างซ้ำ (template family) | 1 repo ที่มี structure signature เดียวกัน |

## 5. คุณค่าและจุดต่าง

- จุดต่างจาก ffmpeg-normalize/Auphonic: replay-safe manifest, toolchain pin และ privacy (ไม่อัปโหลด) — เหมาะกับงานที่ต้องพิสูจน์ผล
- แยก contract ชัดกับ `book-production-platform` (`audio-ir.v1`) ที่ไม่ใช่ fork และมี boundary check
- มุมรายได้: ใช้ในงานผลิตคอนเทนต์ของเจ้าของเอง **[สมมติฐาน]**

## 6. ช่องว่างสำคัญ

- ยังไม่ผ่าน human listening review — README ระบุว่ายังไม่ pilot ready
- ไม่มีผู้ใช้หรือ workflow คอนเทนต์ที่เรียกใช้จริง **[ต้องยืนยัน]**
- ต้นทุนเป็นเงินยัง unknown (ไม่มี rate card)

## 7. คำตัดสิน

**`showcase`** — วิศวกรรมแข็งแรงและเป็นหลักฐาน portfolio ที่ดี แต่ยังไม่มีผู้ใช้ จะเปลี่ยนเป็น `invest` เมื่อถูกใช้ใน pipeline คอนเทนต์เสียงจริงของ Solo Empire อย่างน้อยหนึ่งงานต่อเนื่อง

## 8. ขั้นต่อไป

1. ทำ listening review ตาม `docs/engineering/2026-09-26-audio-listening-checklist.md`
2. ใช้กับงานเสียงจริงหนึ่งชุดแล้วบันทึกผล
3. รักษา boundary กับ `book-production-platform` ตาม README

## การอนุมัติ

| บทบาท | สถานะ | วันที่ | ลงนาม |
|---|---|---|---|
| Product owner (Book Dev) | รอพิจารณา | — | ________ |

## แหล่งข้อมูล

- `README.md`
- `pyproject.toml`
- `src/book_audio_production/cli.py`
- `schemas/audio-batch.v1.schema.json`
- `(book-dev) bookchaowalit/book-production-platform/README.md`
