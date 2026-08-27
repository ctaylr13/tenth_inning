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
import { getGameArtifactLocation } from "../../api/gameArtifact";
import {
    listPitchTypes,
    queryPitches,
    type PitchRow,
    type PitchTypeOption,
} from "../../api/pitchTable";

const DEFAULT_GAME_PK = 777940;

type GameSelection = {
    gamePk: number;
    revision: number;
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

const withError = (
    state: PitchTableState,
    error: string
): PitchTableState => ({
    ...state,
    loading: false,
    querying: false,
    error,
});

export const usePitchTable = (defaultGamePk = DEFAULT_GAME_PK) => {
    const [selection, setSelection] = useState<GameSelection>({
        gamePk: defaultGamePk,
        revision: 0,
    });
    const [gamePkInput, setGamePkInput] = useState(String(defaultGamePk));
    const [pitchType, setPitchType] = useState("");
    const [state, setState] = useState<PitchTableState>(emptyState);
    const databaseRef = useRef<GameArtifactDatabase | null>(null);
    const queryRevision = useRef(0);
    const { gamePk, revision } = selection;

    useEffect(() => {
        let cancelled = false;
        let openedDatabase: GameArtifactDatabase | null = null;

        setState(emptyState());
        setPitchType("");
        databaseRef.current = null;

        const load = async () => {
            const response = await getGameArtifactLocation(gamePk);
            if (cancelled) return;
            if (response.status !== "ok") {
                setState((current) =>
                    withError(current, response.error.message)
                );
                return;
            }
            if (!response.data.artifact_url) {
                setState((current) =>
                    withError(
                        current,
                        `Game ${gamePk} does not have a delivered artifact yet.`
                    )
                );
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
                    setState((current) =>
                        withError(current, errorMessage(error))
                    );
                }
            }
        };

        void load();

        return () => {
            cancelled = true;
            queryRevision.current += 1;
            databaseRef.current = null;
            if (openedDatabase) {
                void openedDatabase.close().catch(() => undefined);
            }
        };
    }, [gamePk, revision]);

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
                setState((current) =>
                    withError(current, "Enter a positive gamePk.")
                );
                return;
            }
            setSelection((current) => ({
                gamePk: nextGamePk,
                revision: current.revision + 1,
            }));
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
                setState((current) =>
                    withError(current, errorMessage(error))
                );
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
