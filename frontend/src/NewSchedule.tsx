import { styled } from "@linaria/react";
import DayComponent from "./components/schedule/DayComponent";
import DayHeader from "./components/schedule/DayHeader";
const Box = styled.div`
    display: flex;
    flex-direction: column;
`;

const NewSchedule = () => {
    return (
        <Box>
            <DayHeader day={"SUN"} />
            <DayComponent date={1} opponent={"TEX"} time={"7:10"} />
        </Box>
    );
};

export default NewSchedule;
