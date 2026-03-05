import React from "react";
import { styled } from "@linaria/react";

const Box = styled.div`
    display: flex;
    flex-direction: column;
    background-color: #1b0464;
    /* align-self: flex-start; */
    color: white;
    font-family: Impact;
    padding: 0.5rem;
`;

interface DayHeaderProps {
    day: string;
}

const DayHeader: React.FC<DayHeaderProps> = (props) => {
    const { day } = props;
    return <Box>{day}</Box>;
};

export default DayHeader;
