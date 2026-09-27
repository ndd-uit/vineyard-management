# Giao diện Vườn nhà

Giao diện Next.js để xem tình hình vườn nho và trò chuyện với trợ lý. FastAPI vẫn là nơi xử lý dữ liệu và xác nhận thao tác ghi.

## Chạy ở máy cá nhân

1. Chạy backend FastAPI ở `http://127.0.0.1:8000`.
2. Sao chép `.env.example` thành `.env.local` trong thư mục `frontend`, rồi sửa `NEXT_PUBLIC_API_BASE_URL` nếu backend ở địa chỉ khác. Không đặt khóa Gemini vào frontend.
3. Trong thư mục `frontend`, chạy `npm install` rồi `npm run dev`.
4. Mở `http://localhost:3000`.

Giao diện gọi FastAPI qua một tuyến chuyển tiếp cùng miền của Next.js để tránh lỗi CORS. Tuyến này chỉ cho phép các API đọc đang dùng và yêu cầu chat. Trên môi trường triển khai, đặt `NEXT_PUBLIC_API_BASE_URL` thành địa chỉ backend mà máy chủ Next.js truy cập được.

Lịch sử trò chuyện hiện chỉ nằm trong bộ nhớ trình duyệt và sẽ mất khi tải lại trang. Không có đăng nhập trong giai đoạn này.
