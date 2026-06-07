import { LoginForm } from '@shared/components/auth/LoginForm';

export function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  return <LoginForm onLoggedIn={onLoggedIn} />;
}
