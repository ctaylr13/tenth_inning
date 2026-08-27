import {
    type ChangeEvent,
    type FormEvent,
    useCallback,
    useEffect,
    useRef,
    useState,
} from "react";

import {
    openGameArtifactDatabase,
    type GameArtifactDatabase,
} from "../../api/browserDuckDB";
import { request } from "../../api/errors";
import {
    listPitchTypes,
    queryPitches,
    type PitchRow,
    type PitchTypeOption,
} from "../../api/pitchTable";

const DEFAULT_GAME_PK = 777940;

type GameDetail = {
    artifact_url: string | null;
};

type PitchTableState = {
    rows: PitchRow[];
    pitchTypes: PitchTypeOption[];
    loading: boolean;
    querying: boolean;
    error: string | null;
};

const emptyState = (): PitchTableState => ({
    rows: [],
    pitchTypes: [],
    loading: true,
    querying: false,
    error: null,
});

const errorMessage = (error: unknown): string =>
    error instanceof Error
        ? error.message
        : "The pitch table could not be loaded.";

export const usePitchTable = () => {
    const [gamePk, setGamePk] = useState(DEFAULT_GAME_PK);
    const [gamePkInput, setGamePkInput] = useState(String(DEFAULT_GAME_PK));
    const [loadRevision, setLoadRevision] = useState(0);
    const [pitchType, setPitchType] = useState("");
    const [state, setState] = useState<PitchTableState>(emptyState);
    const databaseRef = useRef<GameArtifactDatabase | null>(null);
    const queryRevision = useRef(0);

    useEffect(() => {
        let cancelled = false;
        let openedDatabase: GameArtifactDatabase | null = null;

        setState(emptyState());
        setPitchType("");
        databaseRef.current = null;

        const load = async () => {
            const response = await request<GameDetail>(`/api/games/${gamePk}`);
            if (cancelled) return;
            if (response.status !== "ok") {
                setState((current) => ({
                    ...current,
                    loading: false,
                    error: response.error.message,
                }));
                return;
            }
            if (!response.data.artifact_url) {
                setState((current) => ({
                    ...current,
                    loading: false,
                    error: `Game ${gamePk} does not have a delivered artifact yet.`,
                }));
                return;
            }

            try {
                openedDatabase = await openGameArtifactDatabase(
                    response.data.artifact_url
                );
                if (cancelled) {
                    await openedDatabase.close();
                    return;
                }

                const pitchTypes = await listPitchTypes(
                    openedDatabase.connection
                );
                const rows = await queryPitches(openedDatabase.connection, "");
                if (cancelled) return;

                databaseRef.current = openedDatabase;
                setState({
                    rows,
                    pitchTypes,
                    loading: false,
                    querying: false,
                    error: null,
                });
            } catch (error) {
                if (openedDatabase) {
                    await openedDatabase.close().catch(() => undefined);
                    openedDatabase = null;
                }
                if (!cancelled) {
                    setState((current) => ({
                        ...current,
                        loading: false,
                        error: errorMessage(error),
                    }));
                }
            }
        };

        void load();

        return () => {
            cancelled = true;
            queryRevision.current += 1;
            databaseRef.current = null;
            if (openedDatabase) void openedDatabase.close();
        };
    }, [gamePk, loadRevision]);

    const handleGamePkChange = useCallback(
        (event: ChangeEvent<HTMLInputElement>) => {
            setGamePkInput(event.target.value);
        },
        []
    );

    const handleGameSubmit = useCallback(
        (event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            const nextGamePk = Number(gamePkInput);
            if (!Number.isSafeInteger(nextGamePk) || nextGamePk <= 0) {
                setState((current) => ({
                    ...current,
                    error: "Enter a positive gamePk.",
                }));
                return;
            }
            setGamePk(nextGamePk);
            setLoadRevision((current) => current + 1);
        },
        [gamePkInput]
    );

    const handlePitchTypeChange = useCallback(
        async (event: ChangeEvent<HTMLSelectElement>) => {
            const selected = event.target.value;
            const database = databaseRef.current;
            setPitchType(selected);
            if (!database) return;

            const revision = ++queryRevision.current;
            setState((current) => ({ ...current, querying: true, error: null }));
            try {
                const rows = await queryPitches(database.connection, selected);
                if (revision !== queryRevision.current) return;
                setState((current) => ({
                    ...current,
                    rows,
                    querying: false,
                }));
            } catch (error) {
                if (revision !== queryRevision.current) return;
                setState((current) => ({
                    ...current,
                    querying: false,
                    error: errorMessage(error),
                }));
            }
        },
        []
    );

    return {
        gamePk,
        gamePkInput,
        pitchType,
        ...state,
        handleGamePkChange,
        handleGameSubmit,
        handlePitchTypeChange,
    };
};
