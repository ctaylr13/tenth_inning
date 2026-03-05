import { styled } from "@linaria/react";

interface DayComponentProps {
    date: number;
    opponent: string;
    time: string;
}

const DayCell = styled.div`
    display: flex;
    flex-direction: column;
    border: 1px solid black;
    padding: 0.5rem;
    gap: 0.5rem;
    background-color: #094f4f;
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
    const { date, opponent, time } = props;
    return (
        <DayCell>
            <DayHeader>{date}</DayHeader>
            <DayContent>
                <div>{opponent}</div>
                <div>{time}</div>
            </DayContent>
        </DayCell>
    );
};

export default DayComponent;
