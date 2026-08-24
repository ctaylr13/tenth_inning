import { styled } from "@linaria/react";

import type { Failure } from "../../api/errors";
import type { Inning } from "../../api/live";
import { POLL_INTERVAL_MS } from "../../api/pollGame";
import { useLiveComparison } from "./useLiveComparison";

const Page = styled.div`
    padding: 1rem;
`;

const Columns = styled.div`
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr));
    gap: 1rem;
    align-items: start;
`;

const Panel = styled.section`
    border: 1px solid #ddd;
    border-radius: 6px;
    padding: 0.75rem;
`;

const Meta = styled.p`
    color: #666;
    font-family: monospace;
    margin: 0.25rem 0;
`;

const Table = styled.table`
    border-collapse: collapse;
    width: 100%;
    margin-top: 0.5rem;
`;

const Th = styled.th`
    border: 1px solid #ccc;
    padding: 0.25rem 0.5rem;
    text-align: right;
`;

const Td = styled.td`
    border: 1px solid #eee;
    padding: 0.25rem 0.5rem;
    text-align: right;
`;

const Controls = styled.div`
    margin-bottom: 0.75rem;
    display: flex;
    gap: 0.5rem;
    align-items: center;
`;

const Linescore = ({ innings }: { innings: Inning[] }) => {
    if (innings.length === 0) return <Meta>no innings yet</Meta>;

    return (
        <Table>
            <thead>
                <tr>
                    <Th>Inn</Th>
                    <Th>Away R</Th>
                    <Th>Home R</Th>
                    <Th>Away H</Th>
                    <Th>Home H</Th>
                </tr>
            </thead>
            <tbody>
                {innings.map((inning) => (
                    <tr key={inning.inning_num}>
                        <Td>{inning.ordinalNum}</Td>
                        <Td>{inning.away_runs ?? "-"}</Td>
                        <Td>{inning.home_runs ?? "-"}</Td>
                        <Td>{inning.away_hits ?? "-"}</Td>
                        <Td>{inning.home_hits ?? "-"}</Td>
                    </tr>
                ))}
            </tbody>
        </Table>
    );
};

const FailureNote = ({ failure }: { failure: Failure }) => (
    <>
        <Meta>{failure.error.message}</Meta>
        {/* A retry can succeed on its own, so the id would just be noise. */}
        {failure.status !== "retry" && (
            <Meta>request id: {failure.error.request_id}</Meta>
        )}
    </>
);

/**
 * The same game, delivered two ways, side by side. The numbers are the point:
 * SSE costs one connection and one read however long it runs, while the polling
 * counter climbs every second for identical data.
 */
const LiveGame = () => {
    const { input, setInput, gamePk, valid, start, stop, live, polled } =
        useLiveComparison();

    return (
        <Page>
            <h1>Live layer — SSE vs REST polling</h1>

            <Controls>
                <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    aria-label="gamePk"
                />
                <button disabled={!valid} onClick={start}>
                    Start feed
                </button>
                <button onClick={stop}>Stop</button>
            </Controls>

            {!valid && <Meta>gamePk must be a positive whole number</Meta>}

            {gamePk === null ? (
                <Meta>pick a gamePk and start the feed</Meta>
            ) : (
                <Columns>
                    <Panel>
                        <h2>SSE</h2>
                        <Meta>status: {live.status}</Meta>
                        <Meta>connections opened: 1</Meta>
                        <Meta>
                            request id: {live.requestId ?? "—"} (per connection)
                        </Meta>
                        {live.failure && <FailureNote failure={live.failure} />}
                        {!live.failure &&
                            live.status === "done" &&
                            live.innings.length === 0 && (
                                <Meta>
                                    game exists, nothing recorded — empty state,
                                    not an error
                                </Meta>
                            )}
                        <Linescore innings={live.innings} />
                    </Panel>

                    <Panel>
                        <h2>REST polling</h2>
                        <Meta>every {POLL_INTERVAL_MS}ms</Meta>
                        <Meta>requests sent: {polled.requests}</Meta>
                        <Meta>request id: new one every tick</Meta>
                        {polled.failure && (
                            <FailureNote failure={polled.failure} />
                        )}
                        <Linescore innings={polled.innings} />
                    </Panel>
                </Columns>
            )}
        </Page>
    );
};

export default LiveGame;
