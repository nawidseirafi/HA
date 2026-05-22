import { LoginForm } from '../components/auth/LoginForm';

interface Props {
  onLoggedIn: () => void;
}

export function LoginPage({ onLoggedIn }: Props) {
  return (
    <main className="login-shell">
      <section className="login-panel">
        <div className="login-card-shell">
          <LoginForm onLoggedIn={onLoggedIn} />
        </div>
      </section>
    </main>
  );
}
