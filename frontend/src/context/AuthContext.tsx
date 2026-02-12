"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import api from "@/lib/api";

interface User {
    id: number;
    email: string;
    role: string;
}

interface AuthContextType {
    user: User | null;
    token: string | null;
    login: (email: string, password: string) => Promise<void>;
    register: (email: string, password: string, tenantName: string) => Promise<void>;
    logout: () => void;
    isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const storedToken = localStorage.getItem("access_token");
        if (storedToken) {
            setToken(storedToken);
            fetchUser(storedToken);
        } else {
            setIsLoading(false);
        }
    }, []);

    const fetchUser = async (accessToken: string) => {
        try {
            const res = await api.get("/auth/me", {
                headers: { Authorization: `Bearer ${accessToken}` },
            });
            setUser(res.data);
        } catch {
            localStorage.removeItem("access_token");
            setToken(null);
        } finally {
            setIsLoading(false);
        }
    };

    const login = async (email: string, password: string) => {
        const formData = new URLSearchParams();
        formData.append("username", email);
        formData.append("password", password);

        const res = await api.post("/auth/login", formData, {
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
        });

        const accessToken = res.data.access_token;
        localStorage.setItem("access_token", accessToken);
        setToken(accessToken);
        await fetchUser(accessToken);
    };

    const register = async (email: string, password: string, tenantName: string) => {
        const res = await api.post("/auth/register", {
            email,
            password,
            tenant_name: tenantName,
        });

        const accessToken = res.data.access_token;
        localStorage.setItem("access_token", accessToken);
        setToken(accessToken);
        await fetchUser(accessToken);
    };

    const logout = () => {
        localStorage.removeItem("access_token");
        setToken(null);
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, token, login, register, logout, isLoading }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) throw new Error("useAuth must be used within AuthProvider");
    return context;
}
