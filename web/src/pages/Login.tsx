import { useSearchParams } from "react-router-dom";
import { BrandLogo } from "../components/BrandLogo";
import { Button } from "../components/ui/Button";
import { Alert } from "../components/ui/Alert";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const { mode, signIn, signUp } = useAuth();
  const [searchParams] = useSearchParams();
  const authError = searchParams.get("error");

  return (
    <div className="app-shell relative flex min-h-dvh flex-col">
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-12">
        <div className="mb-10 text-center">
          <div className="mx-auto mb-6 flex justify-center">
            <BrandLogo size="lg" />
          </div>
          <p className="mx-auto mt-4 max-w-xs text-sm leading-relaxed text-muted">
            Ranked job matches based on your goals. Review with intent, apply with confidence.
          </p>
        </div>

        {authError ? (
          <Alert tone="error" className="mb-4">
            Sign-in did not complete. Try again or create an account below.
          </Alert>
        ) : null}

        <Button fullWidth size="lg" onClick={() => void signIn()}>
          Sign in
        </Button>

        {mode === "keycloak" ? (
          <Button fullWidth size="lg" variant="secondary" className="mt-3" onClick={() => void signUp()}>
            Create account
          </Button>
        ) : null}

        <p className="mt-5 text-center text-sm text-subtle">
          {mode === "keycloak"
            ? "You'll use your email and a password on the next screen."
            : "Sign in to continue."}
        </p>
        <p className="mt-3 text-center text-xs text-subtle">
          By continuing you agree to our{" "}
          <a href="/terms" className="font-semibold text-brand-strong hover:text-brand-deep">
            Terms of Service
          </a>{" "}
          and{" "}
          <a href="/privacy" className="font-semibold text-brand-strong hover:text-brand-deep">
            Privacy Policy
          </a>
          .
        </p>
      </div>
    </div>
  );
}
