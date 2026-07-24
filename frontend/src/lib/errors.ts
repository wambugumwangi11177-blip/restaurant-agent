import axios from "axios";

export function getErrorMessage(err: unknown, fallback = "Something went wrong"): string {
    if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        if (typeof detail === "string") return detail;
    }
    if (err instanceof Error) return err.message;
    return fallback;
}

export function isHttpStatus(err: unknown, status: number): boolean {
    return axios.isAxiosError(err) && err.response?.status === status;
}
