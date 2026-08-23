import { useCallback, useEffect, useState } from "react";

import { request, type Failure, type Outcome } from "../../api/errors";
import { updateWatchHistory, type DataRow } from "../../api/watch_history";

export type Row = DataRow & { watched?: boolean };

// Pure, so the wording is testable without rendering anything
const saveMessage = (res: Outcome<{ updated: number }>): string => {
    switch (res.status) {
        case "ok":
            return `Saved ${res.data.updated} rows`;
        case "invalid":
            return res.fields.length
                ? res.fields.map((f) => `${f.field}: ${f.reason}`).join("; ")
                : res.error.message;
        case "conflict":
            return `${res.error.message} (${String(res.error.details.duplicates ?? "")})`;
        case "retry":
            return `${res.error.message} Nothing was saved.`;
        default:
            // Nothing useful left to say, so hand over the id to grep for
            return `${res.error.message} request id: ${res.error.request_id}`;
    }
};

export const useSchedule = () => {
    const [rows, setRows] = useState<Row[] | null>(null);
    const [failure, setFailure] = useState<Failure | null>(null);
    const [saveMsg, setSaveMsg] = useState<string | null>(null);

    const load = useCallback(async () => {
        const res = await request<DataRow[]>("/api/schedule");
        if (res.status === "ok") {
            setRows(res.data.map((r) => ({ watched: false, ...r })));
            setFailure(null);
        } else {
            setFailure(res);
            setRows(null);
        }
    }, []);

    useEffect(() => {
        void load();
    }, [load]);

    const toggleWatched = useCallback((gamePk: number) => {
        setRows(
            (prev) =>
                prev?.map((r) =>
                    r.gamePk === gamePk ? { ...r, watched: !r.watched } : r
                ) ?? null
        );
    }, []);

    const submit = useCallback(async () => {
        if (!rows?.length) return;
        setSaveMsg(saveMessage(await updateWatchHistory(rows)));
    }, [rows]);

    return { rows, failure, saveMsg, load, toggleWatched, submit };
};
