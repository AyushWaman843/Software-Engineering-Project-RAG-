"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Session, User } from "@supabase/supabase-js";
import { AuthModal } from "@/components/auth/AuthModal";
import { createClient, supabaseConfigured } from "@/lib/supabase/client";
import type { AuthResult } from "@/lib/supabase/auth-actions";
import {
  resendSignupConfirmation,
  requestPasswordReset,
  signInWithEmail,
  signUpWithEmail,
  updatePassword,
} from "@/lib/supabase/auth-actions";
import { withBasePath } from "@/lib/base-path";
import { claimVisitorScanClient } from "@/lib/quota";

interface AuthContextValue {
  user: User | null;
  session: Session | null;
  loading: boolean;
  configured: boolean;
  signIn: (email: string, password: string) => Promise<AuthResult>;
  signUp: (email: string, password: string, captchaToken?: string) => Promise<AuthResult>;
  resendConfirmation: (email: string) => Promise<AuthResult>;
  requestPasswordReset: (email: string) => Promise<AuthResult>;
  updatePassword: (password: string) => Promise<AuthResult>;
  signOut: () => Promise<void>;
  openAuth: (mode?: "signin" | "signup" | "forgot") => void;
  closeAuth: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const DEMO_AUTO_LOGIN = process.env.NEXT_PUBLIC_DEMO_AUTO_LOGIN === "1";
const DEMO_EMAIL = process.env.NEXT_PUBLIC_DEMO_EMAIL?.trim() || "";
const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD || "";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authModalMode, setAuthModalMode] = useState<"signin" | "signup" | "forgot">("signin");
  const configured = supabaseConfigured();

  useEffect(() => {
    if (!configured) {
      setLoading(false);
      return undefined;
    }

    const supabase = createClient();

    supabase.auth.getSession().then(async ({ data }) => {
      if (data.session?.user) {
        setSession(data.session);
        setUser(data.session.user);
        setLoading(false);
        return;
      }

      if (DEMO_AUTO_LOGIN && DEMO_EMAIL) {
        try {
          const res = await fetch(`${window.location.origin}/scanner/api/demo/sign-in`, {
            method: "POST",
            credentials: "include",
          });
          const payload = (await res.json()) as {
            token_hash?: string;
            error?: string;
          };
          if (res.ok && payload.token_hash) {
            const { error } = await supabase.auth.verifyOtp({
              token_hash: payload.token_hash,
              type: "email",
            });
            if (!error) {
              const { data: refreshed } = await supabase.auth.getSession();
              setSession(refreshed.session);
              setUser(refreshed.session?.user ?? null);
            }
          } else if (DEMO_PASSWORD) {
            const result = await signInWithEmail(supabase, DEMO_EMAIL, DEMO_PASSWORD);
            if (result.status === "ok") {
              const { data: refreshed } = await supabase.auth.getSession();
              setSession(refreshed.session);
              setUser(refreshed.session?.user ?? null);
            }
          }
        } catch {
          /* demo sign-in optional */
        }
      }

      setLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession);
      setUser(nextSession?.user ?? null);
      setLoading(false);
      if (nextSession?.user) {
        if (event === "PASSWORD_RECOVERY") {
          if (
            typeof window !== "undefined" &&
            !window.location.pathname.includes("/auth/reset-password")
          ) {
            window.location.assign(withBasePath("/auth/reset-password"));
          }
          return;
        }
        if (event === "SIGNED_IN") {
          void claimVisitorScanClient(nextSession.user.id, nextSession.access_token);
          window.dispatchEvent(new Event("premium-status-updated"));
          // Keep the modal open and spinning for an extra 2 seconds
          // so that background SWR data fetches can complete before the user sees the page.
          setTimeout(() => setAuthModalOpen(false), 2000);
        } else {
          setAuthModalOpen(false);
        }
      } else if (
        event === "SIGNED_OUT" &&
        typeof window !== "undefined" &&
        window.location.pathname.includes("/report/")
      ) {
        window.location.replace(withBasePath("/"));
      }
    });

    return () => subscription.unsubscribe();
  }, [configured]);

  const signIn = useCallback(async (email: string, password: string) => {
    const supabase = createClient();
    return signInWithEmail(supabase, email, password);
  }, []);

  const signUp = useCallback(async (email: string, password: string, captchaToken?: string) => {
    const supabase = createClient();
    return signUpWithEmail(supabase, email, password, captchaToken);
  }, []);

  const resendConfirmation = useCallback(async (email: string) => {
    const supabase = createClient();
    return resendSignupConfirmation(supabase, email);
  }, []);

  const requestPasswordResetFn = useCallback(async (email: string) => {
    const supabase = createClient();
    return requestPasswordReset(supabase, email);
  }, []);

  const updatePasswordFn = useCallback(async (password: string) => {
    const supabase = createClient();
    return updatePassword(supabase, password);
  }, []);

  const signOut = useCallback(async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    if (typeof window !== "undefined") {
      window.location.replace(withBasePath("/"));
    }
  }, []);

  const openAuth = useCallback((mode: "signin" | "signup" | "forgot" = "signin") => {
    setAuthModalMode(mode);
    setAuthModalOpen(true);
  }, []);

  const closeAuth = useCallback(() => {
    setAuthModalOpen(false);
  }, []);

  const value = useMemo(
    () => ({
      user,
      session,
      loading,
      configured,
      signIn,
      signUp,
      resendConfirmation,
      requestPasswordReset: requestPasswordResetFn,
      updatePassword: updatePasswordFn,
      signOut,
      openAuth,
      closeAuth,
    }),
    [user, session, loading, configured, signIn, signUp, resendConfirmation, requestPasswordResetFn, updatePasswordFn, signOut, openAuth, closeAuth],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
      {configured && (
        <AuthModal open={authModalOpen} onClose={closeAuth} initialMode={authModalMode} />
      )}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
