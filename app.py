import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
import datetime
import io
import json

# ── Cấu hình trang ──────────────────────────────────────────────
st.set_page_config(
    page_title="Xuất Kho",
    page_icon="📦",
    layout="centered",
)

# ── CSS tùy chỉnh ───────────────────────────────────────────────
st.markdown("""
<style>
    /* Tổng thể */
    .stApp { background-color: #F7F9FC; }

    /* Header */
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

    /* Card section */
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

    /* Nút gửi */
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
    }
    div.stButton > button:hover { opacity: 0.88; }

    /* Ẩn footer mặc định */
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
    """Khởi tạo Google Sheets + Drive client từ secrets."""
    creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    drive_service = build("drive", "v3", credentials=creds)
    return gc, drive_service

def upload_image_to_drive(drive_service, image_bytes, filename, folder_id):
    """Upload ảnh lên Google Drive, trả về URL xem ảnh."""
    media = MediaInMemoryUpload(image_bytes, mimetype="image/jpeg")
    file_metadata = {"name": filename, "parents": [folder_id]}
    uploaded = drive_service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()
    file_id = uploaded.get("id")
    # Đặt quyền xem công khai
    drive_service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()
    return f"https://drive.google.com/uc?id={file_id}"

def append_to_sheet(gc, spreadsheet_id, row_data):
    """Ghi một dòng mới vào Google Sheet."""
    sh = gc.open_by_key(spreadsheet_id)
    ws = sh.sheet1
    ws.append_row(row_data)

# ── Giao diện ───────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <h1>📦 Xuất Kho</h1>
    <p>Ghi nhận hàng hóa trước khi đóng thùng</p>
</div>
""", unsafe_allow_html=True)

# ── Thông tin đơn ────────────────────────────────────────────────
st.markdown('<div class="section-card"><div class="section-title">📋 Thông tin đơn</div>', unsafe_allow_html=True)

branch_options = [
    "-- Chọn chi nhánh --",
    "Chi nhánh Hà Nội",
    "Chi nhánh TP. Hồ Chí Minh",
    "Chi nhánh Đà Nẵng",
    "Chi nhánh Cần Thơ",
    "Chi nhánh Hải Phòng",
]
branch = st.selectbox("Tên chi nhánh nhận hàng", branch_options)
st.markdown('</div>', unsafe_allow_html=True)

# ── Chụp ảnh phiếu gửi hàng ─────────────────────────────────────
st.markdown('<div class="section-card"><div class="section-title">🧾 Ảnh phiếu gửi hàng</div>', unsafe_allow_html=True)
photo_bill = st.camera_input("Chụp phiếu gửi hàng")
st.markdown('</div>', unsafe_allow_html=True)

# ── Chụp ảnh hàng hóa ────────────────────────────────────────────
st.markdown('<div class="section-card"><div class="section-title">🗃️ Ảnh hàng hóa bày ra</div>', unsafe_allow_html=True)
photo_goods = st.camera_input("Chụp hàng hóa")
st.markdown('</div>', unsafe_allow_html=True)

# ── Nút gửi ─────────────────────────────────────────────────────
submit = st.button("✅ Xác nhận & Lưu")

if submit:
    # Validate
    if branch == "-- Chọn chi nhánh --":
        st.error("⚠️ Vui lòng chọn chi nhánh.")
    elif photo_bill is None:
        st.error("⚠️ Vui lòng chụp ảnh phiếu gửi hàng.")
    elif photo_goods is None:
        st.error("⚠️ Vui lòng chụp ảnh hàng hóa.")
    else:
        with st.spinner("Đang lưu..."):
            try:
                gc, drive_service = get_google_clients()

                now = datetime.datetime.now()
                timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
                date_str  = now.strftime("%Y%m%d_%H%M%S")

                folder_id      = st.secrets["GOOGLE_DRIVE_FOLDER_ID"]
                spreadsheet_id = st.secrets["GOOGLE_SHEET_ID"]

                # Upload ảnh
                url_bill = upload_image_to_drive(
                    drive_service,
                    photo_bill.getvalue(),
                    f"phieu_{branch.replace(' ', '_')}_{date_str}.jpg",
                    folder_id,
                )
                url_goods = upload_image_to_drive(
                    drive_service,
                    photo_goods.getvalue(),
                    f"hang_{branch.replace(' ', '_')}_{date_str}.jpg",
                    folder_id,
                )

                # Ghi vào Sheet
                append_to_sheet(gc, spreadsheet_id, [
                    timestamp,
                    branch,
                    url_bill,
                    url_goods,
                    st.experimental_user.get("email", "—"),  # email nếu có auth
                ])

                st.success(f"✅ Đã lưu thành công lúc {timestamp}")
                st.markdown(f"[🔗 Xem ảnh phiếu]({url_bill})　[🔗 Xem ảnh hàng]({url_goods})")

            except Exception as e:
                st.error(f"❌ Lỗi: {e}")
