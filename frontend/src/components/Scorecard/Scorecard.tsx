import { styled } from "@linaria/react";
import AtBat from "./AtBat";

const ScoreGrid = styled.div`
    display: grid;
    grid-template-columns:
        160px 60px
        repeat(11, 40px)
        40px 40px 40px 50px 40px;
    gap: 0.5rem;
    align-items: center;
`;

const RowStyled = styled.div`
    display: flex;
    flex-direction: row;
    /* width: 100%; */
`;

const Scorecard = () => {
    const innings = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
    return (
        <div>
            <div>Player</div>
            <div>Pos.</div>
            {innings.map((inning) => (
                <div key={inning}>{inning}</div>
            ))}
            <div>AB</div>
            <div>R</div>
            <div>H</div>
            <div>RBI</div>
            <div>SB</div>
            <div>Betts</div>
            <div>RF</div>
            <RowStyled>
                {innings.map((inning) => (
                    // <div key={`bett-${inning}`}>
                    <AtBat key={`bett-${inning}`} />
                    // </div>
                ))}
            </RowStyled>
            <div>4</div>
            <div>1</div>
            <div>2</div>
            <div>1</div>
            <div>0</div>
        </div>
    );
};

export default Scorecard;
