import { styled } from "@linaria/react";

interface DayComponentProps {
    date: number;
    opponent: string;
    time: string;
    location: string;
}

interface DayCellProps {
    location: string;
}

const DayCell = styled.div<DayCellProps>`
    display: flex;
    flex-direction: column;
    border: 1px solid black;
    padding: 0.5rem;
    gap: 0.5rem;
    font-family: Impact;
    color: ${(props) => (props.location === "home" ? "white" : "black")};
    background-color: ${(props) =>
        props.location === "home" ? "darkred" : "lightgray"};
`;

const DayHeader = styled.div`
    display: flex;
    justify-content: flex-end;
`;

const DayContent = styled.div`
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    flex: 1;
`;

const DayComponent: React.FC<DayComponentProps> = (props) => {
    const { date, opponent, time, location } = props;

    return (
        <DayCell location={location}>
            <DayHeader>{date}</DayHeader>
            <DayContent>
                <div>{opponent}</div>
                <div>{time}</div>
            </DayContent>
        </DayCell>
    );
};

export default DayComponent;
