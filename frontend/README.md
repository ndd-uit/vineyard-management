# Giao diện Vườn nhà

Giao diện Next.js để xem tình hình vườn nho và trò chuyện với trợ lý. FastAPI vẫn là nơi xử lý dữ liệu và xác nhận thao tác ghi.

## Chạy ở máy cá nhân

1. Chạy backend FastAPI ở `http://127.0.0.1:8000`.
2. Sao chép `.env.example` thành `.env.local` trong thư mục `frontend`. Điền `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` và `BACKEND_API_URL`. Không đặt khóa Gemini vào frontend.
3. Trong thư mục `frontend`, chạy `npm install` rồi `npm run dev`.
4. Mở `http://localhost:3000`.

Giao diện gọi FastAPI qua tuyến chuyển tiếp cùng miền của Next.js. Tuyến này lấy session token Clerk phía máy chủ và chuyển cho FastAPI. Trên Vercel, đặt `BACKEND_API_URL` thành địa chỉ backend mà máy chủ Next.js truy cập được (không dùng biến `NEXT_PUBLIC_API_BASE_URL` cũ). FastAPI cần `CLERK_SECRET_KEY`, `CLERK_ISSUER` và `CLERK_AUTHORIZED_PARTIES` để tự xác minh token. Có thể đặt `CLERK_ALLOWED_USER_IDS` để chỉ cho các tài khoản gia đình được dùng.

Trong Clerk Dashboard, bật chế độ Invite-only và gửi lời mời cho các thành viên. Chỉ gửi invitation không đủ để khóa đăng ký công khai. Lịch sử trò chuyện hiện chỉ nằm trong bộ nhớ trình duyệt và sẽ mất khi tải lại trang.
