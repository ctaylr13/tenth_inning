import { useState } from "react";

import { useLiveGame, type LiveGame } from "../../api/live";
import { usePolledGame, type PolledGame } from "../../api/pollGame";

/** Pure, so the rule is testable without rendering. */
export const parseGamePk = (input: string): number | null => {
    const parsed = Number(input);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
};

export type LiveComparison = {
    input: string;
    setInput: (value: string) => void;
    gamePk: number | null;
    valid: boolean;
    start: () => void;
    stop: () => void;
    live: LiveGame;
    polled: PolledGame;
};

/** The same game over both transports, plus the input driving them. */
export const useLiveComparison = (): LiveComparison => {
    const [input, setInput] = useState("777");
    const [gamePk, setGamePk] = useState<number | null>(null);

    // NaN never equals itself, so letting one reach the hooks would make their
    // reset guard fire on every render.
    const parsed = parseGamePk(input);

    const live = useLiveGame(gamePk);
    const polled = usePolledGame(gamePk);

    const start = () => {
        if (parsed !== null) setGamePk(parsed);
    };
    const stop = () => setGamePk(null);

    return {
        input,
        setInput,
        gamePk,
        valid: parsed !== null,
        start,
        stop,
        live,
        polled,
    };
};
