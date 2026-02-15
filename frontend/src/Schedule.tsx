import { useEffect, useState } from "react";
import { updateWatchHistory, type DataRow } from "./api/watch_history";

export type Row = DataRow & { watched?: boolean };

export default function Schedule() {
    const [rows, setRows] = useState<Row[] | null>(null);
    const [err, setErr] = useState<string | null>(null);

    useEffect(() => {
        fetch("/api/schedule")
            .then((res) => {
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return res.json();
            })
            .then((data: DataRow[]) => {
                setRows(data.map((r) => ({ watched: false, ...r })));
            })
            .catch((e) => setErr(String(e)));
    }, []);

    const toggleWatched = (gamePk: number) => {
        setRows(
            (prev) =>
                prev?.map((r) =>
                    r.gamePk === gamePk ? { ...r, watched: !r.watched } : r
                ) ?? null
        );
    };

    const submit = async () => {
        try {
            const resp = await updateWatchHistory(rows);
            alert(`Saved ${resp?.updated ?? 0} rows`);
        } catch (e) {
            alert("Save failed: " + e);
        }
    };

    if (err) return <div>Error: {err}</div>;
    if (!rows) return <div>Loading…</div>;
    if (rows.length === 0) return <div>No schedule data</div>;

    const watchedCount = rows.filter((r) => r.watched).length;

    return (
        <div style={{ padding: 16 }}>
            <h1>Red Sox 2025 Schedule</h1>
            <div style={{ marginBottom: 8 }}>
                Watched: {watchedCount} / {rows.length}
            </div>
            <button onClick={submit} style={{ marginBottom: 12 }}>
                Submit Watch history
            </button>

            <table style={{ borderCollapse: "collapse", width: "100%" }}>
                <thead>
                    <tr>
                        <th style={{ border: "1px solid #ccc", padding: 8 }}>
                            Watched
                        </th>
                        <th style={{ border: "1px solid #ccc", padding: 8 }}>
                            Game PK
                        </th>
                        <th style={{ border: "1px solid #ccc", padding: 8 }}>
                            Game Date (UTC)
                        </th>
                        <th style={{ border: "1px solid #ccc", padding: 8 }}>
                            Official Date
                        </th>
                        <th style={{ border: "1px solid #ccc", padding: 8 }}>
                            Doubleheader
                        </th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r, index) => {
                        const rowStyle: React.CSSProperties = r.watched
                            ? { backgroundColor: "#f0f0f0" }
                            : {};
                        return (
                            <tr key={index} style={rowStyle}>
                                <td
                                    style={{
                                        border: "1px solid #eee",
                                        padding: 8,
                                        textAlign: "center",
                                    }}
                                >
                                    <input
                                        type="checkbox"
                                        checked={!!r.watched}
                                        onChange={() => toggleWatched(r.gamePk)}
                                    />
                                </td>
                                <td
                                    style={{
                                        border: "1px solid #eee",
                                        padding: 8,
                                    }}
                                >
                                    {r.gamePk}
                                </td>
                                <td
                                    style={{
                                        border: "1px solid #eee",
                                        padding: 8,
                                    }}
                                >
                                    {new Date(r.gameDate).toLocaleString(
                                        undefined,
                                        { timeZone: "UTC" }
                                    )}
                                </td>
                                <td
                                    style={{
                                        border: "1px solid #eee",
                                        padding: 8,
                                    }}
                                >
                                    {r.officialDate ?? ""}
                                </td>
                                <td
                                    style={{
                                        border: "1px solid " + "#eee",
                                        padding: 8,
                                    }}
                                >
                                    {r.doubleheader ? "Yes" : "No"}
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
