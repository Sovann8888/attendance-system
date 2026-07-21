import qrcode
import io
import base64

def get_client_ip(request_obj) -> str:
    if request_obj.headers.get("X-Forwarded-For"):
        return request_obj.headers["X-Forwarded-For"].split(",")[0].strip()
    return request_obj.remote_addr

def is_school_wifi(ip: str, subnet: str, bypass: bool) -> bool:
    if bypass:
        return True
    return ip.startswith(subnet)

def make_qr_image(url: str) -> str:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a2e", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()