import { styled } from "@linaria/react";
import DayHeader from "./DayHeader";
import type { Game } from "../../NewSchedule";
import GameComponent from "./GameComponent";

const Box = styled.div`
    display: flex;
    flex-direction: column;
`;

const MonthTitle = styled.div`
    color: #1b0464;
    font-family: Impact;
    padding: 0.5rem;
`;

const DaysHeaderRow = styled.div`
    display: grid;
    grid-template-columns: repeat(7, 1fr);
`;

const DaysGrid = styled.div`
    display: grid;
    grid-template-columns: repeat(7, 1fr);
`;

interface MonthComponentProps {
    title: string;
    games: Game[];
    daysInMonth: number;
}

const MonthComponent: React.FC<MonthComponentProps> = ({
    title,
    games,
    daysInMonth,
}) => {
    const days = Array.from({ length: daysInMonth }, (_, i) => i + 1);
    const gamesByDate = new Map(games.map((g) => [g.date, g]));
    return (
        <Box>
            <MonthTitle>{title}</MonthTitle>

            <DaysHeaderRow>
                {["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"].map((d) => (
                    <DayHeader key={d} day={d} />
                ))}
            </DaysHeaderRow>

            <DaysGrid>
                {days.map((day) => (
                    <GameComponent
                        key={day}
                        day={day}
                        game={gamesByDate.get(day)}
                    />
                ))}
            </DaysGrid>
        </Box>
    );
};

export default MonthComponent;
