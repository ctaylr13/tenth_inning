import { styled } from "@linaria/react";

const Box = styled.div`
    aspect-ratio: 1;
    border: 1px solid black;

    display: grid;
    grid-template-columns: 70% 30%;
    grid-template-rows: 1fr 1fr;
    /* min-width: 8rem; */
    /* overflow: auto; */
    /* max-height: 100dvh; */
`;

const Cell = styled.div`
    border: 1px solid black;
    display: flex;
    align-items: center;
    justify-content: center;
`;

const ResultSection = styled.div`
    grid-column: 1;
    grid-row: 1 / 3;

    display: grid;
    grid-template-rows: 40% 60%;
`;

const ResultStyled = styled(Cell)`
    background-color: green;
    display: grid;
    grid-template-columns: 70% 30%;
    justify-items: center;
    align-items: center;
`;
const ResultCell = styled.div`
    width: 100%;
    height: 100%;
    border: 1px solid black;

    display: flex;
    align-items: center;
    justify-content: center;
`;
const BasepathStyled = styled(Cell)`
    background-color: blue;
`;

const StrikesStyled = styled(Cell)`
    background-color: red;
    grid-column: 2;
    grid-row: 1;
`;

const OutsStyled = styled(Cell)`
    background-color: orange;
    grid-column: 2;
    grid-row: 2;
`;

const VerticalRow = styled.div`
    display: flex;
    flex-direction: column;
    align-items: center;
`;
const mockStrikes = ["X", "X", "F", "C"];
const AtBat = () => {
    return (
        <Box>
            <ResultSection>
                <ResultStyled>
                    <ResultCell>1B</ResultCell>
                    <ResultCell>RBI</ResultCell>
                </ResultStyled>
                <BasepathStyled>basepath</BasepathStyled>
            </ResultSection>

            <StrikesStyled>
                <VerticalRow>
                    {mockStrikes.map((strike, i) => (
                        <div key={i}>{strike}</div>
                    ))}
                </VerticalRow>
            </StrikesStyled>
            <OutsStyled>2</OutsStyled>
        </Box>
    );
};

export default AtBat;
