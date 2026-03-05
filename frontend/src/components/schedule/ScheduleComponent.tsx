import MonthComponent from "./MonthComponent";
import marchGames from "../../data/calendarData.json";
import { styled } from "@linaria/react";

export interface Game {
    date: number;
    opponent: string;
    time: string;
    location: string;
}
const Container = styled.div`
    display: flex;
    flex-direction: column;
`;
const Header = styled.div`
    color: #1b0464;
    font-family: Impact;
    padding: 0.5rem;
    align-self: center;
`;

const MonthsGrid = styled.div`
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
`;

const ScheduleComponent = () => {
    const gamesData: Game[] = marchGames.games;

    return (
        <Container>
            <Header>2025 Boston Red Sox Schedule</Header>
            <MonthsGrid>
                {Array.from({ length: 6 }).map((_, i) => (
                    <MonthComponent
                        key={i}
                        title="March / April"
                        games={gamesData}
                        daysInMonth={31}
                    />
                ))}
            </MonthsGrid>
        </Container>
    );
};

export default ScheduleComponent;
