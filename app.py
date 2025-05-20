from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime
import sqlite3
import qrcode
import io
import base64
import hashlib
import hmac
import urllib.parse

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Cấu hình VNPay
VNPAY_CONFIG = {
    'vnp_TmnCode': 'YOUR_MERCHANT_CODE',  # Mã website tại VNPAY 
    'vnp_HashSecret': 'YOUR_HASH_SECRET',  # Chuỗi bí mật
    'vnp_Url': 'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html',
    'vnp_ReturnUrl': 'http://localhost:5000/payment/vnpay_return',  # URL nhận kết quả
    'vnp_Command': 'pay',
    'vnp_CurrCode': 'VND',
    'vnp_Locale': 'vn',
    'vnp_Version': '2.1.0'
}

# Khởi tạo database
def init_db():
    with sqlite3.connect('hotel.db') as conn:
        cursor = conn.cursor()
        # Bảng phòng
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                room_number TEXT PRIMARY KEY,
                guest_name TEXT,
                check_in_date TEXT,
                status TEXT
            )
        ''')
        # Bảng hóa đơn
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_code TEXT UNIQUE,
                room_number TEXT,
                total_amount REAL,
                status TEXT,
                FOREIGN KEY (room_number) REFERENCES rooms (room_number)
            )
        ''')
        # Bảng dịch vụ
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER,
                service_name TEXT,
                amount REAL,
                FOREIGN KEY (invoice_id) REFERENCES invoices (id)
            )
        ''')
        # Xóa dữ liệu cũ để reset mẫu
        cursor.execute('DELETE FROM services')
        cursor.execute('DELETE FROM invoices')
        cursor.execute('DELETE FROM rooms')
        
        # Thêm dữ liệu mẫu hợp lý hơn
        cursor.execute("INSERT INTO rooms VALUES ('101', 'Nguyen Van A', '2024-06-01', 'occupied')")
        cursor.execute("INSERT INTO rooms VALUES ('102', 'Tran Thi B', '2024-06-02', 'occupied')")
        cursor.execute("INSERT INTO rooms VALUES ('103', 'Le Van C', '2024-06-03', 'available')")
        cursor.execute("INSERT INTO rooms VALUES ('104', 'Pham Thi D', '2024-06-04', 'occupied')")
        cursor.execute("INSERT INTO rooms VALUES ('105', 'Vo Van E', '2024-06-05', 'available')")
        
        # Hóa đơn cho các phòng đang occupied với mã hóa đơn mới
        cursor.execute("INSERT INTO invoices (invoice_code, room_number, total_amount, status) VALUES ('HD01', '101', 2500000, 'pending')")
        invoice_id_1 = cursor.lastrowid
        cursor.execute("INSERT INTO invoices (invoice_code, room_number, total_amount, status) VALUES ('HD02', '102', 3200000, 'pending')")
        invoice_id_2 = cursor.lastrowid
        cursor.execute("INSERT INTO invoices (invoice_code, room_number, total_amount, status) VALUES ('HD03', '104', 2800000, 'pending')")
        invoice_id_3 = cursor.lastrowid
        
        # Dịch vụ cho hóa đơn HD01 (Phòng 101)
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Room Charge', 1500000)", (invoice_id_1,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Breakfast', 200000)", (invoice_id_1,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Laundry', 300000)", (invoice_id_1,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Mini Bar', 200000)", (invoice_id_1,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Spa', 300000)", (invoice_id_1,))
        
        # Dịch vụ cho hóa đơn HD02 (Phòng 102)
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Room Charge', 2000000)", (invoice_id_2,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Breakfast', 200000)", (invoice_id_2,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Dinner', 500000)", (invoice_id_2,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Laundry', 300000)", (invoice_id_2,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Airport Transfer', 200000)", (invoice_id_2,))
        
        # Dịch vụ cho hóa đơn HD03 (Phòng 104)
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Room Charge', 1800000)", (invoice_id_3,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Breakfast', 200000)", (invoice_id_3,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Lunch', 400000)", (invoice_id_3,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Spa', 300000)", (invoice_id_3,))
        cursor.execute("INSERT INTO services (invoice_id, service_name, amount) VALUES (?, 'Gym', 100000)", (invoice_id_3,))
        
        conn.commit()


# Trang tìm kiếm hóa đơn
@app.route('/', methods=['GET', 'POST'])
def search_room():
    invoices = []
    if request.method == 'POST':
        invoice_code = request.form.get('invoice_code', '').strip().upper()
        with sqlite3.connect('hotel.db') as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT i.invoice_code, i.room_number, i.total_amount, i.status,
                       r.guest_name, r.check_in_date
                FROM invoices i
                JOIN rooms r ON i.room_number = r.room_number
                WHERE i.invoice_code LIKE ? AND i.status = 'pending'
            """, ('%' + invoice_code + '%',))
            invoices = cursor.fetchall()
        if not invoices:
            flash('Không tìm thấy hóa đơn')
    return render_template('search_room.html', invoices=invoices)


# Trang xem chi tiết hóa đơn
@app.route('/invoice/<invoice_code>')
def view_invoice(invoice_code):
    with sqlite3.connect('hotel.db') as conn:
        cursor = conn.cursor()
        # Lấy thông tin hóa đơn
        cursor.execute("""
            SELECT i.id, i.invoice_code, i.room_number, i.total_amount, i.status, 
                   r.guest_name, r.check_in_date,
                   (SELECT COUNT(*) FROM services WHERE invoice_id = i.id) as service_count
            FROM invoices i
            JOIN rooms r ON i.room_number = r.room_number
            WHERE i.invoice_code = ? AND i.status = 'pending'
        """, (invoice_code,))
        invoice = cursor.fetchone()
        
        if not invoice:
            flash('Không tìm thấy hóa đơn!')
            return redirect(url_for('search_room'))

        # Lấy thông tin chi tiết dịch vụ
        cursor.execute("""
            SELECT service_name, amount, 
                   CASE 
                       WHEN service_name = 'Room Charge' THEN 'Tiền phòng'
                       WHEN service_name = 'Breakfast' THEN 'Ăn sáng'
                       WHEN service_name = 'Laundry' THEN 'Giặt ủi'
                       WHEN service_name = 'Spa' THEN 'Dịch vụ spa'
                       ELSE service_name
                   END as service_name_vn
            FROM services 
            WHERE invoice_id = ?
            ORDER BY 
                CASE 
                    WHEN service_name = 'Room Charge' THEN 1
                    ELSE 2
                END,
                service_name
        """, (invoice[0],))
        services = cursor.fetchall()

        # Tính tổng tiền dịch vụ
        total_services = sum(service[1] for service in services)
        
        # Tạo dictionary chứa thông tin hóa đơn
        invoice_data = {
            'id': invoice[0],
            'invoice_code': invoice[1],
            'room_number': invoice[2],
            'total_amount': invoice[3],
            'status': invoice[4],
            'guest_name': invoice[5],
            'check_in_date': invoice[6],
            'service_count': invoice[7],
            'services': services,
            'total_services': total_services
        }

        return render_template('invoice.html', invoice=invoice_data)


# Hàm tạo URL thanh toán VNPay
def create_vnpay_payment_url(invoice_code, amount):
    vnp_TmnCode = VNPAY_CONFIG['vnp_TmnCode']
    vnp_HashSecret = VNPAY_CONFIG['vnp_HashSecret']
    vnp_Url = VNPAY_CONFIG['vnp_Url']
    vnp_ReturnUrl = VNPAY_CONFIG['vnp_ReturnUrl']
    vnp_Command = VNPAY_CONFIG['vnp_Command']
    vnp_CurrCode = VNPAY_CONFIG['vnp_CurrCode']
    vnp_Locale = VNPAY_CONFIG['vnp_Locale']
    vnp_Version = VNPAY_CONFIG['vnp_Version']
    
    # Tạo các tham số thanh toán
    vnp_Params = {
        'vnp_Version': vnp_Version,
        'vnp_Command': vnp_Command,
        'vnp_TmnCode': vnp_TmnCode,
        'vnp_Amount': str(int(amount * 100)),  # Số tiền * 100
        'vnp_CurrCode': vnp_CurrCode,
        'vnp_Locale': vnp_Locale,
        'vnp_ReturnUrl': vnp_ReturnUrl,
        'vnp_OrderInfo': f'Thanh toan hoa don {invoice_code}',
        'vnp_OrderType': 'billpayment',
        'vnp_TxnRef': invoice_code,
        'vnp_CreateDate': datetime.now().strftime('%Y%m%d%H%M%S')
    }
    
    # Sắp xếp các tham số theo thứ tự a-z
    vnp_Params = sorted(vnp_Params.items())
    
    # Tạo chuỗi hash data
    hashdata = '&'.join(f'{urllib.parse.quote_plus(str(item[0]))}={urllib.parse.quote_plus(str(item[1]))}' for item in vnp_Params)
    
    # Tạo HMAC-SHA512 signature
    hmac_obj = hmac.new(vnp_HashSecret.encode('utf-8'), 
                        hashdata.encode('utf-8'), 
                        hashlib.sha512).hexdigest()
    
    # Thêm signature vào URL
    vnp_Params.append(('vnp_SecureHash', hmac_obj))
    
    # Tạo URL thanh toán
    payment_url = f"{vnp_Url}?{urllib.parse.urlencode(vnp_Params)}"
    
    return payment_url

# Hàm tạo QR code từ URL thanh toán
def generate_qr_code(payment_url):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(payment_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Chuyển đổi hình ảnh thành base64
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return img_str

# Trang xử lý thanh toán
@app.route('/payment/<invoice_code>', methods=['GET', 'POST'])
def process_payment(invoice_code):
    if request.method == 'POST':
        payment_method = request.form.get('payment_method')
        
        if payment_method == 'Chuyển khoản':
            # Lấy thông tin hóa đơn
            with sqlite3.connect('hotel.db') as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT total_amount FROM invoices WHERE invoice_code = ?", (invoice_code,))
                amount = cursor.fetchone()[0]
            
            # Tạo URL thanh toán VNPay
            payment_url = create_vnpay_payment_url(invoice_code, amount)
            
            # Tạo QR code
            qr_code = generate_qr_code(payment_url)
            
            return render_template('vnpay_qr.html', 
                                 invoice_code=invoice_code,
                                 amount=amount,
                                 qr_code=qr_code,
                                 payment_url=payment_url)
        
        # Xử lý thanh toán tiền mặt
        with sqlite3.connect('hotel.db') as conn:
            cursor = conn.cursor()
            # Lấy thông tin phòng từ hóa đơn
            cursor.execute("SELECT room_number FROM invoices WHERE invoice_code = ?", (invoice_code,))
            room_number = cursor.fetchone()[0]
            
            # Cập nhật trạng thái hóa đơn
            cursor.execute("UPDATE invoices SET status = 'paid' WHERE invoice_code = ? AND status = 'pending'",
                           (invoice_code,))
            # Cập nhật trạng thái phòng
            cursor.execute("UPDATE rooms SET status = 'available' WHERE room_number = ?", (room_number,))
            conn.commit()
            flash(f'Thanh toán thành công bằng {payment_method}!')
            return redirect(url_for('search_room'))

    return render_template('payment.html', invoice_code=invoice_code)

# Trang xử lý kết quả thanh toán VNPay
@app.route('/payment/vnpay_return')
def vnpay_return():
    vnp_Params = request.args
    
    # Lấy các tham số từ VNPay
    secureHash = vnp_Params.get('vnp_SecureHash', '')
    vnp_ResponseCode = vnp_Params.get('vnp_ResponseCode', '')
    vnp_TxnRef = vnp_Params.get('vnp_TxnRef', '')  # Mã hóa đơn
    
    # Xóa các tham số không cần thiết
    if 'vnp_SecureHash' in vnp_Params:
        del vnp_Params['vnp_SecureHash']
    if 'vnp_SecureHashType' in vnp_Params:
        del vnp_Params['vnp_SecureHashType']
    
    # Sắp xếp các tham số theo thứ tự a-z
    vnp_Params = sorted(vnp_Params.items())
    
    # Tạo chuỗi hash data
    hashdata = '&'.join(f'{urllib.parse.quote_plus(str(item[0]))}={urllib.parse.quote_plus(str(item[1]))}' for item in vnp_Params)
    
    # Tạo HMAC-SHA512 signature
    hmac_obj = hmac.new(VNPAY_CONFIG['vnp_HashSecret'].encode('utf-8'), 
                        hashdata.encode('utf-8'), 
                        hashlib.sha512).hexdigest()
    
    # Kiểm tra signature
    if secureHash == hmac_obj:
        if vnp_ResponseCode == '00':
            # Thanh toán thành công
            with sqlite3.connect('hotel.db') as conn:
                cursor = conn.cursor()
                # Lấy thông tin phòng từ hóa đơn
                cursor.execute("SELECT room_number FROM invoices WHERE invoice_code = ?", (vnp_TxnRef,))
                room_number = cursor.fetchone()[0]
                
                # Cập nhật trạng thái hóa đơn
                cursor.execute("UPDATE invoices SET status = 'paid' WHERE invoice_code = ? AND status = 'pending'",
                               (vnp_TxnRef,))
                # Cập nhật trạng thái phòng
                cursor.execute("UPDATE rooms SET status = 'available' WHERE room_number = ?", (room_number,))
                conn.commit()
            
            flash('Thanh toán thành công qua VNPay!')
        else:
            flash('Thanh toán thất bại!')
    else:
        flash('Chữ ký không hợp lệ!')
    
    return redirect(url_for('search_room'))

# Khởi tạo database khi ứng dụng chạy
init_db()

if __name__ == '__main__':
    app.run(debug=True)