import { createContext, useContext, useEffect, useState } from "react";
import { api, apiError } from "../lib/api";

const AuthContext = createContext(null);

// Only enable this for local development/testing.
// In frontend/.env:
// VITE_DEV_AUTH_BYPASS=true
const DEV_AUTH_BYPASS =
  import.meta.env.DEV &&
  import.meta.env.VITE_DEV_AUTH_BYPASS === "true";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [theme, setTheme] = useState(
    localStorage.getItem("theme") || "dark"
  );

  useEffect(() => {
    document.documentElement.classList.toggle(
      "dark",
      theme === "dark"
    );
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    if (DEV_AUTH_BYPASS) {
      setUser({
        id: "local-dev-admin",
        email: "Qht@talbros.com",
        name: "Administrator",
        role: "admin",
        isDevelopmentUser: true,
      });
      return;
    }

    api
      .get("/auth/me")
      .then((r) => setUser(r.data))
      .catch(() => setUser(false));
  }, []);

  const login = async (email, password) => {
    if (DEV_AUTH_BYPASS) {
      setUser({
        id: "local-dev-admin",
        email: email || "Qht@talbros.com",
        name: "Administrator",
        role: "admin",
        isDevelopmentUser: true,
      });

      return { ok: true };
    }

    try {
      const { data } = await api.post("/auth/login", {
        email,
        password,
      });

      setUser(data);
      return { ok: true };
    } catch (e) {
      return {
        ok: false,
        error: apiError(e),
      };
    }
  };

  const enterWithoutPassword = () => {
    if (!DEV_AUTH_BYPASS) {
      return {
        ok: false,
        error: "Password-free entry is disabled.",
      };
    }

    setUser({
      id: "local-dev-admin",
      email: "Qht@talbros.com",
      name: "Administrator",
      role: "admin",
      isDevelopmentUser: true,
    });

    return { ok: true };
  };

  const logout = async () => {
    if (!DEV_AUTH_BYPASS) {
      try {
        await api.post("/auth/logout");
      } catch {}
    }

    setUser(false);
  };

  const toggleTheme = () =>
    setTheme((t) => (t === "dark" ? "light" : "dark"));

  return (
    <AuthContext.Provider
      value={{
        user,
        setUser,
        login,
        logout,
        enterWithoutPassword,
        devAuthBypass: DEV_AUTH_BYPASS,
        theme,
        toggleTheme,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
