import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import datetime
import io
import json
from PIL import Image, ImageDraw, ImageFont

# ── Cấu hình trang ──────────────────────────────────────────────
st.set_page_config(
    page_title="Xuất Kho",
    page_icon="📦",
    layout="centered",
)

# ── CSS tùy chỉnh ───────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #F7F9FC; }

    .app-header {
        background: linear-gradient(135deg, #1B4F72, #2E86C1);
        color: white;
        padding: 20px 24px 16px;
        border-radius: 16px;
        margin-bottom: 24px;
        text-align: center;
    }
    .app-header h1 { margin: 0; font-size: 1.6rem; font-weight: 700; }
    .app-header p  { margin: 4px 0 0; font-size: 0.9rem; opacity: 0.85; }

    .section-card {
        background: white;
        border-radius: 14px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }
    .section-title {
        font-size: 0.8rem;
        font-weight: 600;
        color: #2E86C1;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 12px;
    }

    .progress-bar-bg {
        background: #E8F4FD;
        border-radius: 8px;
        height: 8px;
        margin: 8px 0 16px;
        overflow: hidden;
    }
    .progress-bar-fill {
        background: linear-gradient(90deg, #1B4F72, #2E86C1);
        height: 100%;
        border-radius: 8px;
        transition: width 0.3s ease;
    }

    div.stButton > button {
        width: 100%;
        background: linear-gradient(135deg, #1B4F72, #2E86C1);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 14px;
        font-size: 1rem;
        font-weight: 600;
        letter-spacing: 0.03em;
        cursor: pointer;
        transition: opacity 0.2s;
        margin-bottom: 8px;
    }
    div.stButton > button:hover { opacity: 0.88; }

    .thumb-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 8px;
    }
    .thumb-item {
        width: 60px;
        height: 60px;
        border-radius: 8px;
        overflow: hidden;
        border: 2px solid #2E86C1;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
        background: #E8F4FD;
    }

    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Kết nối Google ───────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

@st.cache_resource
def get_google_clients():
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    drive_service = build("drive", "v3", credentials=creds)
    return gc, drive_service

def add_watermark(image_bytes, text_lines):
    import requests, os
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    font_size = max(30, img.width // 45)
    
    font = None
    font_path = "/tmp/arialbd.ttf"
    
    # Tải font về /tmp nếu chưa có
    if not os.path.exists(font_path):
        try:
            r = requests.get(
                "https://github.com/matomo-org/travis-scripts/raw/master/fonts/Arial.ttf",
                timeout=5
            )
            with open(font_path, "wb") as f:
                f.write(r.content)
        except:
            pass
    
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()

    x0, y0 = 24, 24
    line = text_lines[0]
    for dx, dy in [(-3,-3),(3,-3),(-3,3),(3,3)]:
        draw.text((x0+dx, y0+dy), line, font=font, fill=(0,0,0))
    draw.text((x0, y0), line, font=font, fill=(255,255,255))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()
def upload_image_to_drive(drive_service, image_bytes, filename, folder_id, watermark_lines=None):
    if watermark_lines:
        image_bytes = add_watermark(image_bytes, watermark_lines)
    media = MediaInMemoryUpload(image_bytes, mimetype="image/jpeg")
    file_metadata = {"name": filename, "parents": [folder_id]}
    uploaded = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    file_id = uploaded.get("id")
    drive_service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
        supportsAllDrives=True,
    ).execute()
    return f"https://drive.google.com/uc?id={file_id}"

def finalize_to_sheet(gc, spreadsheet_id, branch, timestamp, image_urls):
    sh = gc.open_by_key(spreadsheet_id)
    ws = sh.sheet1

    all_values = ws.get_all_values()
    next_row = len(all_values) + 1

    # Tạo 1 dòng 18 cột (A..R), điền trống trước
    row = [""] * 18
    row[0] = timestamp   # A
    row[1] = branch      # B

    col_letters = {0:"C", 2:"E", 4:"G", 6:"I", 8:"K", 10:"M", 12:"O", 14:"Q"}
    link_positions = [2, 4, 6, 8, 10, 12, 14, 16]  # C=2, E=4, G=6...

    for i, url in enumerate(image_urls):
        lp = link_positions[i]
        row[lp] = url
        row[lp + 1] = f'=IMAGE({list(col_letters.values())[i]}{next_row})'

    ws.append_row(row, value_input_option="USER_ENTERED")
def upload_all_and_finalize(drive_service, gc, folder_id, spreadsheet_id, branch, session_ts, photos_bytes):
    import concurrent.futures
    timestamp = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
    branch_slug = branch.replace(" ", "_")

    def upload_one(args):
        i, img_bytes = args
        now_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
        filename = f"anh{i+1}_{branch_slug}_{session_ts}.jpg"
        return i, upload_image_to_drive(drive_service, img_bytes, filename, folder_id, watermark_lines=[now_str])

    urls = [None] * len(photos_bytes)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for i, url in executor.map(upload_one, enumerate(photos_bytes)):
            urls[i] = url

    finalize_to_sheet(gc, spreadsheet_id, branch, timestamp, urls)
    return urls
# ── Session state ────────────────────────────────────────────────
if "saved_urls" not in st.session_state:
    st.session_state.saved_urls = []          # list of uploaded Drive URLs
if "saved_bytes" not in st.session_state:
    st.session_state.saved_bytes = []         # list of image bytes (for thumbnail)
if "session_done" not in st.session_state:
    st.session_state.session_done = False
if "branch" not in st.session_state:
    st.session_state.branch = "-- Chọn chi nhánh --"
if "session_ts" not in st.session_state:
    st.session_state.session_ts = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y%m%d_%H%M%S")

MAX_PHOTOS = 8

# ── Header ───────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <h1>📦 Xuất Kho</h1>
    <p>Ghi nhận hàng hóa trước khi đóng thùng</p>
</div>
""", unsafe_allow_html=True)

# ── Nếu phiên đã hoàn tất ────────────────────────────────────────
if st.session_state.session_done:
    st.success(f"✅ Đã hoàn tất! Đã lưu {len(st.session_state.saved_urls)} ảnh.")
    if st.button("🔄 Bắt đầu phiên mới"):
        st.session_state.saved_urls  = []
        st.session_state.saved_bytes = []
        st.session_state.session_done = False
        st.session_state.branch = "-- Chọn chi nhánh --"
        st.session_state.session_ts = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y%m%d_%H%M%S")
        st.rerun()
    st.stop()

# ── Chọn chi nhánh (chỉ hiện khi chưa có ảnh nào) ───────────────
if len(st.session_state.saved_urls) == 0:
    st.markdown('<div class="section-card"><div class="section-title">📋 Thông tin đơn</div>', unsafe_allow_html=True)
    branch_options = [
        "-- Chọn chi nhánh --",
        "Chi nhánh Hà Nội",
        "Chi nhánh TP. Hồ Chí Minh",
        "Chi nhánh Đà Nẵng",
        "Chi nhánh Cần Thơ",
        "Chi nhánh Hải Phòng",
    ]
    st.session_state.branch = st.selectbox("Tên chi nhánh nhận hàng", branch_options)
    st.markdown('</div>', unsafe_allow_html=True)

# ── Tiến trình ───────────────────────────────────────────────────
count = len(st.session_state.saved_urls)
if count > 0:
    pct = int(count / MAX_PHOTOS * 100)
    st.markdown(f"""
    <div style="margin-bottom:4px; font-size:0.85rem; color:#555;">
        📸 Đã chụp: <b>{count}/{MAX_PHOTOS}</b> ảnh
    </div>
    <div class="progress-bar-bg">
        <div class="progress-bar-fill" style="width:{pct}%"></div>
    </div>
    """, unsafe_allow_html=True)

    # Thumbnail các ảnh đã lưu
    cols = st.columns(min(count, 8))
    for i, img_bytes in enumerate(st.session_state.saved_bytes):
        with cols[i]:
            st.image(img_bytes, width=60, caption=f"#{i+1}")

# ── Chụp ảnh mới (nếu chưa đủ 8) ───────────────────────────────
if count < MAX_PHOTOS:
    st.markdown(f'<div class="section-card"><div class="section-title">📷 Chụp ảnh #{count + 1}</div>', unsafe_allow_html=True)
    photo = st.camera_input(f"Ảnh thứ {count + 1}", key=f"cam_{count}")
    st.markdown('</div>', unsafe_allow_html=True)

    if photo is not None:
        # Nút Lưu ảnh này
        col1, col2 = st.columns(2)

        with col1:
            if st.button(f"💾 Lưu ảnh #{count + 1}"):
                if st.session_state.branch == "-- Chọn chi nhánh --":
                    st.error("⚠️ Vui lòng chọn chi nhánh trước.")
                else:
                    st.session_state.saved_bytes.append(photo.getvalue())
                    st.session_state.saved_urls.append(f"__pending__")
                    st.rerun()

        with col2:
            if st.button("🏁 Hoàn tất ngay"):
                if st.session_state.branch == "-- Chọn chi nhánh --":
                    st.error("⚠️ Vui lòng chọn chi nhánh trước.")
                elif len(st.session_state.saved_bytes) == 0 and photo is None:
                    st.error("⚠️ Chưa có ảnh nào.")
                else:
                    if photo is not None and len(st.session_state.saved_bytes) == count:
                        st.session_state.saved_bytes.append(photo.getvalue())
                    with st.spinner("Đang upload & lưu..."):
                        try:
                            gc, drive_service = get_google_clients()
                            urls = upload_all_and_finalize(
                                drive_service, gc,
                                st.secrets["GOOGLE_DRIVE_FOLDER_ID"],
                                st.secrets["GOOGLE_SHEET_ID"],
                                st.session_state.branch,
                                st.session_state.session_ts,
                                st.session_state.saved_bytes,
                            )
                            st.session_state.saved_urls = urls
                            st.session_state.session_done = True
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Lỗi: {e}")

# ── Nút Hoàn tất (khi đã có ≥1 ảnh lưu, không có ảnh mới đang chờ) ──
elif count > 0:
    # Đã đủ 8 ảnh
    st.info("📸 Đã đủ 8 ảnh tối đa.")
    if st.button("🏁 Hoàn tất & Lưu vào Sheet"):
        with st.spinner("Đang upload & lưu..."):
            try:
                gc, drive_service = get_google_clients()
                urls = upload_all_and_finalize(
                    drive_service, gc,
                    st.secrets["GOOGLE_DRIVE_FOLDER_ID"],
                    st.secrets["GOOGLE_SHEET_ID"],
                    st.session_state.branch,
                    st.session_state.session_ts,
                    st.session_state.saved_bytes,
                )
                st.session_state.saved_urls = urls
                st.session_state.session_done = True
                st.rerun()
            except Exception as e:
                st.error(f"❌ Lỗi: {e}")

# ── Nút Hoàn tất sớm (hiện khi đã có ≥1 ảnh, đang ở màn chụp) ──
if 0 < count < MAX_PHOTOS and count == len(st.session_state.saved_urls):
    st.markdown("---")
    if st.button(f"🏁 Hoàn tất với {count} ảnh đã lưu"):
        with st.spinner("Đang upload & lưu..."):
            try:
                gc, drive_service = get_google_clients()
                urls = upload_all_and_finalize(
                    drive_service, gc,
                    st.secrets["GOOGLE_DRIVE_FOLDER_ID"],
                    st.secrets["GOOGLE_SHEET_ID"],
                    st.session_state.branch,
                    st.session_state.session_ts,
                    st.session_state.saved_bytes,
                )
                st.session_state.saved_urls = urls
                st.session_state.session_done = True
                st.rerun()
            except Exception as e:
                st.error(f"❌ Lỗi: {e}")
st.markdown("""
<script>
async function switchToBackCamera() {
    await new Promise(r => setTimeout(r, 1000));
    const videos = document.querySelectorAll('video');
    for (const video of videos) {
        if (video.srcObject) {
            video.srcObject.getTracks().forEach(t => t.stop());
        }
    }
    const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { exact: "environment" } }
    });
    for (const video of videos) {
        video.srcObject = stream;
    }
}
switchToBackCamera();
</script>
""", unsafe_allow_html=True)
