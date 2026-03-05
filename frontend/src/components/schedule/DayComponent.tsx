import { styled } from "@linaria/react";

interface DayComponentProps {
    date: number;
    opponent: string;
    time: string;
    location: "home" | "away";
}

interface DayCellProps {
    location: "home" | "away";
}

const DayCell = styled.div<DayCellProps>`
    display: flex;
    flex-direction: column;
    border: 1px solid black;
    padding: 0.5rem;
    gap: 0.5rem;

    background-color: ${(props) =>
        props.location === "home" ? "red" : "lightgray"};
`;

const DayHeader = styled.div`
    display: flex;
    justify-content: flex-end;
    background-color: lightgray;
`;

const DayContent = styled.div`
    display: flex;
    flex-direction: column;
    background-color: aliceblue;
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
