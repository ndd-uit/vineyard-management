import type { CSSProperties } from "react";

export function ChatGrapeLoader() {
  return (
    <div className="grape-chat-loader flex items-center gap-3" role="status" aria-live="polite">
      <span className="grape-chat-fruit flex items-center gap-1" aria-hidden="true">
        <span className="grape-chat-berry" />
        <span className="grape-chat-berry" />
        <span className="grape-chat-berry" />
      </span>
      <span>Con đang xem giúp mẹ...</span>
    </div>
  );
}

export function PageGrapeLoader({ message = "Đang lấy thông tin cho mẹ..." }: { message?: string }) {
  return (
    <div className="grape-page-loader flex flex-col items-center justify-center gap-3" role="status" aria-live="polite">
      <span className="grape-wheel-wrap" aria-hidden="true">
        <span className="grape-wheel-leaf" />
        <span className="grape-wheel">
          {Array.from({ length: 8 }, (_, index) => (
            <span
              className="grape-wheel-berry"
              key={index}
              style={{ "--berry-angle": `${index * 45}deg` } as CSSProperties}
            />
          ))}
        </span>
      </span>
      <span>{message}</span>
    </div>
  );
}
