import React from "react";
import { styled } from "@linaria/react";

import type { Game } from "../../NewSchedule";
import DayComponent from "./DayComponent";

interface GameComponentProps {
    day: number;
    game?: Game;
}
const EmptyDay = styled.div`
    border: 1px solid black;
    padding: 0.5rem;
    min-height: 60px;
`;
const GameComponent: React.FC<GameComponentProps> = ({ day, game }) => {
    return game ? (
        <DayComponent
            date={game.date}
            opponent={game.opponent}
            time={game.time}
            location={game.location}
        />
    ) : (
        <EmptyDay>{day}</EmptyDay>
    );
};

export default GameComponent;
