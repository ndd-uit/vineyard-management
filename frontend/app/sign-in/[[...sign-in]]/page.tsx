import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-6 p-6"><h1 className="text-2xl font-semibold">Đăng nhập Vườn nhà</h1><SignIn /></div>;
}
