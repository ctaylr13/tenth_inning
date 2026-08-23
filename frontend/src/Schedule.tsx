import { styled } from "@linaria/react";

import ScheduleFailure from "./components/schedule/ScheduleFailure";
import { useSchedule } from "./components/schedule/useSchedule";

const Page = styled.div`
    padding: 1rem;
`;

const Bar = styled.div`
    margin-bottom: 0.75rem;
`;

const Table = styled.table`
    border-collapse: collapse;
    width: 100%;
`;

const Th = styled.th`
    border: 1px solid #ccc;
    padding: 0.5rem;
`;

const Td = styled.td`
    border: 1px solid #eee;
    padding: 0.5rem;
`;

const CheckTd = styled(Td)`
    text-align: center;
`;

const GameRow = styled.tr`
    &[data-watched="true"] {
        background-color: #f0f0f0;
    }
`;

export default function Schedule() {
    const { rows, failure, saveMsg, load, toggleWatched, submit } = useSchedule();

    if (failure) {
        return <ScheduleFailure failure={failure} onRetry={() => void load()} />;
    }
    if (!rows) return <div>Loading…</div>;
    if (rows.length === 0) return <div>No games on the schedule.</div>;

    const watchedCount = rows.filter((r) => r.watched).length;

    return (
        <Page>
            <h1>Red Sox 2025 Schedule</h1>
            <Bar>
                Watched: {watchedCount} / {rows.length}
            </Bar>
            <Bar>
                <button onClick={() => void submit()}>Submit Watch history</button>
            </Bar>
            {saveMsg && <Bar>{saveMsg}</Bar>}

            <Table>
                <thead>
                    <tr>
                        <Th>Watched</Th>
                        <Th>Game PK</Th>
                        <Th>Game Date (UTC)</Th>
                        <Th>Official Date</Th>
                        <Th>Doubleheader</Th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r) => (
                        // gamePk repeats in the schedule data, so it is not a key on its own
                        <GameRow
                            key={`${r.gamePk}-${r.gameDate}`}
                            data-watched={!!r.watched}
                        >
                            <CheckTd>
                                <input
                                    type="checkbox"
                                    checked={!!r.watched}
                                    onChange={() => toggleWatched(r.gamePk)}
                                />
                            </CheckTd>
                            <Td>{r.gamePk}</Td>
                            <Td>
                                {new Date(r.gameDate).toLocaleString(undefined, {
                                    timeZone: "UTC",
                                })}
                            </Td>
                            <Td>{r.officialDate ?? ""}</Td>
                            <Td>{r.doubleheader ? "Yes" : "No"}</Td>
                        </GameRow>
                    ))}
                </tbody>
            </Table>
        </Page>
    );
}
