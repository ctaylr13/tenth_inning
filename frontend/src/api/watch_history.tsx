export type DataRow = {
    gamePk: number;
    gameDate: string;
    officialDate?: string | null;
    doubleheader?: boolean;
    watched?: boolean;
};

export const updateWatchHistory = async (
    rows: DataRow[] | null | undefined,
    options?: { url?: string }
): Promise<{ updated: number } | null> => {
    if (!rows || rows.length === 0) return null;
    const payload = rows.map((r) => ({
        gamePk: r.gamePk,
        watched: !!r.watched,
    }));
    const url = options?.url ?? "http://localhost:8000/api/watchhistory";
    const res = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        const txt = await res.text().catch(() => res.statusText);
        throw new Error(`HTTP ${res.status}: ${txt}`);
    }
    return (await res.json()) as { updated: number };
};
