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
    """
    Ghi 1 dòng vào sheet:
    A = Thời gian, B = Trung Tâm/Chi nhánh
    C = url1, D = =IMAGE(C?), E = url2, F = =IMAGE(E?), ...
    Tối đa 8 ảnh → cột C..R
    """
    sh = gc.open_by_key(spreadsheet_id)
    ws = sh.sheet1

    # Tìm dòng tiếp theo trống
    all_values = ws.get_all_values()
    next_row = len(all_values) + 1

    # Cột link: C=3, E=5, G=7, I=9, K=11, M=13, O=15, Q=17
    link_cols = [3, 5, 7, 9, 11, 13, 15, 17]

    # Ghi Thời gian (A) và Chi nhánh (B)
    ws.update_cell(next_row, 1, timestamp)
    ws.update_cell(next_row, 2, branch)

    col_letters = {3:"C", 5:"E", 7:"G", 9:"I", 11:"K", 13:"M", 15:"O", 17:"Q"}

    for i, url in enumerate(image_urls):
        link_col = link_cols[i]
        img_col  = link_col + 1  # D, F, H, J, L, N, P, R
        letter   = col_letters[link_col]

        ws.update_cell(next_row, link_col, url)
        ws.update_cell(next_row, img_col, f'=IMAGE({letter}{next_row})')

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
        st.session_state.session_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
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
                    with st.spinner("Đang upload ảnh..."):
                        try:
                            gc, drive_service = get_google_clients()
                            folder_id = st.secrets["GOOGLE_DRIVE_FOLDER_ID"]
                            branch_slug = st.session_state.branch.replace(" ", "_")
                            filename = f"anh{count+1}_{branch_slug}_{st.session_state.session_ts}.jpg"
                            now_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
                            watermark = [now_str]
                            url = upload_image_to_drive(
                                drive_service,
                                photo.getvalue(),
                                filename,
                                folder_id,
                                watermark_lines=watermark,
                            )
                            st.session_state.saved_urls.append(url)
                            st.session_state.saved_bytes.append(photo.getvalue())
                            st.success(f"✅ Đã lưu ảnh #{count + 1}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Lỗi upload: {e}")

        with col2:
            if st.button("🏁 Hoàn tất ngay"):
                if st.session_state.branch == "-- Chọn chi nhánh --":
                    st.error("⚠️ Vui lòng chọn chi nhánh trước.")
                elif len(st.session_state.saved_urls) == 0 and photo is None:
                    st.error("⚠️ Chưa có ảnh nào được lưu.")
                else:
                    with st.spinner("Đang hoàn tất..."):
                        try:
                            gc, drive_service = get_google_clients()
                            folder_id = st.secrets["GOOGLE_DRIVE_FOLDER_ID"]
                            spreadsheet_id = st.secrets["GOOGLE_SHEET_ID"]

                            urls = list(st.session_state.saved_urls)

                            # Nếu ảnh hiện tại chưa lưu, upload luôn
                            if photo is not None and len(urls) == count:
                                branch_slug = st.session_state.branch.replace(" ", "_")
                                filename = f"anh{count+1}_{branch_slug}_{st.session_state.session_ts}.jpg"
                                now_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
                                watermark = [now_str]
                                url = upload_image_to_drive(
                                    drive_service,
                                    photo.getvalue(),
                                    filename,
                                    folder_id,
                                    watermark_lines=watermark,
                                )
                                urls.append(url)
                                st.session_state.saved_bytes.append(photo.getvalue())

                            timestamp = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
                            finalize_to_sheet(
                                gc,
                                spreadsheet_id,
                                st.session_state.branch,
                                timestamp,
                                urls,
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
        with st.spinner("Đang lưu vào Google Sheet..."):
            try:
                gc, _ = get_google_clients()
                spreadsheet_id = st.secrets["GOOGLE_SHEET_ID"]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                finalize_to_sheet(
                    gc,
                    spreadsheet_id,
                    st.session_state.branch,
                    timestamp,
                    st.session_state.saved_urls,
                )
                st.session_state.session_done = True
                st.rerun()
            except Exception as e:
                st.error(f"❌ Lỗi: {e}")

# ── Nút Hoàn tất sớm (hiện khi đã có ≥1 ảnh, đang ở màn chụp) ──
if 0 < count < MAX_PHOTOS and count == len(st.session_state.saved_urls):
    st.markdown("---")
    if st.button(f"🏁 Hoàn tất với {count} ảnh đã lưu"):
        with st.spinner("Đang lưu vào Google Sheet..."):
            try:
                gc, _ = get_google_clients()
                spreadsheet_id = st.secrets["GOOGLE_SHEET_ID"]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                finalize_to_sheet(
                    gc,
                    spreadsheet_id,
                    st.session_state.branch,
                    timestamp,
                    st.session_state.saved_urls,
                )
                st.session_state.session_done = True
                st.rerun()
            except Exception as e:
                st.error(f"❌ Lỗi: {e}")
