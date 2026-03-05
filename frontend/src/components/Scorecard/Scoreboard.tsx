import { styled } from "@linaria/react";

const Box = styled.div`
    display: flex;
    flex-direction: column;
    gap: 1rem;
`;

const BottomRow = styled.div`
    display: flex;
    flex-direction: row;
    gap: 1rem;
`;

export const BoxScore = styled.div`
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    grid-template-rows: repeat(3, 1fr);
    gap: 8px; /* optional spacing */
`;

export const InningBox = styled.div`
    display: grid;
    grid-template-columns: repeat(10, 1fr);
    grid-template-rows: repeat(3, 1fr);
    gap: 8px; /* optional spacing */
`;

const Scoreboard = () => {
    return (
        <Box>
            <InningBox>
                <div>Team</div>
                <div>1</div>
                <div>2</div>
                <div>3</div>
                <div>4</div>
                <div>5</div>
                <div>6</div>
                <div>7</div>
                <div>8</div>
                <div>9</div>
                <div>BOS</div>
                <div>0</div>
                <div>0</div>
                <div>1</div>
                <div>0</div>
                <div>0</div>
                <div>0</div>
                <div>0</div>
                <div>0</div>
                <div>0</div>
                <div>TEX</div>
                <div>0</div>
                <div>0</div>
                <div>1</div>
                <div>0</div>
                <div>0</div>
                <div>0</div>
                <div>0</div>
                <div>0</div>
                <div>0</div>
            </InningBox>
            <BottomRow>
                <BoxScore>
                    <div>Final</div>
                    <div>R</div>
                    <div>H</div>
                    <div>E</div>
                    <div>LOB</div>
                    <div>BOS</div>
                    <div>5</div>
                    <div>6</div>
                    <div>-</div>
                    <div>4</div>
                    <div>TEX</div>
                    <div>2</div>
                    <div>7</div>
                    <div>-</div>
                    <div>3</div>
                </BoxScore>
                <div>
                    <div>WP: Chapman</div>
                    <div>LP: Jackson</div>
                    <div>SV: Slaten</div>
                </div>
            </BottomRow>
        </Box>
    );
};

export default Scoreboard;
