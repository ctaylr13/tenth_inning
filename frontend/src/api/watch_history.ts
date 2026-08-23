import { request, type Outcome } from "./errors";

export type DataRow = {
    gamePk: number;
    gameDate: string;
    officialDate?: string | null;
    doubleheader?: boolean;
    watched?: boolean;
};

export const updateWatchHistory = async (
    rows: DataRow[],
    options?: { url?: string }
): Promise<Outcome<{ updated: number }>> => {
    const payload = rows.map((r) => ({
        gamePk: r.gamePk,
        watched: !!r.watched,
    }));
    // Relative through the Vite proxy (same-origin, no CORS)
    const url = options?.url ?? "/api/watchhistory";
    return request<{ updated: number }>(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
};
