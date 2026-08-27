import { styled } from "@linaria/react";

import type { PitchRow } from "../../api/pitchTable";
import { usePitchTable } from "./usePitchTable";

const Page = styled.main`
    max-width: 72rem;
    margin: 0 auto;
    padding: 3rem 1.5rem;
    color: #17231d;
    font-family: Inter, ui-sans-serif, system-ui, sans-serif;
`;

const Eyebrow = styled.p`
    margin: 0 0 0.5rem;
    color: #a43d2f;
    font-size: 0.75rem;
    font-weight: 800;
    letter-spacing: 0.14em;
    text-transform: uppercase;
`;

const Title = styled.h1`
    margin: 0;
    font-family: Georgia, serif;
    font-size: clamp(2rem, 6vw, 4rem);
    font-weight: 500;
    letter-spacing: -0.04em;
`;

const Summary = styled.p`
    max-width: 42rem;
    margin: 0.75rem 0 2rem;
    color: #5c6861;
    line-height: 1.6;
`;

const Controls = styled.div`
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: 1rem;
    padding: 1rem;
    border: 1px solid #d7ddd9;
    border-radius: 0.75rem;
    background: #f7f8f4;
`;

const GameForm = styled.form`
    display: flex;
    align-items: end;
    gap: 0.5rem;
`;

const Field = styled.label`
    display: grid;
    gap: 0.4rem;
    color: #526058;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
`;

const Input = styled.input`
    min-height: 2.5rem;
    box-sizing: border-box;
    padding: 0.6rem 0.75rem;
    border: 1px solid #b9c2bc;
    border-radius: 0.4rem;
    background: white;
    color: #17231d;
    font: inherit;
`;

const Select = styled.select`
    min-height: 2.5rem;
    min-width: 14rem;
    box-sizing: border-box;
    padding: 0.6rem 2rem 0.6rem 0.75rem;
    border: 1px solid #b9c2bc;
    border-radius: 0.4rem;
    background: white;
    color: #17231d;
    font: inherit;
`;

const LoadButton = styled.button`
    min-height: 2.5rem;
    padding: 0.6rem 1rem;
    border: 1px solid #17231d;
    border-radius: 0.4rem;
    background: #17231d;
    color: white;
    font: inherit;
    font-weight: 700;
    cursor: pointer;
`;

const ResultCount = styled.p`
    margin: 1.25rem 0 0.75rem;
    color: #5c6861;
    font-size: 0.9rem;
`;

const Status = styled.div`
    margin-top: 1.5rem;
    padding: 1.25rem;
    border: 1px solid #d7ddd9;
    border-radius: 0.75rem;
    background: #f7f8f4;
`;

const ErrorStatus = styled(Status)`
    border-color: #e7c0b8;
    background: #fff3f0;
    color: #8d2f22;
`;

const TableFrame = styled.div`
    overflow-x: auto;
    border: 1px solid #d7ddd9;
    border-radius: 0.75rem;
`;

const Table = styled.table`
    width: 100%;
    border-collapse: collapse;
    background: white;
    font-variant-numeric: tabular-nums;
`;

const Th = styled.th`
    padding: 0.75rem 0.9rem;
    border-bottom: 1px solid #cbd3ce;
    background: #edf0eb;
    color: #526058;
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    text-align: left;
    text-transform: uppercase;
    white-space: nowrap;
`;

const Td = styled.td`
    padding: 0.8rem 0.9rem;
    border-bottom: 1px solid #e5e9e6;
    font-size: 0.9rem;
    white-space: nowrap;
`;

const PitchCode = styled.span`
    display: inline-block;
    min-width: 2rem;
    margin-right: 0.5rem;
    padding: 0.2rem 0.4rem;
    border-radius: 999px;
    background: #dfe9e2;
    color: #264b34;
    font-size: 0.75rem;
    font-weight: 800;
    text-align: center;
`;

const PitchTableRow = styled.tr`
    &:last-child td {
        border-bottom: 0;
    }
`;

const formatCount = (row: PitchRow): string =>
    row.balls === null || row.strikes === null
        ? "—"
        : `${row.balls}-${row.strikes}`;

const formatVelocity = (velocity: number | null): string =>
    velocity === null ? "—" : `${velocity.toFixed(1)} mph`;

const formatResultCount = (count: number, querying: boolean): string =>
    querying ? "Running SQL…" : `${count} pitch${count === 1 ? "" : "es"}`;

const PitchTablePage = () => {
    const {
        gamePk,
        gamePkInput,
        pitchType,
        rows,
        pitchTypes,
        loading,
        querying,
        error,
        handleGamePkChange,
        handleGameSubmit,
        handlePitchTypeChange,
    } = usePitchTable();

    return (
        <Page>
            <Eyebrow>Browser analytics · Game {gamePk}</Eyebrow>
            <Title>Every pitch, queryable.</Title>
            <Summary>
                This table is rendered from the delivered Protobuf artifact.
                The browser converts it to Arrow, registers it in DuckDB, and
                runs the pitch-type filter locally with SQL.
            </Summary>

            <Controls>
                <GameForm onSubmit={handleGameSubmit}>
                    <Field>
                        Game PK
                        <Input
                            inputMode="numeric"
                            value={gamePkInput}
                            onChange={handleGamePkChange}
                        />
                    </Field>
                    <LoadButton type="submit">Load game</LoadButton>
                </GameForm>
                <Field>
                    Pitch type · SQL filter
                    <Select
                        value={pitchType}
                        onChange={handlePitchTypeChange}
                        disabled={loading || pitchTypes.length === 0}
                    >
                        <option value="">All pitch types</option>
                        {pitchTypes.map((option) => (
                            <option key={option.code} value={option.code}>
                                {option.description} ({option.code})
                            </option>
                        ))}
                    </Select>
                </Field>
            </Controls>

            {loading && <Status>Loading the game artifact…</Status>}
            {error && <ErrorStatus role="alert">{error}</ErrorStatus>}
            {!loading && !error && (
                <>
                    <ResultCount aria-live="polite">
                        {formatResultCount(rows.length, querying)}
                    </ResultCount>
                    <TableFrame>
                        <Table>
                            <thead>
                                <tr>
                                    <Th>Inning</Th>
                                    <Th>Batter</Th>
                                    <Th>Pitcher</Th>
                                    <Th>Count</Th>
                                    <Th>Pitch</Th>
                                    <Th>Velocity</Th>
                                    <Th>Result</Th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((row) => (
                                    <PitchTableRow
                                        key={`${row.paId}-${row.pitchNumber}`}
                                    >
                                        <Td>
                                            {row.halfInning} {row.inning}
                                        </Td>
                                        <Td>{row.batterId}</Td>
                                        <Td>{row.pitcherId}</Td>
                                        <Td>{formatCount(row)}</Td>
                                        <Td>
                                            <PitchCode>
                                                {row.pitchTypeCode || "—"}
                                            </PitchCode>
                                            {row.pitchTypeDescription ||
                                                "Unknown"}
                                        </Td>
                                        <Td>
                                            {formatVelocity(row.startSpeed)}
                                        </Td>
                                        <Td>{row.description || "—"}</Td>
                                    </PitchTableRow>
                                ))}
                            </tbody>
                        </Table>
                    </TableFrame>
                </>
            )}
        </Page>
    );
};

export default PitchTablePage;
